# Manual de escrita medievo mínimo

Este manual descreve a versão mínima da linguagem medievo. A proposta é permitir escrita clínica natural, mas com estrutura suficiente para compilar o texto em JSON/Python object.

## 1. Estrutura geral

Um documento é composto por seções, subseções e itens.

```medievo
# NOME DA SEÇÃO: valor opcional (valor comentado opcional)
item 1 | item 2
> Nome da subseção:
item 3
```

## 2. Seções

Seção começa com `#`.

```medievo
# EXAMES:
# EXAMES: laboratoriais
# EXAMES: laboratoriais (últimas 24h)
```

A linha da seção só pode conter:

```text
# section_name: section_value
```

`section_value` é opcional.

### Válido

```medievo
# MEDICAMENTOS:
# EXAMES: laboratoriais
```

### Inválido

```medievo
# MEDICAMENTOS > Antibiótico:
# CONTROLES: FC: 100 | FR: 20
#
```

Motivo:

- subseções precisam estar em linha própria;
- itens precisam ficar nas linhas abaixo da seção;
- seção precisa ter nome.

## 3. Subseções

Subseção começa com `>` e precisa ter `:`.

```medievo
> Prévio:
> Suspenso:
> Antibiótico:
```

Itens podem vir na mesma linha da subseção.

```medievo
> Prévio: Hb: 10 | PCR: 20
```

Os itens dessa linha recebem `state = "Prévio"`.

### Válido

```medievo
> Prévio:
> Prévio: Hb: 10
```

### Inválido

```medievo
> Prévio
>:
```

## 4. Itens

Itens podem ser texto livre ou `key: value`.

### Texto livre

```medievo
Paciente em bom estado geral
Sem intercorrências no período
```

Resultado: `key = None`, `values = [texto]`.

### Key-value

```medievo
Hb: 10,2
FC: 104-137 bpm
Dipirona: se febre
```

Resultado: `key` recebe o texto antes do primeiro `:` estrutural; `values` recebe o texto depois.

### Key vazia é inválida

```medievo
: value
```

### Value vazio é inválido

```medievo
key:
key : |
key : ;
```

## 5. Separadores

### Separador universal de itens: `|`

```medievo
FC: 104-137 bpm | FR: 26-34 irpm | Tax: 36,5°C
```

Gera três itens.

### Separador de values: `;`

```medievo
Hb: 10,2; Leuco: 12000; Plaquetas: 250000
```

Quando um value contém outro `key: value`, ele vira `children`.

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

## 6. Datas

A linguagem reconhece datas em qualquer posição do item.

### Formatos aceitos

```text
dd/mm/aaaa hh:mm
dd/mm/aaaa
dd/mm
(dd/mm)
```

Exemplos:

```medievo
10/06 Hb: 10
Hb: 10; 10/06
(10/06) Sem intercorrências
10/06: melhora clínica
```

No caso abaixo, `key` e `date` são a mesma coisa:

```medievo
10/06: melhora clínica
```

Resultado conceitual:

```python
key = "10/06"
date = ClinicalDate(...)
values = ["melhora clínica"]
```

## 7. Regra de ano implícito

O cabeçalho deve conter uma data completa para servir como referência.

```medievo
EVOLUÇÃO - DIURNA - 16/06/2026 10:30
```

Depois disso, os itens podem usar `dd/mm` sem ano.

Regra:

- usa o ano do cabeçalho;
- se a data ainda não ocorreu naquele ano em relação à data do cabeçalho, assume o ano anterior.

Exemplo com cabeçalho `16/06/2026`:

```text
10/06 -> 10/06/2026
20/06 -> 20/06/2025
```

## 8. Períodos de data

Formatos aceitos:

```text
DATA-DATA
dd-DATA
```

Exemplos:

```medievo
SVD: 10/06-12/06
SVD: 10-12/06
Antibiótico: 31/05/2026-03/06/2026
```

O parser gera `ClinicalDatePeriod` com:

```python
start: ClinicalDate
end: ClinicalDate
delta_time: timedelta
```

## 9. Valores entre parênteses

Parênteses não são comentário ignorado. Eles viram `commented_values`.

```medievo
Dipirona: se febre (T > 37,8°C)
```

Resultado conceitual:

```python
ClinicalValue(
    value="se febre",
    commented_values=["T > 37,8°C"],
)
```

Isso evita perder informação clínica importante.

## 10. Comentários ignoráveis

Comentários que o sistema deve ignorar usam `/* */`.

```medievo
FC: 120 /* valor duvidoso, não renderizar */
```

O conteúdo não entra como value clínico, mas fica preservado em `ignored_comments`.

## 11. States inline

A linguagem mínima não reconhece state inline por padrão.

```medievo
Prévio Hb: 10
```

Isso só vira `state="Prévio"` se uma seção específica registrada declarar `Prévio` como state inline.

Subseções sempre geram state estrutural:

```medievo
> Prévio:
Hb: 10
```

Nesse caso, o item recebe `state="Prévio"` mesmo sem parser específico.

## 12. Regras de seções específicas

Além da estrutura mínima da linguagem, algumas seções possuem regras próprias de escrita e validação.

### INFORMAÇÕES DO PACIENTE

A seção é obrigatória e deve conter itens em formato `key: value`.

Itens obrigatórios:

- `Nome`
- `Idade`
- `Data internacao`
- `Sexo`
- `Peso`

Chaves desconhecidas são permitidas nessa seção. Use-as quando houver uma informação relevante do paciente que ainda não tenha campo estruturado específico.

O peso deve conter um número parseável em formato pt-BR.

```medievo
Peso: 56,987 kg
```

Sempre que possível, escreva a data de medição junto do peso.

```medievo
Peso: 16/06 56,987 kg
Peso: 16/06/2026 56,987 kg
```

Regras do peso:

- peso medido exatamente 7 dias antes da evolução, ou há mais tempo, gera erro;
- peso sem data gera warning;
- quando o peso não tem data associada, assume-se que foi medido na data da evolução.

Exemplo completo:

```medievo
# INFORMACOES DO PACIENTE
Nome: Maria Silva
Idade: 2 anos 3 meses
Data internacao: 10/06/2026
Sexo: feminino
Peso: 16/06 56,987 kg
Leito: 123
```
