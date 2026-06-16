# medievo mínimo

**MediEvo** é uma DSL inspirada em Markdown para escrever evolução médica com estrutura suficiente para gerar um Python object/JSON confiável.

Esta entrega contém **somente a linguagem mínima**. O pipeline antigo foi removido do pacote, da interface Streamlit, dos testes, dos exemplos e da documentação.

A decisão arquitetural é:

```text
texto medievo
  -> gramática Lark estrutural mínima
  -> parser genérico Python
  -> AST clínica genérica
  -> parsers específicos de seção, opcionais e plugáveis
  -> JSON / Python object
```

A linguagem mínima não conhece regras clínicas de `MEDICAMENTOS`, `EXAMES`, `CONTROLES`, etc. Ela só cria a estrutura base. Regras clínicas entram depois por arquivos de seção específica registrados em `SectionRegistry`.

## Instalação

Com Poetry:

```bash
poetry install --with ui,dev
poetry run pytest
poetry run streamlit run app_streamlit.py
```

Com pip:

```bash
pip install -r requirements.txt
pip install -e .
python -m pytest
streamlit run app_streamlit.py
```

## Uso em Python

```python
from med_evo import compile_medievo

compiled = compile_medievo(text)
print(compiled.to_json())
```

`compile_medievo` é o compilador mínimo principal. `compile_minimal_medievo` continua existindo como alias explícito.

## Estruturas principais

A compilação retorna `ClinicalDocument`:

```python
ClinicalDocument(
    reference_datetime=datetime | None,
    sections=list[ClinicalSection],
    diagnostics=list[CompilerDiagnostic],
    processed_sections=dict[str, list[Any]],
    raw_text=str,
)
```

Cada seção:

```python
ClinicalSection(
    section_name=str,
    section_value=str | None,
    commented_values=list[str],
    states=list[Subsection],
    items=list[ClinicalItem],
    ignored_comments=list[str],
    raw_text=str,
)
```

Cada item:

```python
ClinicalItem(
    raw_text=str,
    date=ClinicalDate | ClinicalDatePeriod | None,
    state=str | None,
    key=str | None,
    values=list[ClinicalValue],
    commented_values=list[str],
    children=list[ClinicalItem],
)
```

Datas usam `datetime` internamente e preservam o texto original:

```python
ClinicalDate(
    raw_text="10/06",
    value=datetime(2026, 6, 10),
    precision="day",
    explicit_year=False,
    inferred_year=2026,
)
```

Períodos possuem delta:

```python
ClinicalDatePeriod(
    raw_text="10/06-12/06",
    start=ClinicalDate(...),
    end=ClinicalDate(...),
    delta_time=timedelta(days=2),
)
```

## Exemplo mínimo

```medievo
EVOLUÇÃO - DIURNA - 16/06/2026 10:30
# EXAMES: laboratoriais (últimas 24h)
Hb: 10,2; Leuco: 12000; Plaquetas: 250000 | PCR: 45
> Prévio: 10/06 Hb: 9,8; PCR: 80
/* comentário ignorável */
# MEDICAMENTOS:
Dipirona: se febre (T > 37,8°C)
# DISPOSITIVOS:
SVD: 10-12/06
```

## Gramática Lark

Arquivo principal:

```text
med_evo/parser/medievo.lark
```

A gramática reconhece:

- seção com `#`;
- subseção com `>`;
- linha textual;
- linha em branco.

A gramática e as pré-validações sintáticas mínimas bloqueiam:

- seção sem nome: `#`;
- seção com subseção na mesma linha: `# MEDICAMENTOS > Antibiótico:`;
- seção com separador universal de item: `# CONTROLES: FC: 100 | FR: 20`;
- subseção sem nome: `>:`;
- subseção sem `:`: `> Prévio`;
- item com key explicitamente vazia: `: value`;
- item com key explícita e value vazio: `key:` ou `key : |`.

A gramática **não** normaliza nomes de seção, não interpreta medicação, não valida exames, não classifica controles e não decide obrigatoriedade de seção. Isso pertence aos parsers específicos.

## Regras semânticas genéricas

### Datas

Formatos aceitos:

```text
dd/mm/aaaa hh:mm
dd/mm/aaaa
dd/mm
(dd/mm)
```

Períodos aceitos:

```text
DATA-DATA
dd-DATA
```

Regra de ano implícito:

- o ano explícito deve vir no cabeçalho ou em uma data completa;
- datas `dd/mm` usam o ano do cabeçalho;
- se a data `dd/mm` ainda não ocorreu em relação ao cabeçalho, o parser assume o ano anterior.

Exemplo com cabeçalho `16/06/2026`:

```text
10/06 -> 10/06/2026
20/06 -> 20/06/2025
```

### Valores entre parênteses

Parênteses viram `commented_values`, não comentários ignorados.

```medievo
Dipirona: se febre (T > 37,8°C)
```

### Comentários ignoráveis

Comentários que o sistema deve ignorar usam `/* */`:

```medievo
FC: 120 /* valor duvidoso, não renderizar */
```

O conteúdo é preservado em `ignored_comments`, mas não entra como value clínico.

### Itens compostos

O separador `;` divide values. Se um value contém outro `key: value`, ele vira `children`.

```medievo
Hb: 10,2; Leuco: 12000; Plaquetas: 250000
```

Resultado conceitual:

```python
ClinicalItem(
    key="Hb",
    values=["10,2"],
    children=[
        ClinicalItem(key="Leuco", values=["12000"]),
        ClinicalItem(key="Plaquetas", values=["250000"]),
    ],
)
```

## Interface de seções específicas

O projeto já possui o contrato para seções específicas em:

```text
med_evo/sections/base.py
med_evo/sections/registry.py
```

A ideia é criar um arquivo por seção, por exemplo:

```text
med_evo/specific_sections/medicamentos.py
med_evo/specific_sections/exames.py
med_evo/specific_sections/controles.py
```

Cada arquivo implementa uma classe que herda de `BaseSpecificSectionParser` e declara:

- `section_parser`: nomes aceitos, obrigatoriedade e necessidade de `section_value`;
- `subsection_parser`: subseções default, subseções obrigatórias, permissão de subseções novas e states inline;
- `item_parser`: restrições de item;
- `normalization`: forma ideal de escrita para normalização futura;
- `associated_errors`: códigos de erros/warnings dessa seção.

Exemplo mínimo:

```python
from med_evo.sections import (
    BaseSpecificSectionParser,
    ItemParserConfig,
    SectionParserConfig,
    SectionRegistry,
    SubsectionParserConfig,
)

class MedicamentosSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="MEDICAMENTOS",
        accepted_names=("MEDICAMENTOS", "MEDICAÇÕES", "MEDICACOES"),
        required=False,
    )
    subsection_parser = SubsectionParserConfig(
        default_subsections=("Atual", "Prévio", "Suspenso"),
        allow_new=True,
    )
    item_parser = ItemParserConfig(require_key=False, allow_free_text=True)

registry = SectionRegistry([MedicamentosSection()])
compiled = compile_medievo(text, section_registry=registry)
```

Leia o guia completo em [`guia_secoes_especificas.md`](guia_secoes_especificas.md).

## Streamlit

Execute:

```bash
streamlit run app_streamlit.py
```

A interface possui:

- editor de texto medievo;
- visualização da AST/JSON;
- diagnostics sintáticos e semânticos;
- testes visuais da gramática mínima;
- exemplo da interface de seções específicas.

## Testes

Execute:

```bash
python -m pytest
```

A suíte cobre:

- erros sintáticos estruturais;
- datas completas, parciais e entre parênteses;
- período com `delta_time`;
- `commented_values` versus `ignored_comments`;
- itens compostos com `children`;
- registro de seções específicas sem alterar a linguagem mínima.

## Arquivos importantes

```text
med_evo/parser/medievo.lark          gramática Lark estrutural
med_evo/minimal/compiler.py         compilador mínimo
med_evo/minimal/dates.py            parser de datas/períodos
med_evo/minimal/text.py             utilitários de split/commented values
med_evo/models.py                   dataclasses da AST
med_evo/sections/base.py            contrato para seções específicas
med_evo/sections/registry.py        registro de seções específicas
app_streamlit.py                    interface visual
manual_de_escrita.md                manual prático da linguagem
guia_secoes_especificas.md          guia para implementar novas seções
```
