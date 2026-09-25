# AlexandreMancia-instagram: regras desta pasta

> **REGRA ZERO:** se uma orientação não for entendida com clareza, NÃO
> executar nada. Perguntar antes. Não adivinhar a intenção, não escolher o
> caminho mais provável, não começar "pra adiantar" e ajustar depois.
> (definido em 2026-09-05, vale em todos os projetos)

> **REGRA DE EXECUÇÃO:** o trabalho segue o `ROADMAP.md` desta pasta, um
> passo por vez. Termina o passo, marca no roadmap, e só então começa o
> próximo. Nunca abrir dois passos ao mesmo tempo nem pular à frente.

Perfil pessoal `@alexandremancia`, frente de captação da Mancia Solutions.
Contexto completo em `README.md`. Antes de criar qualquer peça, ler
`posicionamento.md` e `producao-sem-rosto.md` desta pasta, mais
`_memoria/preferencias.md`.

## Esta pasta fica de lado, de propósito

Decisão do Alexandre em 2026-09-05: o perfil pessoal é desenvolvido aos
poucos, à margem da operação da empresa, e só depois vai se tocando com o
`@manciasolutions`.

Consequências práticas, a serem respeitadas por qualquer sessão futura:

- **Versionada no git**, para ter backup e histórico como o resto.
- **NÃO listar no `CLAUDE.md` da raiz** nem em `_memoria/empresa.md`,
  `_memoria/estrategia.md` ou na lista de projetos do workspace. Se uma
  sessão futura for "atualizar o contexto", esta pasta fica de fora.
- **Não puxar este projeto para dentro de tarefas da empresa** sem pedido
  explícito. Ele não entra na fila de prioridades da Mancia.
- As pontes com o perfil da marca (Fase 3 do `ROADMAP.md`) só acontecem
  quando o Alexandre disser. Nada nas Fases 0, 1 e 2 depende delas.

## Não confundir com o perfil da marca

`ManciaSolutions-instagram/` é o perfil `@manciasolutions`, da empresa.
Esta pasta é o perfil pessoal. Peça deste perfil nasce aqui, peça da marca
nasce lá. Na dúvida sobre onde uma peça pertence, perguntar antes de criar.

A única exceção é o **post de colaboração**, que sai nos dois feeds ao
mesmo tempo com as duas contas como autoras. Nesse caso a peça mora aqui e
o registro fica nos dois `publicados/metricas.md`.

## Quem fala

Alexandre, em primeira pessoa. "Eu testei", "eu errei nisso", "eu refiz".
O perfil da marca fala como marca; este fala como pessoa. Texto em terceira
pessoa ou em nome da empresa está errado aqui.

Sem rosto em vídeo (decisão de 2026-09-05): voz e gravação de tela. Isso
não é regra permanente, é uma decisão com gatilho de revisão registrado no
passo 18 do roadmap.

## Formato das artes

**Identidade própria, diferente da marca** (decisão de 09/09/2026). Este
perfil não usa a identidade da Mancia Solutions: são dois perfis com papéis
diferentes, e quem vê os dois precisa perceber que são coisas distintas.

- Carrossel e post único: **1080x1080, quadrado**. Máximo 10 slides.
- Story: 1080x1920, margem de segurança de 250px no topo e 320px na base.
- Capa de reel: 1080x1920, com o texto principal dentro do quadrado central.
- **Direção "terminal quente":** fundo quase preto neutro `#0c0c0d`, sem o
  azul-marinho da marca. Acento âmbar `#f5a524`, no lugar do azul elétrico.
- **Tipografia:** IBM Plex Sans nos títulos e no corpo, IBM Plex Mono em
  rótulo, contador, número e rodapé. Nada de Space Grotesk nem Inter, que
  são da marca.
- Importar `biblioteca/templates/base.css` **desta pasta**, nunca o da
  marca, e nunca redefinir cor ou fonte na peça.

Render: `ALTURA=1080 bash ../../../ManciaSolutions-instagram/biblioteca/templates/render.sh carrossel.html instagram`

O rodapé leva `@alexandremancia`, que é a autoria. A ponte para a marca
fica no selo do último slide, com `manciasolutions.com`.

## Tradução: tudo, não só o título

Regra global de 09/09/2026, em `~/.claude/CLAUDE.md`.

Português é a língua principal e o inglês traduz o português, sempre, para
alcançar mais gente. **Todo texto visível é traduzido:** frase de apoio,
parágrafo, item de lista, citação, CTA, rótulo e unidade de número.

O inglês nunca lidera e nunca aparece sozinho: vem logo abaixo do português
correspondente, em `<span class="en" lang="en">`, em corpo menor. O `lang`
não é enfeite, é o que faz o navegador hifenizar pela regra certa.

Peça com inglês em um bloco e sem inglês em outro está errada.

## Escrita

Valem as regras globais do Alexandre:

- **Sem travessão (—) em nada.** Vírgula, dois-pontos ou ponto.
- Primeira linha da legenda carrega o gancho inteiro: o app corta o resto.
- Sem clichê de guru, sem emoji em conteúdo técnico.
- Texto corrido dentro de arte justificado, ocupando a largura inteira do
  bloco. Título, rótulo e CTA à esquerda.

## Vídeo

- Legenda queimada é obrigatória em todo reel e story falado. Sem rosto e
  sem legenda, o vídeo é uma tela muda.
- Os 3 primeiros segundos mostram o resultado, nunca a introdução.
- Um CTA por peça. Pedido duplo não é obedecido.
- Não versionar vídeo bruto aqui. Corte final e roteiro bastam, original
  fica no Drive.

## O que não fazer aqui

- Não publicar tela com nome, logo, conversa ou número de cliente sem
  autorização escrita. Para bastidor, usar produto próprio ou dado
  fictício óbvio.
- Não mandar preço na DM antes de entender a dor.
- Não pedir "segue o @manciasolutions" como CTA principal: queima o clique
  que deveria virar conversa.
- Não postar a mesma peça nos dois perfis no mesmo dia. Ou é post de
  colaboração, ou espaça em três dias.
- Não prometer número que não veio de trabalho medido.
- Não transformar o feed pessoal em feed corporativo. Vida normal continua.

## Depois de publicar

Registrar em `publicados/metricas.md` com data real, formato, link e, uma
semana depois, **quantas conversas a peça gerou**. Alcance e curtida entram
como contexto, não como resultado.
