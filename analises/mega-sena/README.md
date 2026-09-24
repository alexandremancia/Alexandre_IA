# Análise de padrões na Mega-Sena

Três perguntas, três relatórios:

- [`RELATORIO.md`](RELATORIO.md) — **existe padrão nos números?** 26 testes sobre
  frequência, repetição, atraso, soma, paridade, duplas e estratégias de aposta.
- [`RELATORIO-TEMPORAL.md`](RELATORIO-TEMPORAL.md) — **existe padrão por ano,
  semestre ou mês?** 19 testes sobre calendário, sazonalidade e tendência.
- [`RELATORIO-SOMA.md`](RELATORIO-SOMA.md) — **e na soma das dezenas?** 20 testes
  sobre a distribuição da soma, a memória da série e os sistemas de fechamento.

Esta pasta é o material que sustenta os dois — dados, scripts e gráficos — para
que qualquer afirmação possa ser refeita do zero.

## Como reproduzir

```bash
pip install numpy scipy pandas matplotlib

python3 scripts/consolidar_dados.py    # baixa e valida o histórico completo
python3 scripts/analise.py             # testes de padrão nos números (≈15 min)
python3 scripts/analise_temporal.py    # testes de padrão por período (≈8 min)
python3 scripts/analise_soma.py        # testes sobre a soma das dezenas (≈6 min)
python3 scripts/graficos.py            # figuras do relatório principal
python3 scripts/graficos_temporais.py  # figuras do relatório temporal
python3 scripts/graficos_soma.py       # figuras do relatório da soma
```

Os dois scripts de análise aceitam `--sims N`. Com `--sims 2000` rodam em cerca
de um minuto e servem para inspecionar; os p-valores de Monte Carlo ficam com
menos precisão.

## Arquivos

| Caminho | O que é |
|---|---|
| `scripts/consolidar_dados.py` | Baixa quatro fontes públicas, valida as sobreposições entre elas e grava o histórico consolidado |
| `scripts/analise.py` | Testes de padrão nos números. Cada um registra hipótese nula, estatística, p-valor e detalhe |
| `scripts/analise_temporal.py` | Testes de padrão por ano, semestre, mês, dia da semana e data |
| `scripts/analise_soma.py` | Testes sobre a soma das dezenas: forma, memória e utilidade prática |
| `scripts/graficos*.py` | Os gráficos, sempre com a faixa do azar como referência |
| `dados/megasena_consolidado.csv` | Um concurso por linha: número, data, as 6 dezenas e a ordem de sorteio quando conhecida |
| `dados/resultados*.json` | Saída completa das análises, com os detalhes que não cabem nos relatórios |
| `graficos/*.png` | Figuras dos relatórios |

## Sobre os dados

Nenhuma fonte pública isolada cobre o histórico inteiro com datas, então a
consolidação usa quatro e **valida todas as faixas em que elas se sobrepõem**
antes de aceitar qualquer coisa. O script aborta se encontrar divergência nas
dezenas ou nas datas, em vez de seguir com dado suspeito.

| Fonte | Cobertura | Papel |
|---|---|---|
| [guilhermeasn/loteria.json](https://github.com/guilhermeasn/loteria.json) | concursos 1–2797 | dezenas na ordem de sorteio |
| [neliobnjr/megasena](https://github.com/neliobnjr/megasena) | 1–2365 | datas |
| [gnai-creator/gerasena.com](https://github.com/gnai-creator/gerasena.com) | 1–2896 | datas e dezenas |
| [OsJunnior/mega_sena](https://github.com/OsJunnior/mega_sena) | 2551–3056 | única fonte da ponta recente |

Conferência: 2.797 concursos com dezenas idênticas entre a primeira e a terceira
fontes, 2.365 entre a primeira e a segunda, 247 entre a primeira e a quarta, e
346 concursos com datas idênticas entre a terceira e a quarta. Uma única
divergência de data apareceu, e está resolvida abaixo.

### Limitações conhecidas

Ficam registradas porque afetam o que se pode afirmar:

- **Recorte**: concursos 1 a 3056 (11/03/1996 a 10/09/2026). Concursos
  posteriores não entraram porque as fontes usadas não os publicavam quando a
  análise foi feita.
- **Concurso 1754**: duas fontes discordam da data. `neliobnjr` diz 04/10/2015,
  um domingo, quando só havia sorteio às quartas e aos sábados; `gerasena` diz
  24/10/2015, um sábado, coerente com os vizinhos (1753 em 21/10, 1755 em
  28/10). A consolidação adota 24/10/2015.
- **Datas da ponta recente**: a partir do concurso 3033 (julho de 2026) só a
  fonte `OsJunnior` publica as datas, e ela coloca o sorteio de sábado no
  domingo seguinte, mantendo terça e quinta no lugar — quase certamente erro
  dela. Por isso o teste de dia da semana para no concurso 2896. Ano e mês não
  são afetados: um deslize de um dia quase nunca troca o mês.
- **Ordem de sorteio** conhecida só até o concurso 2797. Os testes que usam a
  ordem das bolas se restringem a essa faixa; os demais usam as dezenas
  ordenadas.
- A API oficial da Caixa não era acessível no ambiente onde isto rodou, o que
  motivou o uso de fontes espelhadas com validação cruzada.
