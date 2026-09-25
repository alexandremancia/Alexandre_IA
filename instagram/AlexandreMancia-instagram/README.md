# AlexandreMancia-instagram

Perfil **pessoal** do Alexandre no Instagram, `@alexandremancia`, usado
como frente de captação de clientes para a Mancia Solutions.

Projeto próprio, separado de `ManciaSolutions-instagram/`, que é a
operação do perfil da marca (`@manciasolutions`). São dois perfis, dois
públicos e duas rotinas: misturar as pastas confunde a produção e faz um
conteúdo vazar no feed errado.

## Por que dois perfis

Não é vaidade nem trabalho dobrado. Cada um resolve um problema diferente:

| | @alexandremancia | @manciasolutions |
|---|---|---|
| Papel | captar, aquecer, gerar conversa | provar que a empresa existe e é séria |
| Audiência | ~1.000 contas reais (de 4.503 declarados), 420 a 990 decisores | quem chega pelo site, proposta ou busca |
| Quem fala | Alexandre, em primeira pessoa | a marca |
| Métrica | conversas iniciadas por semana | consistência do feed, credibilidade |
| Ritmo | 3 peças por semana + stories | conforme a fila do calendário de lá |
| Pasta | esta | `ManciaSolutions-instagram/` |

A regra que amarra os dois: **quem está pronto pra contratar vai pro
WhatsApp, não pro outro perfil.** Cada clique a mais derruba metade das
pessoas. O `@manciasolutions` é destino de quem quer conferir, não de quem
quer contratar.

## Decisões já tomadas

- **Sem rosto em vídeo, por enquanto.** Voz e gravação de tela. Método em
  `producao-sem-rosto.md`, com gatilho de revisão em 8 semanas.
- **Sem pressa.** O roadmap é sequencial e os 5 primeiros passos acontecem
  sem nada público, para o perfil já estar certo quando o primeiro post
  sair.
- **A métrica é conversa iniciada por semana**, não seguidor.

## Estrutura

```
AlexandreMancia-instagram/
├── CLAUDE.md                regras desta pasta
├── README.md                este arquivo
├── ROADMAP.md               18 passos numerados, um por vez
├── posicionamento.md        para quem, promessa, bio, pilares, o que não se publica
├── producao-sem-rosto.md    método de gravação com voz e tela
├── audiencia.md             quem são os seguidores: resultado do passo 1
├── posts/                   carrossel e imagem única
│   └── AAAA-MM-DD-slug/
├── reels/
│   └── AAAA-MM-DD-slug/
├── stories/
│   └── AAAA-MM-DD-slug/
└── publicados/
    └── metricas.md          o que foi ao ar, quando, e quantas conversas gerou
```

O formato de cada peça (briefing, texto, arte, legenda, render) segue o
mesmo padrão de `ManciaSolutions-instagram/README.md`. O que muda aqui é o
perfil, o tom em primeira pessoa e o objetivo de cada peça.

## Relação com o resto do workspace

- **Identidade visual:** a mesma do site e do perfil da marca, de
  propósito. É uma das três pontes entre os perfis. Referência em
  `ManciaSolutions-instagram/biblioteca/identidade-instagram.md` e em
  `identidade/design-guide.md`.
- **Tom de voz:** `_memoria/preferencias.md`, ajustado para primeira pessoa
  em `posicionamento.md`.
- **Diagnóstico gratuito:** a matéria-prima vem do FindLeadsNow
  (`ManciaSolutions-leads/`).
- **Demonstração de produto:** depende do Atendimento IA
  (`ManciaSolutions-atendimento/`), desenvolvido em outro chat.

## Estado

Fase 0 do roadmap, nada publicado.

**Passo 1 concluído em 05/09/2026.** 4.503 seguidores, 22% decisores
(cenário 1: a varredura da rede é prioridade absoluta), 48% contas fake
concentradas no miolo da lista. Revisão pelo raio-x: ~3.500 são bots, base real ~1.000. Detalhes e a decisão de
não limpar os fakes em `audiencia.md`.

**Próximo passo: 2, curadoria do feed atual.**
