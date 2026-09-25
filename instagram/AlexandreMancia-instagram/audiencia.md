# Audiência do @alexandremancia

> Passo 1 do `ROADMAP.md`. **Concluído em 05/09/2026.**

**Seguidores exibidos no perfil:** 4.503 · **contas reais: ~1.000** (ver revisão abaixo)
**Você segue:** ~750
**Amostra:** 50 perfis, em 5 blocos de 10 (topo, ~25%, ~50%, ~75%, fim)
**Método:** bio e atividade conferidas perfil a perfil

---

## Resultado

| Categoria | Amostra | % | Projeção sobre 4.503 |
|---|---|---|---|
| Decisor | 11 | 22% | ~991 |
| CLT | 2 | 4% | ~180 |
| Pessoal | 7 | 14% | ~631 |
| **Morto** | **24** | **48%** | **~2.162** |
| Indefinido | 6 | 12% | ~540 |

**Cenário 1: base comercial.** 22% está acima da régua de 20%, então a
varredura manual da rede (passo 7) é prioridade absoluta.

Com amostra de 50, a margem de erro é de cerca de 11 pontos para mais ou
para menos: o intervalo honesto vai de 10,5% a 33,5%, ou seja, entre 470 e
1.500 decisores. Isso **não muda a decisão**, porque em qualquer ponto desse
intervalo sobra gente muito além das 30 pessoas que o passo 7 alcança.

Esta tabela projeta sobre os 4.503 exibidos. A leitura sobre a base real,
que é a que vale para planejar, está na revisão mais abaixo.

Indefinidos ficaram em 6, abaixo do limite de 15, então o número vale
direto, sem faixa.

---

## A descoberta que vale mais que o percentual

Os decisores não estão espalhados. Estão concentrados nas duas pontas da
lista, e o meio é lixo.

| Bloco | Decisor | CLT | Pessoal | Morto | Indefinido | % decisor |
|---|---|---|---|---|---|---|
| Topo (mais recentes) | 4 | 1 | 4 | 1 | 0 | **40%** |
| ~25% | 1 | 0 | 1 | 7 | 0 | 10% |
| ~50% | 0 | 0 | 1 | 8 | 1 | **0%** |
| ~75% | 1 | 0 | 1 | 6 | 2 | 10% |
| Fim (mais antigos) | 5 | 1 | 0 | 1 | 3 | **50%** |

Agrupando:

- **Zona limpa** (topo + fim, cerca de metade da lista): 9 decisores em 20,
  ou **45%**. Só 2 mortos em 20.
- **Zona contaminada** (os três blocos do meio): 2 decisores em 30, ou 6,7%.
  **21 mortos em 30, ou 70%.**

### O que é a zona contaminada

Contas fake. As mesmas se repetiram dezenas de vezes nas sugestões
(`erinp999`, `manderz41288`, `apriltimm123`, `528lms`, `jomama1955` e
parecidas): sem posts, poucos seguidores, seguindo entre 400 e 1.500,
nomes em inglês sem nenhuma relação com o público brasileiro.

É assinatura de compra de seguidores ou de serviço de crescimento
automatizado. Como a lista é ordenada por data, e a contaminação está
confinada ao miolo, **o problema é histórico e já parou.** A entrada
recente (bloco do topo) é limpa e de qualidade alta.

### A leitura correta da base, revisada em 05/09/2026

A amostra de 50 apontou 48% de contas mortas. A varredura do raio-x sobre a
**lista inteira** apontou bem mais: cerca de 3.500 bots, restando **~1.000
contas reais**. Os dois números vieram de métodos diferentes, e o segundo
olha a população toda em vez de 50 perfis, então é ele que vale.

A diferença tem explicação: parte do que foi classificado como "pessoal" ou
"indefinido" nos blocos do meio provavelmente também é bot, só que menos
óbvio perfil a perfil do que quando se vê a lista inteira de uma vez.

| | |
|---|---|
| Seguidores exibidos no perfil | 4.503 |
| Bots (raio-x) | ~3.500, ou 78% |
| **Contas reais** | **~1.000** |
| Você segue | ~750 |
| Decisores entre as contas reais | **entre 420 e 990** |

**Por que a faixa de decisores é larga, e por que isso não atrapalha.** Os
11 decisores da amostra foram identificados positivamente, um a um, o que
projeta ~990 sobre a lista inteira. Já a densidade de decisores entre as
contas vivas da amostra (42%) aplicada às 1.000 reais projeta ~420. Os dois
métodos discordam por 2x, e não dá para resolver isso sem classificar mais
perfis. Não precisa: **em qualquer ponto dessa faixa a decisão é a mesma**,
porque o passo 7 alcança 30 pessoas por rodada.

Medida contra a base real, a densidade de decisores é de no mínimo 42%.
Isso confirma o cenário 1 com folga.

**Toda projeção de alcance e de engajamento usa 1.000 como base, nunca
4.503.** Um post que alcança 200 contas e leva 25 curtidas está indo
normal, não mal. Sem esse ajuste, você mata um plano que está funcionando
achando que fracassou na segunda semana.

---

## O que isso muda no roadmap

1. **Passo 7 ganha endereço.** As 30 pessoas saem do **topo e do fim da
   lista**, nunca do meio. Na zona limpa, quase 1 em cada 2 é decisor; no
   meio, 7 em cada 10 são bots. Isso derruba o trabalho de olhar ~140
   perfis para ~65.
2. **Nenhuma limpeza de fake antes da varredura.** Ver a decisão registrada
   no fim deste arquivo.
3. **As ~1.000 contas reais viram o denominador** de tudo em
   `publicados/metricas.md`, nunca os 4.503 exibidos.

---

## Decisão: não limpar os fakes agora

Registrado em 05/09/2026, com motivo, para não ser reaberto por impulso.

**Por que não:**

- **Não está no caminho do primeiro cliente.** A varredura mira 30 pessoas
  escolhidas a dedo. Bot não atrapalha quem não vai receber mensagem.
- **Não existe remoção em massa nativa.** O Instagram remove seguidor um a
  um. São ~3.500 contas: inviável na mão.
- **Toda ferramenta que promete fazer isso em lote pede senha ou token.** É
  o jeito mais comum de perder a conta, e ação em massa ainda pega bloqueio.
  Vale a mesma regra que já vale para os apps de "quem não te segue".

**O custo real dos fakes é de percepção, e com 78% ele é sério:** 4.503
seguidores com 25 curtidas por post lê como conta comprada para qualquer
cliente que abrir seu perfil antes de responder uma proposta. Não dá para
esconder isso, e nem adianta tentar.

O que resolve, sem tocar na lista: **nunca usar o número de seguidores como
argumento**, em lugar nenhum. Não citar em proposta, não citar em bio, não
tratar como prova. A prova da Mancia é cliente entregue e produto rodando,
não audiência. Se um cliente comentar o descompasso, a resposta honesta é
curta: perfil antigo, serviço de crescimento que trouxe conta falsa, o que
vale é quem conversa.

**Quando reabrir a decisão:**

- Se você quiser rodar anúncio com público semelhante baseado nos
  seguidores, aí a base suja atrapalha de verdade.
- Se, depois de 8 semanas publicando, o engajamento continuar visivelmente
  constrangedor em relação ao número de seguidores.
- Se aparecerem seguidores fake **novos**, o que indicaria que algo ainda
  está rodando. Hoje não há sinal disso.

---

## Respostas da varredura da rede (passo 7)

Preenchido depois das 30 mensagens.

| Pessoa | Data | Respondeu | Interesse próprio | Ofereceu indicação | Próxima ação |
|---|---|---|---|---|---|
| | | | | | |
