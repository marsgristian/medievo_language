# Manual de escrita - Medi Evo language

Este manual descreve como escrever uma evolução médica no padrão Medi Evo language.

A ideia é manter uma escrita próxima da rotina clínica, mas com marcações simples para que o texto possa ser validado e reutilizado por outros sistemas.

## Regras gerais

Cada seção começa com `#`.

```text
# NOME DA SEÇÃO
```

Itens podem ser escritos em linhas separadas ou na mesma linha usando `|`.

```text
FC: 80-120 bpm | FR: 20-30 irpm
```

Quando um item tem nome e valor, use `:`.

```text
Peso: 10 kg
```

Subseções começam com `>`.

```text
> Suspenso:
Metadona: 0,15 mg/kg/dose; 04/06-12/06
```

Datas aceitas:

```text
10/06
10/06/2026
10/06 10:00
10/06-12/06
```

## Seções obrigatórias

Todas as seções abaixo devem aparecer na evolução.

## Informações do paciente

Nomes aceitos: `INFORMAÇÕES DO PACIENTE`, `INFORMACOES DO PACIENTE`, `DADOS DO PACIENTE`, `IDENTIFICAÇÃO`.

Itens obrigatórios:

- Nome
- Idade
- Data da internação
- Sexo
- Peso

Exemplo:

```text
# INFORMACOES DO PACIENTE
Nome: Maria Silva
Idade: 2 anos 3 meses
Data internacao: 10/06/2026
Sexo: feminino
Peso: 16/06 10 kg
```

O peso deve ter data sempre que possível. Peso sem data gera aviso e será interpretado como medido na data da evolução. Peso medido há 7 dias ou mais gera erro.

## Diagnóstico

Nomes aceitos: `DIAGNÓSTICO`, `DIAGNOSTICO`, `DIAGNÓSTICOS`, `DIAGNOSTICOS`, `HIPÓTESE DIAGNÓSTICA`, `HIPOTESE DIAGNOSTICA`, `HIPÓTESES DIAGNÓSTICAS`, `HIPOTESES DIAGNOSTICAS`.

Escreva um diagnóstico por item. O CID é opcional.

Estados aceitos:

- Ativo: padrão quando nada for informado
- Em tratamento
- Tratado
- Investigação: pode ser marcado com `?`

Exemplo:

```text
# DIAGNOSTICO
R09 Hipoxemia
R13 Disfagia?
> Em tratamento:
J18 Pneumonia nasocomial
> Tratado:
E87.6 Hipocalemia 01/06-05/06
```

Diagnóstico tratado com data deve usar período. Diagnóstico ativo, em tratamento ou em investigação não deve usar período.

## Medicamentos

Nomes aceitos: `MEDICAMENTOS`, `MEDICAÇÕES`, `MEDICACOES`, `MEDICAMENTO`.

Se não houver medicamentos:

```text
# MEDICAMENTOS: sem medicamentos
```

Formato:

```text
Nome do medicamento: dose; intervalo; outras informações; data
```

Exemplo:

```text
# MEDICAMENTOS
Clonidina: 3 mcg/kg/dose; 6/6h; Di 09/06; VS
Dipirona: 14 mg/kg/dose; ACM; se dor ou febre
> Suspenso:
Lorazepam: 0,1 mg/kg/dose; 4/4h; 04/06-12/06
```

Medicamento suspenso deve ter período de uso. Se tiver apenas uma data, gera aviso. Se não tiver data, gera erro.

## Balanço hídrico

Nomes aceitos: `BALANÇO HÍDRICO`, `BALANCO HIDRICO`.

Itens obrigatórios:

- Entradas
- Saídas
- BH
- Diurese

O BH pode vir no título da seção:

```text
# BALANCO HIDRICO: +369,4 ml
Entradas: 897,4 ml | Saidas: 528 ml | Diurese: 2,98 ml/kg/h
```

Ou como item:

```text
# BALANCO HIDRICO
Entradas: 897,4 ml | Saidas: 528 ml | BH: +369,4 ml | Diurese: 2,98 ml/kg/h
```

O BH deve ter sinal `+` ou `-`, exceto quando for zero. Se o BH estiver ausente, o sistema tenta calcular usando `Entradas - Saídas`.

## PRISMIV

A seção deve ter valor percentual.

```text
# PRISMIV: 90%
```

O item `PRISMIII` é opcional. Se aparecer, deve conter `Neurológico` e `Não Neurológico`.

```text
# PRISMIV: 90%
PRISMIII: Neurologico: 90; Nao Neurologico: 90
```

## Controles

Nomes aceitos: `CONTROLES`, `SINAIS VITAIS`.

Aceita qualquer chave, desde que o valor siga um destes formatos.

Controle com mínimo e máximo:

```text
FC: 59-180 bpm
FR: 25-59 irpm
Tax: 36,5-39,2 C
```

Controle simples com data:

```text
HGT: 99 mg/dL 16/06
Glasgow: 15 16/06
Dist. resp: N 16/06
```

Controles simples e textuais devem ter data. Unidade ausente gera aviso, porque em alguns casos a unidade é subentendida.

## Exames laboratoriais

Nomes aceitos: `EXAMES LABORATORIAIS`, `EXAME LABORATORIAL`, `EXAMES`, `EXAME COMPLEMENTAR`.

Cada item deve estar associado a uma data.

```text
# EXAMES
10/06: Hb 10,2 Leuco 12000 Plaquetas 250000
```

Também é possível usar a data como subseção. Nesse caso, cada item deve começar com horário.

```text
# EXAMES
> 10/06:
10:00: Hb 10,2 Leuco 12000
```

## Exames de imagem

Nomes aceitos: `EXAMES DE IMAGEM`, `EXAME DE IMAGEM`.

Segue a mesma regra de data dos exames laboratoriais.

```text
# EXAMES DE IMAGEM
10/06: RX torax sem consolidacoes
```

## Intercorrências

Nomes aceitos: `INTERCORRÊNCIAS`, `INTERCORRENCIAS`, `INTERCORRENCIA`, `EVOLUCAO`, `EVOLUÇÃO`.

Cada item deve ter data.

```text
# INTERCORRENCIAS
10/06: Sem intercorrencias
```

Ou:

```text
# INTERCORRENCIAS
> 10/06:
10:00: Sem intercorrencias
```

## Seções livres

As seções abaixo aceitam texto livre, itens com `chave: valor` e subseções.

- `RESUMO DO CASO`, também aceita `HMA` e `HISTORIA DA MOLESTIA ATUAL`
- `EXAME FÍSICO`, também aceita `EXAME FISICO`
- `APORTE`, também aceita `DIETA`
- `CONDUTA`, também aceita `CONDUTAS`
- `PLANO DE CUIDADO`
- `DISPOSITIVOS`

Exemplos:

```text
# RESUMO DO CASO
Paciente em acompanhamento por desconforto respiratorio.

# EXAME FISICO
BEG
AR: MV presente bilateralmente

# APORTE
Dieta enteral plena

# CONDUTA
Manter medidas atuais

# PLANO DE CUIDADO
Reavaliar exames

# DISPOSITIVOS
SNE: posicionada
```

Se uma dessas seções existir vazia, o sistema gera aviso.
