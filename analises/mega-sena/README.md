# Análise de padrões na Mega-Sena

Pergunta: **existe algum padrão nos números da Mega-Sena?**

O conteúdo está em [`RELATORIO.md`](RELATORIO.md). Esta pasta é o material que
sustenta o relatório — dados, scripts e gráficos — para que qualquer afirmação
lá possa ser refeita do zero.

## Como reproduzir

```bash
pip install numpy scipy pandas matplotlib

python3 scripts/consolidar_dados.py   # baixa e valida o histórico completo
python3 scripts/analise.py            # roda os testes (≈15 min com 20.000 simulações)
python3 scripts/graficos.py           # gera os gráficos do relatório
```

`analise.py --sims 2000` roda em cerca de 1 minuto e serve para inspecionar; os
p-valores de Monte Carlo ficam com menos precisão.

## Arquivos

| Caminho | O que é |
|---|---|
| `scripts/consolidar_dados.py` | Baixa três fontes públicas, valida a sobreposição entre elas e grava o histórico consolidado |
| `scripts/analise.py` | Os testes estatísticos. Cada um registra hipótese nula, estatística, p-valor e detalhe |
| `scripts/graficos.py` | Os gráficos, sempre com a faixa do azar desenhada como referência |
| `dados/megasena_consolidado.csv` | Um concurso por linha: número, data, as 6 dezenas e a ordem de sorteio quando conhecida |
| `dados/resultados.json` | Saída completa da análise, incluindo os detalhes que não cabem no relatório |
| `graficos/*.png` | Figuras do relatório |

## Sobre os dados

Nenhuma fonte pública isolada cobre o histórico inteiro, então a consolidação
usa três e **valida as faixas em que elas se sobrepõem** antes de aceitar
qualquer coisa:

- [guilhermeasn/loteria.json](https://github.com/guilhermeasn/loteria.json) — concursos 1 a 2797, dezenas na ordem de sorteio.
- [neliobnjr/megasena](https://github.com/neliobnjr/megasena) — concursos 1 a 2365, com datas.
- [OsJunnior/mega_sena](https://github.com/OsJunnior/mega_sena) — concursos 2551 a 3056, com datas.

2.612 concursos aparecem em mais de uma fonte e as dezenas batem em todos —
zero divergência. O script aborta se encontrar qualquer discordância, em vez de
seguir com dado suspeito.

Limitações conhecidas, que ficam registradas porque afetam o que se pode afirmar:

- **Recorte**: concursos 1 a 3056 (11/03/1996 a 10/09/2026). Concursos posteriores
  não entraram porque as fontes usadas não os publicavam quando a análise foi feita.
- **185 concursos sem data** (2366 a 2550). Não afeta nenhum teste do relatório,
  que são todos baseados na sequência de concursos, não no calendário.
- **Ordem de sorteio** conhecida só até o concurso 2797. Os testes que usam a
  ordem das bolas se restringem a essa faixa; os demais usam as dezenas ordenadas.
- A API oficial da Caixa não era acessível no ambiente onde isto rodou, o que
  motivou o uso de fontes espelhadas com validação cruzada.
