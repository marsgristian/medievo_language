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

### DIAGNÓSTICO

A seção é obrigatória.

Nomes aceitos:

- `Diagnóstico`
- `Diagnósticos`
- `Hipótese diagnóstica`
- `Hipóteses diagnósticas`

Maiúsculas e minúsculas não importam. Para essa seção, os nomes também são aceitos com ou sem acento.

Os itens devem ser escritos como texto livre, sem `key: value`.

```medievo
# DIAGNOSTICO
R09 Hipoxemia a/e (cissurite em lobo inferior direito)
J98.1 Atelectasia crônica
R13 Disfagia? (precisa de exames para saber ao certo)
```

Cada item pode conter:

- `cid`: opcional, no começo do item, em padrão CID-10 ou CID-11;
- `diagnostico`: obrigatório, formado pelo texto restante depois de remover campos parseáveis;
- `data`: opcional, como data ou período;
- `estado`: opcional, por subseção ou inline.

Estados aceitos:

- `Ativo`: também aceita `ativa` e `atual`; é o padrão quando o estado é omitido;
- `Em tratamento`: também aceita `tratando` e `tratamento`;
- `Tratado`: também aceita `tratada`;
- `Investigação`: também aceita `?` e `investigando`.

Estados podem ser escritos como subseção:

```medievo
> Em tratamento:
J18 Pneumonia nasocomial / bronco aspirativa
```

Ou inline:

```medievo
I90 Derrame pleural a direita- PO drenagem 05/06 em tratamento
R13 Disfagia?
```

Se um item tiver estado por subseção e também estado inline, o estado inline vence e o item gera erro por possuir mais de um estado.

Regras de data:

- diagnósticos `Ativo`, `Em tratamento` ou `Investigação` podem ter data simples, mas não período;
- diagnóstico `Tratado` com data deve usar período;
- diagnóstico `Tratado` com data simples gera warning.

Exemplo:

```medievo
# DIAGNOSTICO
R09 Hipoxemia a/e (cissurite em lobo inferior direito)
J98.1 Atelectasia crônica
R13 Disfagia? (precisa de exames para saber ao certo)
> Em tratamento:
J18 Pneumonia nasocomial / bronco aspirativa
I90 Derrame pleural a direita- PO drenagem 05/06
> Tratado: E87.6 Hipocalemia 01/06-05/06
```

### MEDICAMENTOS

A seção é obrigatória.

Nomes aceitos:

- `Medicamentos`
- `Medicações`
- `Medicacoes`
- `Medicamento`

Se o paciente estiver sem medicamentos, escreva isso no valor da seção:

```medievo
# MEDICAMENTOS: sem medicamentos
```

Uma seção vazia sem esse marcador explícito gera warning.

Os itens devem usar `key: value`. A key é o nome do medicamento.

```medievo
Clonidina: 3 mcg/kg/dose; 6/6h; Di 09/06
Dipirona: 14 mg/kg/dose; ACM; se dor ou febre
Simeticona: 7 gotas; 6/6
```

Cada item pode conter:

- `dose`: opcional, reconhecida como número seguido de unidade;
- `intervalo`: opcional, em formatos como `6/6h`, `6/6`, `2x/dia` ou `1/dia`;
- `data`: opcional, como data ou período; `Di` antes da data é aceito, mas não obrigatório;
- `extras`: todo valor que não for dose, intervalo, data ou estado.

Via, `ACM`, `SN`, `se necessário`, diluições e observações devem ficar em `extras`.

Estados aceitos:

- `Ativo`: também aceita `ativa` e `atual`; é o padrão quando o estado é omitido;
- `Suspenso`: também aceita `fez uso`, `anterior` e `inativo`.

Estados podem ser escritos como subseção:

```medievo
> Suspenso:
Lorazepam: 0,1 mg/kg/dose; 4/4h; 04/06-12/06
```

Ou inline:

```medievo
Metadona: 0,15 mg/kg/dose; 4/4h; anterior; 04/06-12/06
```

Se um item tiver estado por subseção e também estado inline, o estado inline vence e o item gera erro por possuir mais de um estado.

Regras:

- texto livre na seção gera erro;
- medicamento sem intervalo e sem extras gera warning;
- medicamento suspenso deve ter período de uso;
- medicamento suspenso sem data gera erro;
- medicamento suspenso com data simples gera warning;
- medicamento suspenso com período fica válido.

Exemplo:

```medievo
# MEDICAMENTOS
Clonidina: 3 mcg/kg/dose; 6/6h; Di 09/06; VS
Furosemida: 1 mg/kg/dose; 12/12h; ACM
Dipirona: 14 mg/kg/dose; ACM; se dor ou febre
> Suspenso:
Lorazepam: 0,1 mg/kg/dose; 4/4h; 04/06-12/06
```

### BALANÇO HÍDRICO

A seção é obrigatória.

Nomes aceitos:

- `Balanço hídrico`
- `Balanco hidrico`

Os itens devem usar `key: value`.

Itens obrigatórios:

- `Entradas`
- `Saídas`
- `BH`
- `Diurese`

O `BH` pode vir como valor da seção:

```medievo
# BALANÇO HÍDRICO: +369,40 ml
Entradas: 897,4 ml | Saídas: 528 ml | Diurese: 2,98 ml/kg/h
```

Ou como item:

```medievo
# BALANÇO HÍDRICO
Entradas: 897,4 ml | Saídas: 528 ml | BH: +369,40 ml | Diurese: 2,98 ml/kg/h
```

Outros itens `key: value` são permitidos.

```medievo
Evacuações: 2 ml | Vômitos: 30 ml
```

Valores aceitam `ml` e `ml/kg/h`.

Regras:

- `BH` diferente de zero deve ter sinal `+` ou `-`;
- `BH` igual a zero pode ser escrito sem sinal;
- se `Entradas` e `Saídas` existirem, mas `BH` não vier, o sistema gera warning e calcula automaticamente;
- se `Entradas` e `Saídas` tiverem unidades diferentes, o sistema gera warning e não calcula o `BH`;
- quando `BH` vier informado, a unidade deve ser a mesma de `Entradas` e `Saídas`;
- `BH` informado deve bater com `Entradas - Saídas`;
- a comparação usa precisão de uma casa decimal;
- se o cálculo discrepar, gera erro: `BH discrepante do cálculo, por favor verifique os valores de entradas e saídas`.

Exemplo com cálculo automático:

```medievo
# BALANÇO HÍDRICO
Entradas: 100 ml | Saídas: 40 ml | Diurese: 2 ml/kg/h
```

Nesse caso, o `BH` calculado é `+60 ml`.

### PRISMIV

A seção é obrigatória e deve conter valor percentual no cabeçalho.

```medievo
# PRISMIV: 90%
```

Se o valor da seção estiver vazio, gera erro com a mensagem `por favor calcule o prism`.

O item `PRISMIII` é opcional. Quando vier, deve conter os campos `Neurológico` e `Não Neurológico`.

```medievo
# PRISMIV: 90%
PRISMIII: Neurológico: 90; Não Neurológico: 90
```

A seção não aceita outros itens.

### CONTROLES

A seção é obrigatória.

Nomes aceitos:

- `Controles`
- `Sinais vitais`

Os itens devem usar `key: value`, e qualquer chave é aceita se o valor seguir um dos formatos abaixo.

Controle numérico:

```medievo
FC: 59-180 bpm
FR: 25-59 irpm
Tax: 36,5-39,2°C
```

O controle numérico tem medição mínima, medição máxima e unidade. A unidade é recomendada; se não vier, gera warning. Pode ter período associado; se não vier, assume-se o período das últimas 24h.

Controle básico:

```medievo
HGT: 99 mg/dL 16/06
Glasgow: 15 16/06
```

O controle básico tem uma medição e data obrigatória. A unidade é recomendada; se não vier, gera warning.

Controle textual:

```medievo
Dist. resp: N 16/06
```

Controle textual também deve ter data.

Exemplo:

```medievo
# CONTROLES
FC: 59-180 bpm | FR: 25-59 irpm | Tax: 36,5-39,2°C
PAS: 77-137 mmHg | PAD: 45-101 mmHg | PAM: 55-113 mmHg
HGT: 99-99 mg/dL
Dist. resp: N 16/06
```
