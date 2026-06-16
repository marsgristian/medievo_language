# Guia para implementar seções específicas medievo

Este guia descreve como expandir a linguagem mínima sem modificar a gramática Lark nem o parser genérico.

A regra arquitetural é:

```text
A linguagem mínima monta a AST genérica.
A seção específica interpreta a AST genérica daquela seção.
```

Portanto, para criar uma seção nova, você cria um arquivo novo e registra a seção. Não é necessário alterar `med_evo/parser/medievo.lark`, `med_evo/minimal/compiler.py` ou os modelos base.

## 1. Interface conceitual

Uma seção específica possui cinco partes:

```text
SpecificSectionParser
  section_parser
  subsection_parser
  item_parser
  normalization
  associated_errors
```

### `section_parser`

Define requisitos da linha de seção:

- `canonical_name`: nome canônico interno;
- `accepted_names`: aliases aceitos no texto;
- `required`: se a seção é obrigatória no documento;
- `required_section_value`: se a seção exige valor após `:`.

### `subsection_parser`

Define as subseções dessa seção:

- `default_subsections`: subseções conhecidas;
- `required_subsections`: subseções obrigatórias;
- `allow_new`: permite subseções não previstas;
- `inline_states`: states reconhecidos dentro de itens;
- `use_default_subsections_as_inline_states`: se as subseções default também valem como state inline.

### `item_parser`

Define restrições genéricas dos itens:

- `allow_free_text`: permite item sem `:`;
- `require_key`: exige `key: value`;
- `allow_children`: permite itens compostos em `children`;
- `accepted_keys`: keys conhecidas.

Validações clínicas mais complexas devem ser implementadas em `validate_item()` ou `parse_item()`.

### `normalization`

Define como a seção será escrita na forma ideal futuramente:

- `normalized_section_name`;
- `normalized_subsection_names`;
- `normalized_item_keys`.

A linguagem mínima ainda não renderiza texto normalizado final. Esse campo é o ponto de extensão para a próxima etapa.

### `associated_errors`

Define códigos de erros e warnings gerados pela seção.

Isso evita diagnostics soltos e facilita testes.

## 2. Exemplo mínimo de seção específica

Crie um arquivo, por exemplo:

```text
med_evo/specific_sections/medicamentos.py
```

Conteúdo:

```python
from __future__ import annotations

from typing import Any

from med_evo.models import ClinicalDocument, ClinicalItem, ClinicalSection, CompilerDiagnostic
from med_evo.sections import (
    BaseSpecificSectionParser,
    ItemParserConfig,
    NormalizationConfig,
    SectionParserConfig,
    SubsectionParserConfig,
)


class MedicamentosSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="MEDICAMENTOS",
        accepted_names=("MEDICAMENTOS", "MEDICAÇÕES", "MEDICACOES"),
        required=False,
        required_section_value=False,
    )

    subsection_parser = SubsectionParserConfig(
        default_subsections=("Atual", "Prévio", "Suspenso"),
        required_subsections=(),
        allow_new=True,
        inline_states=("atual", "prévio", "previo", "suspenso"),
    )

    item_parser = ItemParserConfig(
        allow_free_text=True,
        require_key=False,
        allow_children=True,
    )

    normalization = NormalizationConfig(
        normalized_section_name="MEDICAMENTOS",
        normalized_subsection_names={"previo": "Prévio"},
    )

    def parse_item(
        self,
        item: ClinicalItem,
        section: ClinicalSection,
        diagnostics: list[CompilerDiagnostic],
    ) -> dict[str, Any]:
        return {
            "raw_text": item.raw_text,
            "state": item.state,
            "name_or_key": item.key,
            "values": [value.value for value in item.values],
            "commented_values": item.commented_values,
            "children": [self.parse_item(child, section, diagnostics) for child in item.children],
        }
```

Uso:

```python
from med_evo import compile_medievo
from med_evo.sections import SectionRegistry
from med_evo.specific_sections.medicamentos import MedicamentosSection

registry = SectionRegistry([MedicamentosSection()])
compiled = compile_medievo(text, section_registry=registry)

print(compiled.processed_sections["MEDICAMENTOS"].data)
```

## 3. Exemplo de seção obrigatória

```python
class DiagnosticoSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="DIAGNOSTICO",
        accepted_names=("DIAGNÓSTICO", "DIAGNOSTICO", "HD"),
        required=True,
    )
```

Se o documento não tiver nenhuma seção com nome aceito, o registry adiciona diagnostic:

```text
required_section_missing
```

## 4. Exemplo de seção que exige `section_value`

```python
class ExamesSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="EXAMES",
        accepted_names=("EXAMES",),
        required=False,
        required_section_value=True,
    )
```

Válido:

```medievo
# EXAMES: laboratoriais
```

Inválido semanticamente:

```medievo
# EXAMES:
```

Diagnostic:

```text
required_section_value_missing
```

## 5. Exemplo de subseções restritas

```python
class DispositivosSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="DISPOSITIVOS",
        accepted_names=("DISPOSITIVOS",),
    )
    subsection_parser = SubsectionParserConfig(
        default_subsections=("Atual", "Prévio", "Suspenso"),
        allow_new=False,
    )
```

Se o texto tiver:

```medievo
# DISPOSITIVOS:
> Aleatório:
SVD: 10/06-12/06
```

Gera warning:

```text
unknown_subsection
```

## 6. Exemplo de keys restritas

```python
class ControlesSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="CONTROLES",
        accepted_names=("CONTROLES", "SINAIS VITAIS"),
    )
    item_parser = ItemParserConfig(
        allow_free_text=False,
        require_key=True,
        accepted_keys=("FC", "FR", "Tax", "SatO2", "PAS", "PAD", "PAM", "HGT"),
    )
```

Texto livre gera erro:

```text
free_text_not_allowed
```

Key desconhecida gera warning:

```text
unknown_item_key
```

## 7. Quando sobrescrever métodos

Use apenas config quando as regras forem simples.

Sobrescreva `validate_item()` quando quiser validar estrutura específica:

```python
def validate_item(self, item, section):
    diagnostics = super().validate_item(item, section)
    if item.key == "FC" and not item.values:
        diagnostics.append(...)
    return diagnostics
```

Sobrescreva `parse_item()` quando quiser produzir objeto específico:

```python
def parse_item(self, item, section, diagnostics):
    return ControleVital(
        sigla=item.key,
        raw_value=item.values[0].value if item.values else None,
        date=item.date,
    )
```

Sobrescreva `normalize_section()` quando quiser gerar a forma ideal da seção:

```python
def normalize_section(self, section, data):
    return "# CONTROLES:\n" + " | ".join(...)
```

## 8. Fluxo recomendado para criar uma seção nova

1. Criar arquivo da seção específica.
2. Declarar `section_parser` com `canonical_name` e `accepted_names`.
3. Declarar `subsection_parser`, mesmo que vazio.
4. Declarar `item_parser` com regras permissivas no início.
5. Implementar `parse_item()` só para extrair o essencial.
6. Adicionar validações semânticas gradualmente.
7. Criar testes da seção.
8. Só depois implementar `normalize_section()`.

## 9. Regra de ouro

Não altere a linguagem mínima para comportamentos clínicos específicos.

Correto:

```text
Adicionar med_evo/specific_sections/controles.py
```

Errado:

```text
Modificar a gramática Lark para reconhecer FC, FR, Tax, SatO2...
```

A gramática deve continuar pequena e estável. O conhecimento clínico pertence às seções específicas.


---
