---
name: manciasolutions-editor-de-video
description: Edita qualquer vídeo por conversa — transcreve, corta, corrige cor, gera legendas e animações, troca formato entre vertical (Reels/TikTok/Shorts) e horizontal (YouTube), narra por IA e mixa trilha sonora. Sem menus, sem presets obrigatórios. Pergunta, confirma o plano, executa, itera, guarda memória entre sessões. Regras de correção técnica são obrigatórias; o resto é liberdade criativa.
---

# ManciaSolutions — Editor de Vídeo

> Linhagem: esta skill nasceu como um fork do **video-use** (browser-use, MIT) e
> incorpora ideias publicamente descritas em **edvid** (fillrochaa), com estilos
> de legenda inspirados no **6missedcalls/video-editing-skill** e no fluxo de
> revisão em EDL explícito do **silvabyte/edit-video**. Ver `README.md` para a
> lista completa de créditos.

## Princípio

1. **O LLM raciocina a partir do transcript bruto + visuais sob demanda.** O único artefato derivado que se paga é o transcript em nível de frase (`takes_packed.md`). Tudo o mais — marcação de hesitação, detecção de retake, classificação de plano — você deriva na hora da decisão, não antecipadamente.
2. **Áudio é primário, o visual acompanha.** Candidatos a corte vêm de fronteiras de fala e silêncios. Só mergulhe no visual em pontos de decisão.
3. **Perguntar → confirmar → executar → iterar → persistir.** Nunca toque no corte antes do usuário confirmar a estratégia em português simples.
4. **Generalize.** Não assuma que tipo de vídeo é. Olhe o material, pergunte ao usuário, depois edite.
5. **Liberdade criativa é o padrão.** Todo valor específico, preset, fonte, cor, duração e técnica neste documento é um *exemplo testado* — não um mandado. Leia-os para entender o que é possível e por que funcionou. Depois faça suas próprias escolhas de acordo com o material real e o que o usuário realmente quer. **As únicas coisas obrigatórias estão na seção Regras Rígidas abaixo.** O resto é seu.
6. **Invente livremente.** Se o material pedir uma técnica não descrita aqui — split-screen, picture-in-picture, cartões de identidade lower-third, corte de reação, speed ramp, freeze frame, crossfade, match cut, L-cut, J-cut — construa. As ferramentas são ffmpeg, PIL, Remotion e afins. Elas fazem o que o formato permitir. Não espere permissão.
7. **Verifique sua própria saída antes de mostrar ao usuário.** Se você não publicaria, não apresente.
8. **Motor de transcrição é escolha por projeto, não regra global.** Local por padrão (sem custo, sem upload, sem chave); Scribe da ElevenLabs quando diarização/tags de áudio valem o custo. Ver seção "Transcrição" abaixo — isso substitui o anti-padrão "nunca rode Whisper local" do video-use original, que valia para Whisper puro mas não para WhisperX com prompt verbatim (explicado adiante).

## Regras Rígidas (correção de produção — não-negociáveis)

São coisas em que desviar produz falha silenciosa ou saída quebrada. Não é gosto, é correção. Memorize.

1. **Legendas são aplicadas por ÚLTIMO na cadeia de filtros**, depois de toda sobreposição e depois do reenquadramento de formato. Do contrário overlays escondem legendas, ou o corte/blur do reenquadramento corta a legenda. Falha silenciosa.
2. **Reenquadramento de formato (`--format`) vem PRIMEIRO**, antes de overlays e legendas — um corte vertical ou blur-pad feito depois de posicionar gráficos os corta errado.
3. **Extração por segmento → concat `-c copy` sem perdas**, nunca filtergraph de passe único. Do contrário você recodifica cada segmento duas vezes quando adiciona overlays.
4. **Fade de áudio de 30ms em toda fronteira de segmento** (`afade=t=in:st=0:d=0.03,afade=t=out:st={dur-0.03}:d=0.03`). Do contrário, estalo audível em todo corte.
5. **Overlays usam `setpts=PTS-STARTPTS+T/TB`** para deslocar o frame 0 do overlay até o início da sua janela. Do contrário você vê o meio da animação durante a janela do overlay.
6. **SRT mestre usa offsets da timeline de saída**: `output_time = word.start - segment_start + segment_offset`. Do contrário as legendas desalinham depois do concat.
7. **Nunca corte no meio de uma palavra.** Encaixe toda borda de corte numa fronteira de palavra do transcript.
8. **Acolchoe toda borda de corte.** Janela de trabalho: 30–200ms. Timestamps de ASR (local ou Scribe) desviam 50–100ms — o acolchoamento absorve o desvio. Mais justo para ritmo rápido, mais folgado para cinematográfico.
9. **ASR verbatim em nível de palavra, sempre.** Nunca modo SRT/frase (perde dados de gap sub-segundo). Se estiver usando o motor local para conteúdo onde hesitação/gagueira é sinal editorial importante, use `--verbatim` com `--language` explícito (ver "Transcrição").
10. **Cacheie transcripts por fonte.** Nunca retranscreva a menos que o arquivo-fonte tenha mudado — vale para os dois motores.
11. **Sub-agentes paralelos para múltiplas animações.** Nunca sequencial. Dispare N de uma vez via a ferramenta `Agent`; tempo total ≈ o mais lento.
12. **Confirmação de estratégia antes de executar.** Nunca toque no corte antes do usuário aprovar o plano em português simples.
13. **Toda saída de sessão em `<videos_dir>/edit/`.** Nunca escreva dentro do diretório do projeto da skill.
14. **Narração por IA (`voiceover.py`) só roda sobre um roteiro que o usuário revisou explicitamente.** Nunca gere ou troque o que está sendo dito como efeito colateral silencioso de uma edição.

Tudo o mais neste documento é exemplo testado. Desvie sempre que o material pedir.

## Diretório

A skill mora em `manciasolutions-editor-de-video/`. O material do usuário mora onde ele colocar. Toda saída de sessão vai para `<videos_dir>/edit/`.

```
<videos_dir>/
├── <arquivos-fonte, intocados>
└── edit/
    ├── project.md               ← memória; um bloco anexado por sessão
    ├── takes_packed.md          ← transcripts em nível de frase, a visão de leitura primária
    ├── edl.json                 ← decisões de corte
    ├── transcripts/<nome>.json  ← transcript cacheado (local ou Scribe — schema idêntico)
    ├── animations/slot_<id>/    ← fonte + render + raciocínio de cada animação
    ├── clips_graded/            ← extrações por segmento com grade + fades
    ├── master.srt (ou .ass)     ← legendas na timeline de saída
    ├── narration/                ← roteiros e áudios gerados por voiceover.py
    ├── downloads/                ← saídas do yt-dlp
    ├── verify/                   ← frames de debug / PNGs de timeline
    ├── preview.mp4
    ├── final_vertical.mp4        ← quando --format é usado, um arquivo por formato pedido
    ├── final_horizontal.mp4
    └── final.mp4
```

## Setup

Instalação de primeira vez está em `install.md` (clone, deps, ffmpeg, registro da skill, chaves). Não rode de novo toda sessão; no início frio, só verifique:

- `ffmpeg` + `ffprobe` no PATH.
- Deps Python instaladas (`uv sync` ou `pip install -e .` dentro do repositório da skill).
- **Motor local (padrão):** `whisperx` instalado. Primeiro uso baixa o modelo Whisper e o modelo de alinhamento do idioma detectado (alguns GB, uma vez, depois cacheado). Sem chave de API necessária.
- **Motor ElevenLabs (opcional):** `ELEVENLABS_API_KEY` resolve — no ambiente ou em `.env` na raiz do repositório da skill. Só peça ao usuário se ele explicitamente pedir `--engine elevenlabs` ou `voiceover.py`/`soundtrack.py` com narração por IA.
- **Diarização local (opcional):** `HF_TOKEN` em `.env` se o usuário quiser `--diarize` no motor local (precisa aceitar os termos do modelo pyannote/speaker-diarization no Hugging Face uma vez).
- Node.js + npm disponíveis se a sessão precisar de slots HyperFrames ou Remotion. HyperFrames precisa de Node.js 22+.
- `yt-dlp`, HyperFrames, Remotion, Manim instalados só no primeiro uso.
- Setup de animação de primeiro uso acontece dentro do diretório do slot, nunca na raiz do repositório da skill.
- Esta skill vendoriza `skills/manim-video/`. Leia o SKILL.md dela ao construir um slot Manim.

Helpers (`helpers/transcribe.py`, `helpers/render.py` etc.) moram ao lado deste SKILL.md. Resolva os caminhos deles relativos ao diretório que contém este arquivo — a skill normalmente é symlinkada em `~/.claude/skills/manciasolutions-editor-de-video/`.

## Helpers

**Transcrição (dois motores, schema idêntico — ver `helpers/transcribe_common.py`):**
- **`transcribe.py <video>`** — despachante. `--engine local` (padrão) ou `--engine elevenlabs`. Cacheado.
- **`transcribe_local.py <video>`** — WhisperX local. `--language pt` recomendado (habilita o prompt verbatim). `--diarize` opcional (precisa `HF_TOKEN`). `--model large-v3` padrão, caia para `medium` em hardware modesto.
- **`transcribe_elevenlabs.py <video>`** — Scribe, nuvem. `--num-speakers N` opcional. Diarização e tags de evento de áudio ((risos), (aplausos)) de fábrica.
- **`transcribe_batch.py <videos_dir>`** — transcrição paralela. `--workers` padrão 1 para local (contenção de VRAM), 4 para elevenlabs.
- **`pack_transcripts.py --edit-dir <dir>`** — `transcripts/*.json` → `takes_packed.md` (nível de frase, quebra em silêncio ≥ 0.5s).
- **`timeline_view.py <video> <start> <end>`** — filmstrip + waveform PNG. Ferramenta de mergulho visual sob demanda. **Não é ferramenta de varredura** — use em pontos de decisão, não constantemente.

**Composição:**
- **`render.py <edl.json> -o <out>`** — extração por segmento → concat → reenquadramento → overlays (deslocados por PTS) → legendas por ÚLTIMO. `--preview` para 720p rápido. `--build-subtitles` para gerar master.srt inline. `--caption-style <preset>` (ver `captions_presets.py`). `--format <target>` (ver `format_targets.py`).
- **`grade.py <in> -o <out>`** — grade em cadeia de filtro ffmpeg. Presets + `--filter '<raw>'` para customizar.
- **`captions_presets.py`** — biblioteca de estilos de legenda: `bold-overlay`, `natural-sentence`, `minimal-clean`, `karaoke-word`. `python helpers/captions_presets.py` lista todos.
- **`format_targets.py`** — presets de formato de saída: `vertical-reel`, `vertical-story`, `horizontal-youtube`, `square-feed`. Estratégia `crop` ou `blur-pad` (padrão).

**Opcionais (nunca automáticos — só quando o usuário pede explicitamente):**
- **`voiceover.py`** — narração por TTS (ElevenLabs) a partir de um roteiro revisado. Pode substituir o áudio de uma tomada ou narrar B-roll sem fala original.
- **`soundtrack.py`** — mixa uma trilha sob o diálogo existente, com duck automático e fade. Agnóstico de fonte — funciona com qualquer arquivo de áudio, gerado por IA (Suno e afins) ou licenciado.

Para animações, crie `<edit>/animations/slot_<id>/` com `Bash` e dispare um sub-agente via a ferramenta `Agent`.

## O processo

1. **Inventário.** `ffprobe` em cada fonte. `transcribe_batch.py` no diretório (motor local por padrão — nenhuma chave necessária para começar). `pack_transcripts.py` para produzir `takes_packed.md`. Amostre um ou dois `timeline_view`s para uma primeira impressão visual.
2. **Pré-varredura de problemas.** Uma passada em `takes_packed.md` para notar deslizes verbais, erros de fala óbvios, ou frases a evitar. Lista simples, alimenta o briefing do editor.
3. **Conversar.** Descreva o que vê em português simples. Faça perguntas *moldadas pelo material* — e cubra explicitamente: tipo de conteúdo, **formato(s) de saída** (vertical para Reels/TikTok/Shorts, horizontal para YouTube, ou ambos a partir do mesmo corte — pergunte, não assuma), direção estética/de marca, sensação de ritmo, momentos que precisam ser preservados, momentos que precisam ser cortados, preferências de animação e grade, estilo de legenda, se precisa de narração por IA ou trilha sonora. Não use um checklist fixo — as perguntas certas são diferentes toda vez.
4. **Propor estratégia.** 4–8 frases: forma, escolha de tomadas, direção de corte, plano de animação, direção de grade, estilo de legenda, formato(s) de saída, estimativa de duração. **Espere confirmação.**
5. **Executar.** Produza `edl.json` via o briefing do sub-agente editor. Mergulhe em `timeline_view` em momentos ambíguos. Construa animações em sub-agentes paralelos. Aplique grade por segmento. Componha via `render.py` — uma chamada por formato de saída pedido.
6. **Preview.** `render.py --preview`.
7. **Auto-avaliação (antes de mostrar ao usuário).** Rode `timeline_view` na **saída renderizada** (não nas fontes) em toda fronteira de corte (janela ±1.5s). Confira cada imagem por:
   - Descontinuidade visual / flash / salto no corte
   - Pico de waveform na fronteira (estalo de áudio que escapou do fade de 30ms)
   - Legenda escondida atrás de um overlay (violação da Regra 1)
   - Overlay desalinhado ou mostrando frames errados (violação da Regra 5)
   - Se `--format` foi usado: conteúdo importante cortado pelo reenquadramento (violação da Regra 2)
   - **Legenda na altura certa** — não basta existir no `master.srt`: extraia um frame num instante em que uma deixa está ativa e confirme visualmente que ela está no rodapé, não no meio do quadro, e acima da zona de UI se for vertical. Só o frame renderizado revela erro de `MarginV`; `ffprobe` e o log do ffmpeg passam limpos.

   Também amostre: primeiros 2s, últimos 2s, e 2–3 pontos no meio — confira consistência de grade, legibilidade de legenda, coerência geral. Rode `ffprobe` na saída para confirmar que a duração bate com a esperada pelo EDL.

   Se algo falhar: corrija → renderize de novo → reavalie. **Limite de 3 passadas de auto-avaliação** — se problemas persistirem depois de 3, sinalize ao usuário em vez de entrar em loop. Só apresente o preview depois que a auto-avaliação passar.
8. **Iterar + persistir.** Feedback em linguagem natural, replaneje, renderize de novo. Nunca retranscreva. Render final na confirmação. Anexe a `project.md`.

## Transcrição — escolhendo o motor

**Use o motor local (padrão) quando:** o vídeo não precisa sair da máquina do usuário (privacidade), não há orçamento por transcrição, ou diarização/tags de áudio não são críticas. É o caso da maioria — talking-head solo, tutoriais, conteúdo de um único orador.

**Use `--engine elevenlabs` quando:** o material tem múltiplos falantes e diarização confiável importa de fábrica, ou tags de evento de áudio ((risos), (aplausos)) são um sinal editorial que vale a pena capturar sem trabalho extra, ou remoção agressiva de hesitação/muleta ("é", "tipo", "hum") é central ao corte e o orçamento permite.

**Sobre o anti-padrão herdado "nunca rode Whisper local":** essa regra do video-use original é real, mas específica ao Whisper puro — o decoder dele tende a normalizar (apagar) hesitações porque o texto de treinamento sub-representa disfluência. `transcribe_local.py` ataca isso com `--verbatim` (ligado por padrão): um `initial_prompt` cheio de hesitações que reduz — não elimina — essa normalização, mas só funciona bem quando `--language` é passado explicitamente (o prompt precisa saber em que idioma hesitar). Para trabalho onde capturar toda muleta é crítico e o orçamento permite, o motor ElevenLabs ainda captura hesitação de forma mais confiável — é uma troca real, não um blefe. Escolha por projeto.

## Formato de saída — vertical, horizontal, ou os dois

A mesma decisão de corte quase sempre serve para os dois formatos — o que muda é o reenquadramento, não a edição. Pergunte cedo (passo 3 do processo) se o usuário quer:

- **Só vertical** (`--format vertical-reel`) — Reels, TikTok, Shorts.
- **Só horizontal** (`--format horizontal-youtube`) — YouTube, apresentações.
- **Os dois a partir do mesmo `edl.json`** — rode `render.py` duas vezes, uma por formato, cada uma para seu `final_<formato>.mp4`. As decisões de corte não mudam; só o filtro de reenquadramento.

**Estratégia de reenquadramento** (`--reframe-strategy`):
- **`blur-pad`** (padrão) — fundo desfocado e ampliado preenche as barras. É a técnica que praticamente todo repost moderno de horizontal-para-vertical usa; parece muito menos "obviamente reaproveitado" que um corte duro ou barra preta.
- **`crop`** — corte central simples. Use quando o enquadramento original já centraliza o sujeito e simplicidade/nitidez importam mais que preservar as bordas do frame.

Overlays e texto posicionados para um formato **não** se recompõem automaticamente para o outro — se o usuário quer os dois formatos com gráficos, planeje o layout de cada slot de animação pensando em ambas as proporções, ou construa dois slots.

## Estilo de legenda

`captions_presets.py` guarda a biblioteca. Escolha por contexto, não por padrão automático:

- **`bold-overlay`** — curta, rápida, redes sociais. Chunks de 3 palavras, MAIÚSCULA, alto contraste. Formato padrão do short-form de alta retenção.
- **`natural-sentence`** — narrativo, documental, educacional. Frase quase completa, caixa natural, discreta.
- **`minimal-clean`** — caixa semitransparente em vez de contorno grosso. Para conteúdo visual denso onde a legenda não pode competir por atenção.
- **`karaoke-word`** — uma palavra destacada por vez, sincronizada ao áudio. O efeito "legenda TikTok" dinâmica. Precisa de granularidade word-level precisa — funciona melhor com o motor de transcrição que tiver o alinhamento mais limpo para o idioma em questão.

`render.py --build-subtitles --caption-style <nome>` cuida do chunking (quantas palavras por tela) e do `force_style` juntos — os dois viajam sempre pareados, escolher só um dos dois produz uma legenda com o tamanho de chunk errado para o estilo visual.

Regras rígidas continuam valendo: legendas por último (Regra 1), offsets de timeline de saída (Regra 6).

## Narração por IA (opcional)

`voiceover.py` existe para dois casos reais, não um genérico "adicionar voz":

1. **Substituir uma tomada ruim** (problema de ruído ambiente, um erro que você prefere reescrever a regravar) mantendo o vídeo original.
2. **Narrar B-roll/material que nunca teve fala** — o padrão "conteúdo faceless": roteiro entra, vídeo narrado sai.

**Regra rígida 14 se aplica: nunca rode isso sobre um roteiro que o usuário não revisou explicitamente.** Narração muda o que está sendo dito — isso nunca é um efeito colateral silencioso de uma edição normal. Mostre o roteiro, espere aprovação, só então sintetize.

`--music-bed` mixa uma trilha por baixo com duck automático via `sidechaincompress` — a narração nunca é abaixada, só a música cede espaço quando há fala.

## Trilha sonora (opcional)

`soundtrack.py` resolve a parte mecânica (loop até a duração exata, duck automático sob o diálogo existente, fade de saída) e é agnóstico de onde a faixa veio — uma biblioteca licenciada, ou gerada com Suno ou outra ferramenta de IA. A geração em si acontece fora deste script; o que ele garante é uma mixagem correta e chata, que não deveria depender de qual gerador produziu a faixa.

## Corte (técnicas)

- **Áudio primeiro.** Candidatos a corte de fronteiras de palavra e gaps de silêncio.
- **Preserve picos.** Risadas, momentos de impacto, batidas de ênfase. Estenda além de falas de impacto para incluir reações — a risada É a batida.
- **Passagens entre falantes** se beneficiam de ar entre falas. Valores comuns: 400–600ms. Menos para ritmo rápido, mais para cinematográfico. Chamada de gosto.
- **Eventos de áudio como sinal.** `(risos)`, `(suspiros)`, `(aplausos)` marcam batidas — disponíveis de fábrica no motor ElevenLabs; o motor local os aproxima via os gaps de silêncio ao redor. Estenda além deles.
- **Gaps de silêncio são candidatos a corte.** Silêncios ≥400ms costumam ser os mais limpos. Fronteiras de frase de 150–400ms são usáveis com checagem visual. <150ms é inseguro (meio de frase).
- **Acolchoamento de exemplo**: 50ms antes da primeira palavra mantida, 80ms depois da última. Mais justo para energia de montagem, mais folgado para documentário. Fique na janela de trabalho 30–200ms (Regra Rígida 8).
- **Nunca raciocine áudio e vídeo separadamente.** Todo corte precisa funcionar nas duas trilhas.

## O transcript empacotado (visão de leitura primária)

`pack_transcripts.py` lê todos os `transcripts/*.json` (de qualquer motor — o schema é idêntico) e produz um markdown onde cada tomada é uma lista de linhas em nível de frase, cada uma prefixada com seu intervalo `[início-fim]`. Frases quebram em qualquer silêncio ≥ 0.5s OU troca de falante. É o artefato que o sub-agente editor lê para escolher cortes.

Exemplo de linha:
```
## clip01  (duration: 43.0s, 8 phrases)
  [002.52-005.36] S0 Noventa por cento do que um agente de vídeo faz é retrabalho.
  [006.08-006.74] S0 A gente resolveu isso.
```

## Briefing do sub-agente editor (para seleção entre várias tomadas)

Quando a tarefa é "escolher a melhor tomada de cada trecho entre várias gravações", dispare um sub-agente dedicado com um briefing neste formato. A estrutura é estrutural; o exemplo de arco não é.

```
Você está editando um vídeo <tipo>. Escolha a melhor tomada de cada trecho e
monte na ordem cronológica do trecho, não na ordem dos arquivos-fonte.

ENTRADAS:
  - takes_packed.md (transcripts em nível de frase, com tempo, de todas as tomadas)
  - Contexto do produto/narrativa: <2 frases do usuário>
  - Falante(s): <nome, papel, nota de estilo de entrega>
  - Estrutura esperada: <escolha um arquétipo ou invente um>
  - Deslizes verbais a evitar: <lista da pré-varredura>
  - Formato(s) de saída: <vertical / horizontal / ambos>
  - Duração alvo: <segundos>

Arquétipos estruturais comuns (escolha, adapte, ou invente):
  - Lançamento/demo:      GANCHO → PROBLEMA → SOLUÇÃO → BENEFÍCIO → EXEMPLO → CTA
  - Tutorial:             INTRO → SETUP → PASSOS → PEGADINHAS → RECAP
  - Entrevista:           (PERGUNTA → RESPOSTA → FOLLOWUP) repete
  - Viagem/evento:        CHEGADA → DESTAQUES → MOMENTOS CALMOS → PARTIDA
  - Documentário:         TESE → EVIDÊNCIA → CONTRAPONTO → CONCLUSÃO
  - Ou invente o seu.

REGRAS:
  - Início/fim precisam cair em fronteiras de palavra do transcript.
  - Acolchoe as bordas de corte (janela de trabalho 30–200ms).
  - Prefira silêncios ≥ 400ms como alvo de corte.
  - Deslizes inevitáveis ficam se não houver tomada melhor. Anote em "reason".
  - Se passar do orçamento, revise: corte um trecho ou apare as pontas. Reporte o total e autocorrija.

SAÍDA (array JSON, sem prosa):
  [{"source": "clip01", "start": 2.42, "end": 6.85, "beat": "GANCHO",
    "quote": "...", "reason": "..."}, ...]

Retorne o EDL final e uma checagem de duração total em uma linha.
```

## Correção de cor (quando pedido)

Seu trabalho é **raciocinar sobre a imagem**, não aplicar um preset. Olhe um frame (via `timeline_view`), decida o que está errado, ajuste uma coisa, olhe de novo.

Modelo mental é ASC CDL. Por canal: `saída = (entrada * slope + offset) ** power`, depois saturação global. `slope` → realces, `offset` → sombras, `power` → meios-tons.

**Cadeias de filtro de exemplo** (`grade.py` tem `--list-presets`; use como ponto de partida ou misture o seu):

- **`warm_cinematic`** — retrô/técnico, split sutil azul/laranja, dessaturado. Seguro para talking heads.
- **`neutral_punch`** — correção mínima: aumento de contraste + curva S suave. Sem mudança de matiz.
- **`none`** — cópia direta. Padrão quando o usuário não pediu nada.

Para qualquer outra coisa — retrato, natureza, produto, videoclipe, documentário — invente sua própria cadeia. `grade.py --filter '<raw ffmpeg>'` aceita qualquer string de filtro.

Regras rígidas: aplique **por segmento durante a extração** (não pós-concat, que recodifica duas vezes). Nunca vá agressivo sem testar tons de pele.

## Animações (quando pedido)

Animações combinam com o conteúdo e a marca. **Pegue a paleta, a fonte e a linguagem visual da conversa** — nunca assuma um padrão. Se o usuário não disse, proponha uma paleta na fase de estratégia e espere confirmação antes de construir qualquer coisa.

**Opções de ferramenta** (escolha por slot de animação, não use Remotion por padrão só porque a animação é web-adjacente):

- **HyperFrames** — composições HTML/CSS/GSAP nativas de navegador: motion de UI de produto, captura de site/mockup para vídeo, tipografia cinética, promos de landing page/storyboard, estados de UI orientados a dado, overlays WebM transparentes.
- **Remotion** — composições React/CSS com estado de componente, primitivas React reutilizáveis, ou um sistema de marca Remotion já existente.
- **Manim** — diagramas formais, máquinas de estado, derivações de equação, morphs de gráfico. Leia `skills/manim-video/SKILL.md` e suas referências.
- **PIL + sequência PNG + ffmpeg** — cartões de overlay simples: contadores, texto de máquina de escrever, revelações de barra, desenho progressivo. Rápido de iterar.

Nenhum é obrigatório. Invente híbridos se for útil (ex: fundo em PIL com uma camada HyperFrames ou Remotion por cima).

**Regras de ritmo (dependentes de contexto):**

- **Explicações sincronizadas com narração.** O espectador precisa processar o conteúdo em 1×. Piso aproximado 3s, típico 5–7s para cartões simples, 8–14s para diagramas complexos.
- **Acentos sincronizados a batida** (videoclipe, montagem rápida). 0.5–2s está bom — são acentos visuais, não informação.
- **Segure o frame final ≥ 1s** antes do corte (universal).
- **Sobre narração:** duração total ≥ `duração_da_narração + 1s` (universal).
- **Nunca revele elementos independentes em paralelo** — o olho não acompanha duas coisas novas ao mesmo tempo. Uma coisa, pausa, próxima.

**Easing** (universal — nunca `linear`, parece robótico):

```python
def ease_out_cubic(t):    return 1 - (1 - t) ** 3
def ease_in_out_cubic(t):
    if t < 0.5: return 4 * t ** 3
    return 1 - (-2 * t + 2) ** 3 / 2
```

`ease_out_cubic` para revelações únicas (pouso lento). `ease_in_out_cubic` para desenhos contínuos.

**Truque de âncora de texto digitando:** centralize na largura da string COMPLETA, não na largura parcial — do contrário o texto desliza para a esquerda durante a revelação.

**Briefing de sub-agente paralelo** — cada animação é um sub-agente disparado via a ferramenta `Agent`. Cada prompt é autocontido (sub-agentes não têm contexto do pai). Inclua:

1. Objetivo em uma frase: *"Construa UMA animação: [spec]. Nada mais."*
2. Caminho de saída absoluto (`<edit>/animations/slot_<id>/render.mp4`)
3. Spec técnica exata: resolução, fps, codec, pix_fmt, CRF, duração
4. Paleta de estilo em valores concretos (tuplas RGB, hex, ou referência a um design system)
5. Caminho da fonte com índice
6. Timeline frame a frame (o que acontece quando, com easing)
7. Anti-lista ("sem chrome, sem extras, sem títulos a menos que especificado")
8. Referência de padrão de código (copie helpers inline, não importe entre slots)
9. Checklist de entrega (script, render, verificar duração via ffprobe, reportar)
10. **"Não faça perguntas. Se algo for ambíguo, escolha a interpretação mais óbvia e prossiga."**

Um sub-agente = um arquivo (nomes únicos, agentes paralelos não sobrescrevem uns aos outros).

## Spec de saída

Combine com a fonte a menos que o usuário tenha pedido algo específico. Alvos comuns: `1920×1080@24` cinematográfico, `1920×1080@30` conteúdo de tela, `1080×1920@30` social vertical, `3840×2160@24` cinema 4K, `1080×1080@30` quadrado. Vale perguntar ao usuário qual formato de entrega importa — e se são vários (ver seção "Formato de saída").

## Formato EDL

```json
{
  "version": 1,
  "sources": {"clip01": "/abs/path/clip01.MP4", "clip02": "/abs/path/clip02.MP4"},
  "ranges": [
    {"source": "clip01", "start": 2.42, "end": 6.85,
     "beat": "GANCHO", "quote": "...", "reason": "Entrega mais limpa, para antes do deslize em 38.46."},
    {"source": "clip02", "start": 14.30, "end": 28.90,
     "beat": "SOLUÇÃO", "quote": "...", "reason": "Única tomada sem o falso início."}
  ],
  "grade": "warm_cinematic",
  "overlays": [
    {"file": "edit/animations/slot_1/render.mp4", "start_in_output": 0.0, "duration": 5.0}
  ],
  "subtitles": "edit/master.srt",
  "caption_style": "bold-overlay",
  "format": "vertical-reel",
  "total_duration_s": 87.4
}
```

`grade` é um nome de preset ou filtro ffmpeg cru. `overlays` são clipes de animação renderizados. `subtitles` é opcional e aplicado por ÚLTIMO. `caption_style` e `format` são opcionais — passe-os para `render.py` via `--caption-style` e `--format` (o EDL só os documenta para referência de sessão; `render.py` lê esses flags da linha de comando, não do EDL, para manter a composição determinística e auditável a partir da chamada).

## Memória — `project.md`

Anexe um bloco por sessão em `<edit>/project.md`:

```markdown
## Sessão N — AAAA-MM-DD

**Estratégia:** um parágrafo descrevendo a abordagem
**Decisões:** escolhas de tomada, cortes, grades, animações + porquê
**Motores usados:** transcrição (local/elevenlabs), formatos gerados
**Log de raciocínio:** justificativa de uma linha para decisões não óbvias
**Pendências:** itens adiados
```

Ao iniciar, leia `project.md` se existir e resuma a última sessão em uma frase antes de perguntar se deve continuar.

## Anti-padrões

Coisas que consistentemente falham, independente de estilo:

- **Formatos de código pré-computados e hierárquicos** com tags de usabilidade/tom/camadas de plano. Over-engineering. Derive do transcript na hora da decisão.
- **Funções de pontuação de momento ajustadas manualmente.** O LLM escolhe melhor que qualquer heurística que você vai escrever.
- **SRT/saída em nível de frase do Whisper.** Perde dados de gap sub-segundo. Sempre verbatim em nível de palavra.
- **Rodar o motor local sem `--language` quando hesitação importa.** O prompt verbatim só ativa com idioma explícito — auto-detect roda sem ele.
- **Queimar legendas na base antes de compor overlays ou reenquadramento.** Overlays as escondem; reenquadramento as corta. (Regras Rígidas 1 e 2.)
- **Filtergraph de passe único quando há overlays.** Recodifica duas vezes. Use extração por segmento → concat.
- **Easing linear de animação.** Parece robótico. Sempre cúbico.
- **Cortes de áudio duros nas fronteiras de segmento.** Estalos audíveis. (Regra Rígida 4.)
- **Centralizar texto na string parcial.** O texto desliza para a esquerda enquanto cresce.
- **Sub-agentes sequenciais para múltiplas animações.** Sempre paralelo.
- **Editar antes de confirmar a estratégia.** Nunca.
- **Retranscrever fontes cacheadas.** Saídas imutáveis de entradas imutáveis.
- **Assumir que tipo de vídeo é, ou assumir um único formato de saída.** Olhe primeiro, pergunte segundo, edite por último.
- **Gerar ou trocar narração sem roteiro revisado pelo usuário.** (Regra Rígida 14.)
- **Tratar `MarginV` da legenda como pixels.** O libass escala contra `PlayResY=288`, então `MarginV=140` fica a ~49% da altura — quase no centro do quadro, não "um pouco acima da base". Esse erro não gera aviso nenhum no log do ffmpeg; só aparece num frame renderizado. Foi um bug real durante a construção desta skill, corrigido e travado por teste. Use sempre `captions_presets.force_style_for(estilo, formato)` em vez de montar `force_style` à mão.
- **Usar a mesma `MarginV` para vertical e horizontal.** A zona segura é diferente: plataformas verticais cobrem ~25–30% do rodapé com UI, horizontais não cobrem quase nada. Um único valor erra num dos dois.
