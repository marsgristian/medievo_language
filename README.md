# Medi Evo language

Medi Evo language é uma linguagem textual para escrever evoluções médicas semi-estruturadas, validar seções obrigatórias e gerar objetos Python/JSON para uso por outros sistemas.

## Contexto

Este projeto faz parte de:

Trabalho final da disciplina Construção de compiladores - Prof. Dr. Daniel Lucrédio  
DC - Departamento de Computação - UFSCar  
2026/1

Autor: Cristian César Martins, RA 799714

Desenvolvido no contexto de estágio no Ebserh/HU-UFSCar, orientado por Sandra Abib, Niarchos Antonio Prata Cione, Leandro Canali Ramos e Marcos Antonio Francisco.

## Instalação

Com Poetry:

```bash
poetry install --with ui,dev
```

Como biblioteca Python local:

```bash
pip install -e .
```

Para gerar o pacote:

```bash
poetry build
```

## Uso Como Biblioteca

Depois de instalar, use como uma biblioteca Python comum:

```python
from medi_evo import compile_text, compile_json

text = """
EVOLUCAO 16/06/2026
# INFORMACOES DO PACIENTE
Nome: Maria | Idade: 2 anos | Data internacao: 10/06/2026 | Sexo: feminino | Peso: 16/06 10 kg
# DIAGNOSTICO
R09 Hipoxemia
"""

result = compile_text(text, normalization="line_min")

print(result["object"])
print(result["normalized_text"])
print(result["warnings"])
print(result["errors"])

compact_text = compile_json(result, normalization="char_min")
```

`compile_text` retorna:

- `object`: objeto com `document` completo e `sections` processadas;
- `normalized_text`: texto renderizado no modo solicitado;
- `warnings`: avisos de validação;
- `errors`: erros de validação.

Mesmo quando houver erros, `normalized_text` é retornado para facilitar leitura e depuração.

## Normalização

Modos aceitos:

- `line_min`: reduz linhas, agrupando itens com `|` quando possível;
- `char_min`: reduz caracteres, compactando separadores;
- `min`: alias inicial de `char_min`;
- `human`: modo reservado para renderização humanizada por seção. No momento usa renderização genérica legível.

## API De Baixo Nível

Também existem APIs de baixo nível para desenvolvimento da linguagem:

```python
from medi_evo import compile_medi_evo

compiled = compile_medi_evo(text)
print(compiled.to_json())
```

Para uso em outros projetos, prefira `compile_text` e `compile_json`.

## CLI

O pacote instala o comando `medi-evo`:

```bash
poetry run medi-evo examples/minimal_valid.medi_evo --json compiled.json
```

## Interface Streamlit

Para testar visualmente:

```bash
poetry run streamlit run app_streamlit.py
```

## Testes

```bash
poetry run pytest
```

## Estrutura Do Pacote

```text
medi_evo/
  api.py                 API pública
  normalization.py       renderização/normalização
  models.py              modelos de dados
  minimal/               parser estrutural mínimo
  parser/                gramática Lark
  sections/              parsers específicos de seções clínicas
```

## Seções Clínicas Da Versão 1.0

O registry padrão usado por `compile_text` inclui:

- Informações do paciente
- Diagnóstico
- Medicamentos
- Balanço hídrico
- PRISMIV
- Controles
- Exames laboratoriais
- Exames de imagem
- Intercorrências
- Resumo do caso
- Exame físico
- Aporte
- Conduta
- Plano de cuidado
- Dispositivos
