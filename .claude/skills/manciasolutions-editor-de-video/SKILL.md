---
name: manciasolutions-editor-de-video
description: Editor de vídeo completo por conversa. Transcreve, corta, remove silêncio e vício de linguagem, aplica color grade, legenda karaokê/animada, reenquadra para vertical seguindo o sujeito, sincroniza com a batida, mixa trilha com ducking, cria animações, roda QC automático e gera capa. Talking head, podcast, tutorial, vlog, anúncio, entrevista, reels. Use quando o usuário quiser editar, cortar, legendar, reenquadrar, dublar, melhorar áudio ou finalizar qualquer vídeo. Também dispara em "editar vídeo", "fazer um reels", "cortar podcast", "legenda automática", "transformar em vertical", "tirar os silêncios".
---

# ManciaSolutions — Editor de Vídeo

Editor de vídeo conversacional. Sem menu, sem preset obrigatório, sem timeline pra arrastar.
Você pergunta, o usuário responde, você propõe, ele confirma, você executa, verifica e itera.

Derivado do [`browser-use/video-use`](https://github.com/browser-use/video-use) (MIT) — veja `NOTICE`.
O que foi acrescentado: legenda animada, auto-cut, auto-reframe, beat sync, pós de áudio,
transições, punch-in, QC automatizado, capa e integração com MCPs de mídia.

## Princípios

1. **O LLM raciocina sobre o transcript cru + visual sob demanda.** O único artefato derivado que se paga é o transcript empacotado (`takes_packed.md`). Tagging de filler, detecção de retake, classificação de plano — tudo isso você deriva na hora da decisão, não antes.
2. **Áudio é primário, imagem segue.** Candidatos a corte saem de fronteira de palavra e de silêncio. Olhe a imagem nos pontos de decisão, não o tempo todo.
3. **Perguntar → confirmar → executar → iterar → persistir.** Nunca toque no corte antes de o usuário aprovar a estratégia em português claro.
4. **Generalize.** Não presuma que tipo de vídeo é. Olhe o material, pergunte, então edite.
5. **Liberdade artística é o padrão.** Todo valor, preset, fonte, cor, duração e técnica deste documento é um *exemplo que funcionou*, não um mandato. **A única coisa obrigatória são as Regras Duras.** O resto é seu.
6. **Invente.** Split-screen, picture-in-picture, lower third, match cut, L-cut, J-cut, freeze frame, speed ramp sobre a respiração — se o material pede e o ffmpeg faz, construa. Não espere permissão.
7. **Verifique antes de mostrar.** Se você não publicaria, não apresente.
8. **Degrade em voz alta.** Sem chave da ElevenLabs, sem OpenCV, sem MCP — tudo bem, existe caminho. O que não existe é fingir que a capacidade está lá.

## Regras Duras (correção de produção — inegociáveis)

Aqui deviar produz falha silenciosa ou saída quebrada. Não é gosto, é correção.

1. **Legenda é aplicada POR ÚLTIMO** na cadeia de filtros, depois de todo overlay. Senão o overlay esconde a legenda. Falha silenciosa.
2. **Extração por segmento → concat `-c copy`**, nunca filtergraph único. Senão você recodifica cada segmento duas vezes ao acrescentar overlay. O concat exige que **todos** os segmentos tenham a mesma resolução, o mesmo frame rate e o mesmo SAR — o `render.py` resolve uma geometria só para o render inteiro e enquadra o resto com barras. Escalar por orientação de cada fonte (o que parece natural num EDL que mistura horizontal e vertical) gera segmentos de tamanhos diferentes; o `-c copy` aceita sem reclamar e o arquivo troca de resolução no meio. O estrago aparece longe dali: legenda esticada e overlay no lugar errado nos segmentos divergentes.
3. **Fade de áudio de 30 ms em toda borda de segmento** (`afade=t=in:st=0:d=0.03,afade=t=out:st={dur-0.03}:d=0.03`). Senão estala em cada corte.
4. **Overlay usa `setpts=PTS-STARTPTS+T/TB`** para levar o frame 0 do overlay ao início da janela. Senão você vê o meio da animação.
5. **SRT/ASS mestre em offset da timeline de saída**: `t_saida = palavra.start - segmento.start + offset_do_segmento`. Senão a legenda desalinha depois do concat.
6. **Nunca corte dentro de uma palavra.** Encoste toda borda numa fronteira de palavra do transcript.
7. **Padding em toda borda de corte.** Janela de trabalho: 30–200 ms (100–150 ms com Whisper local, que erra mais). O timestamp do ASR deriva 50–100 ms; o padding absorve.
8. **ASR word-level verbatim.** Nunca modo SRT/frase (perde o dado de gap sub-segundo). Nunca filler normalizado (perde sinal editorial).
9. **Cache de transcrição por fonte.** Só re-transcreva se o arquivo de origem mudou.
10. **Sub-agentes paralelos para múltiplas animações.** Nunca em série. Dispare N de uma vez com a ferramenta `Agent`.
11. **Confirmação de estratégia antes da execução.** Nunca toque no corte antes do "pode ir".
12. **Toda saída de sessão em `<videos_dir>/edit/`.** Nunca escreva dentro do diretório da skill.
13. **Transição `xfade` quebra o concat lossless.** Só nas junções marcadas em `transitions`, via passe pairwise. E ela consome *handles* (material extra de d/2 em cada lado), nunca o corte em si — senão cada transição encurta a timeline e desalinha legenda e overlay.
14. **Trilha musical entra DEPOIS do loudnorm da fala**, com ducking. Somar música crua na fala já normalizada estoura o pico e desregula a medição.
15. **Auto-reframe exige suavização de trajetória.** Crop por frame sem média móvel + zona morta + limite de velocidade treme. Confira `reversals_x_per_s` no relatório; acima de ~1 inversão/s, a câmera está indo e voltando. Velocidade alta sozinha não é tremor — sujeito atravessando o quadro exige panorâmica rápida.
16. **Legenda karaokê usa o transcript word-level original**, nunca timestamp reinterpolado de um SRT já montado.
17. **O `.ass` é desenhado para uma resolução específica.** `captions.py --res` tem de casar com a saída do `render.py --size`; em outra geometria o libass reescala e a fonte sai de tamanho errado, sem erro nenhum. O `render.py` avisa quando o `PlayRes` do arquivo não bate.
18. **Rode `qc.py` antes de mostrar qualquer preview.** Máximo 3 ciclos de correção; depois disso, reporte ao usuário em vez de ficar em loop.
19. **Degradação é declarada.** Scribe indisponível → Whisper local **e avise**. Nenhum ASR → modo EDL manual **e avise**. OpenCV ausente → reframe por movimento **e avise**. Nunca entregue como se fosse o caminho completo.

Todo o resto neste documento é exemplo. Desvie sempre que o material pedir.

## Camadas de capacidade

O que funciona com o que você tem instalado. **Sempre diga ao usuário em que camada você está.**

| Camada | Requer | Habilita |
|---|---|---|
| **Base** | ffmpeg + ffprobe | Corte por EDL, grade, transição, punch-in, speed ramp, reframe por movimento, mix de áudio, QC, capa |
| **Transcrição local** | + `faster-whisper` | Auto-cut, legenda (sem diarização, sem evento de áudio, fillers normalizados) |
| **Transcrição completa** | + `ELEVENLABS_API_KEY` | Tudo acima com diarização, `(laughs)`/`(applause)` e fillers verbatim — **é o caminho bom** |
| **Visão** | + `opencv-python-headless` | Auto-reframe seguindo rosto, score de rosto na capa |
| **Música** | + `librosa` | BPM e grade de batida melhores (sem ela, cai no detector em numpy) |
| **Aceleradores** | MCP Magnific / Higgsfield | Upscale, dublagem, TTS, isolamento de voz, b-roll gerado, SFX, publicação. Veja `references/mcp-integrations.md` |

Nada acima da Base é obrigatório. Tudo acima da Base muda o que você consegue prometer.

## Layout de diretórios

A skill vive em `.claude/skills/manciasolutions-editor-de-video/`. O material do usuário fica onde ele quiser.
Toda saída de sessão vai para `<videos_dir>/edit/`.

```
<videos_dir>/
├── <arquivos de origem, intocados>
└── edit/
    ├── project.md               ← memória; um bloco por sessão
    ├── takes_packed.md          ← transcripts em frase, a sua vista de leitura
    ├── edl.json                 ← as decisões de corte
    ├── transcripts/<nome>.json  ← JSON word-level em cache
    ├── animations/slot_<id>/    ← fonte + render + racional de cada animação
    ├── clips_graded/            ← extrações por segmento com grade e fades
    ├── master.ass               ← legenda animada (ou master.srt)
    ├── beats.json               ← grade de batidas da trilha
    ├── downloads/               ← saídas do yt-dlp
    ├── verify/                  ← frames de borda, relatórios de QC, candidatos a capa
    ├── preview.mp4
    └── final.mp4
```

## Setup

A instalação de primeira vez está em `install.md` (ou rode `install.sh`). Não refaça a cada sessão.
No começo de uma sessão fria, só verifique:

- `ffmpeg` e `ffprobe` no PATH — **sem isso nada funciona**.
- `ELEVENLABS_API_KEY` resolve (ambiente ou `.env` na raiz da skill). Se faltar, diga que vai usar Whisper local e siga; só peça a chave se o usuário quiser diarização ou eventos de áudio.
- Deps Python: `uv sync` ou `pip install -e .` dentro da pasta da skill.
- Node.js 22+ só quando a sessão for usar HyperFrames ou Remotion.
- `yt-dlp`, HyperFrames, Remotion, Manim: instale no primeiro uso, dentro do slot, nunca na raiz da skill.

Os helpers ficam ao lado deste arquivo. Resolva o caminho deles relativo ao diretório deste `SKILL.md` — a skill costuma estar symlinkada em `~/.claude/skills/manciasolutions-editor-de-video/`.

## Helpers

| Helper | O que faz |
|---|---|
| `transcribe.py <video>` | Scribe ou Whisper local (`--engine auto\|scribe\|local`). Cacheado. |
| `transcribe_batch.py <dir>` | Transcrição paralela. 4 workers no Scribe, 2 no local. |
| `pack_transcripts.py --edit-dir <dir>` | `transcripts/*.json` → `takes_packed.md` (frase, quebra em silêncio ≥ 0,5 s). |
| `timeline_view.py <video> <ini> <fim>` | PNG com filmstrip + waveform. **Não é ferramenta de varredura** — use em ponto de decisão. |
| `autocut.py --edit-dir <dir> --all` | Propõe EDL removendo silêncio, filler, falso começo e respiração. Sempre proposta. |
| `beats.py <audio>` | BPM, grade de batidas, viradas. `--snap edl.json` encosta as bordas na batida. |
| `captions.py <edl> --style <estilo> --res WxH` | Gera `.ass` animado e já aponta o `subtitles` do EDL para ele. Estilos: `karaoke`, `pop`, `hormozi`, `doc`, `clean`, `box`. |
| `reframe.py <video> --aspect 9:16` | Auto-reframe seguindo o sujeito, com trajetória suavizada. |
| `grade.py <in> -o <out>` | Color grade. Presets + `--filter '<raw>'` + LUT `.cube`. |
| `audio_post.py <in> -o <out>` | Limpeza de voz, trilha com ducking, loudness por plataforma, `--analyze`. |
| `render.py <edl> -o <out> [--size WxH]` | Extrai por segmento → transições → concat → overlays → legenda POR ÚLTIMO → loudnorm → trilha. Uma geometria para todos os segmentos. |
| `qc.py <video> --edl <edl>` | QC automático. **Rode antes de todo preview.** |
| `thumbnail.py <video> -o capa.png` | Acha o melhor frame e monta a capa. |

Todo helper responde a `--help`. Vários têm `--list-presets` / `--list-styles` / `--print-filter` / `--print-chain` para você inspecionar sem renderizar.

## O processo

1. **Inventário.** `ffprobe` em toda origem. `transcribe_batch.py` no diretório. `pack_transcripts.py`. Uma ou duas `timeline_view` para primeira impressão visual.
2. **Pré-varredura.** Uma passada no `takes_packed.md` anotando escorregões, frases a evitar, trechos fortes. Lista simples, entra no brief.
3. **Converse.** Descreva o que você viu em português claro. Faça perguntas *moldadas pelo material* — não um checklist fixo. Colete: tipo de conteúdo, duração e formato alvo, direção estética, sensação de ritmo, momentos a preservar, momentos a cortar, legenda, grade, trilha, plataforma de destino.
4. **Proponha a estratégia.** 4–8 frases: forma, escolha de takes, direção de corte, plano de animação, grade, estilo de legenda, estimativa de duração. **Espere a confirmação.**
5. **Execute.** Monte o `edl.json`. `timeline_view` nos pontos ambíguos. Animações em sub-agentes paralelos. Grade por segmento. Componha com `render.py`.
6. **Preview.** `render.py --preview` (ou `--draft` só para conferir ponto de corte).
7. **QC (antes de mostrar).** `qc.py final.mp4 --edl edl.json --target <plataforma>`. Ele mede duração, estalo de junção, loudness, colisão legenda×overlay e exporta os frames de borda. O que ele aprova, você ainda confere no olho: continuidade visual no corte, legibilidade da legenda, consistência da grade. Falhou? Corrija, re-renderize, repita. **Teto de 3 ciclos** — depois, reporte em vez de loopar.
8. **Itere e persista.** Feedback em linguagem natural, replaneje, re-renderize. Nunca re-transcreva. Render final na confirmação. Escreva em `project.md`.

## Craft de corte

- **Áudio primeiro.** Candidatos saem de fronteira de palavra e de gap de silêncio.
- **Preserve os picos.** Riso, punchline, ênfase. Estenda além da punchline para pegar a reação — a risada *é* a batida.
- **Troca de falante** pede ar entre as falas. Valores comuns: 400–600 ms. Menos em ritmo rápido, mais em cinematográfico.
- **Evento de áudio é sinal.** `(laughs)`, `(sighs)`, `(applause)` marcam batida. Estenda além deles.
- **Silêncio é candidato a corte.** ≥ 400 ms é o mais limpo. 150–400 ms serve com conferência visual. < 150 ms é inseguro (meio de frase).
- **Nunca raciocine áudio e vídeo em separado.** Todo corte precisa funcionar nas duas faixas.
- **`autocut.py` é ponto de partida, não resposta.** Ele acha silêncio e filler; ele não sabe que aquele "né" era a piada. Leia o que ele propôs.

## Legendas

Três eixos que valem raciocínio: **agrupamento** (1/2/3/frase por linha), **caixa** (ALTA/Título/Natural) e **posição** (margem inferior).

**Sempre passe `--res` casando com a saída.** O `.ass` guarda a resolução em que foi desenhado (`PlayRes`), e tamanho de fonte e margens são calculados como fração da altura. Aplicado em outra geometria, o libass reescala e a legenda sai grande ou pequena demais. `captions.py --video final.mp4` lê a resolução do próprio arquivo.

`captions.py --list-styles` mostra o catálogo. Resumo:

- **`karaoke`** — varredura contínua, a palavra acende conforme é falada. Música, lyric, alta energia.
- **`pop`** — uma palavra por vez entrando com escala. Máxima retenção em vertical curto.
- **`hormozi`** — 3 palavras em caixa alta, corrente em amarelo, contorno grosso. Padrão de short viral.
- **`doc`** — frase natural, sóbria. Documentário, entrevista, institucional, aula.
- **`clean`** / **`box`** — meio-termo legível; `box` para fundo claro onde contorno não basta.

Ajuste com `--accent`, `--font`, `--size`, `--max-words`, `--margin-v`. Invente um estilo se nenhum servir.

**A margem inferior não é gosto, é safe-zone — e depende do aspecto.** Em 9:16 a UI de TikTok/Reels/Shorts cobre ~25–30% da base, daí os 18% de margem que o `captions.py` reserva sozinho. Em 16:9 não há UI nenhuma embaixo, e a mesma margem jogaria a legenda para o meio da tela: ali ele usa 7%. `margin_for_aspect()` escolhe pelo aspecto real; `--margin-v` sobrescreve (em fração da altura, não em pixels).

Detalhe: `.ass` carrega o próprio estilo, então o `render.py` usa o filtro `ass` sem `force_style`. Só o `.srt` recebe `force_style`. Mais em `references/captions.md`.

## Vertical e reenquadramento

`reframe.py entrada.mp4 -o vertical.mp4 --aspect 9:16`

Detecta o sujeito (rosto via OpenCV → energia de movimento → centro fixo), suaviza e recorta acompanhando.
Três freios contra tremor (Regra Dura 15): média móvel (`--smooth-window`), zona morta (`--deadzone`) e limite de velocidade (`--max-speed`).

**Detecção de rosto: baixe o modelo YuNet.** A ordem é YuNet → Haar → movimento, por qualidade e não por versão. O Haar vem dentro do wheel do OpenCV 4 (o 5 o removeu), mas foi treinado em fotografia e desaba fora dela — no material de teste deste repo ele acerta 0 de 12 amostras onde o YuNet acerta 12 de 12. O YuNet existe desde o OpenCV 4.5.4 e precisa de um `.onnx` de ~232 KB:

```bash
mkdir -p ~/.cache/manciasolutions && curl -L -o ~/.cache/manciasolutions/face_detection_yunet.onnx \
  https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

Tem de ser `media.githubusercontent.com`: o arquivo está em Git LFS, e a URL `/raw/` devolve o ponteiro de texto. O ponteiro baixa sem erro e só falha no parse do ONNX. Confira o tamanho (~232 KB). Sem o modelo, o helper diz o comando e segue por energia de movimento — nunca baixe sozinho, é ação de rede que o usuário não pediu.

- Conteúdo com uma pessoa parada → `--static` costuma ser melhor que o rastreio. Câmera que não precisa se mexer não deve se mexer.
- Duas pessoas alternando → rastreio com `--smooth-window 2.0` e `--max-speed 90`, ou split-screen (veja `references/transitions.md`).
- Tela/slide em 16:9 → não reenquadre. Ponha o 16:9 inteiro numa faixa central com fundo desfocado.
- Confira `reversals_x_per_s` no relatório. Acima de ~1/s a câmera vai e volta: aumente `--smooth-window` ou `--deadzone`. `speed_x_px_s` alto com poucas inversões é panorâmica legítima, não defeito.

## Color grade

Seu trabalho é **raciocinar sobre a imagem**, não aplicar preset. Olhe um frame (`timeline_view`), decida o que está errado, ajuste uma coisa, olhe de novo.

Modelo mental é ASC CDL. Por canal: `out = (in * slope + offset) ** power`, depois saturação global. `slope` → altas, `offset` → sombras, `power` → médios.

`grade.py --list-presets`: `subtle`, `neutral_punch`, `warm_cinematic`, `vivid_social`, `skin_safe`, `flat_log`, `cool_tech`, `bw_film`, `none`, `auto` (análise por clipe).

- `skin_safe` é o padrão sensato para rosto. `vivid_social` sobrevive à recompressão de TikTok/Reels.
- LUT `.cube` via `lut3d` — vai **depois** da correção técnica e **antes** do sharpen.
- Regra: aplique **por segmento na extração**, nunca pós-concat (recodifica duas vezes). Nunca vá agressivo sem testar em pele.

## Áudio

Áudio ruim mata um vídeo mais rápido que imagem ruim.

```
audio_post.py final.mp4 --analyze                          # mede antes de mexer
audio_post.py voz.mp4 -o limpa.mp4 --clean --target tiktok
audio_post.py corte.mp4 -o com_trilha.mp4 --music t.mp3 --duck --music-db -18
```

- Cadeias: `gentle` (fonte já boa), `clean` (padrão), `rescue` (sala ruim, ar-condicionado), `phone` (efeito).
- Alvos: −14 LUFS para rede social e YouTube, −16 podcast, −23 broadcast. Entregar mais alto só faz a plataforma abaixar de volta com a dinâmica já esmagada.
- Ducking (`sidechaincompress`): a voz vira cadeia lateral do compressor na música. `--music-db -20` com `--duck` é o ponto de partida; −24 se a fala for baixa.
- Ordem é Regra Dura 14: limpeza → loudnorm da voz → trilha com ducking. O `render.py` faz isso sozinho se o EDL tiver um bloco `music`.

## Movimento: transições, punch-in e speed

- **Transição** (`transitions` no EDL) re-encoda só o par envolvido e consome handles, não o corte. Tipos do `xfade`: `fade`, `dissolve`, `wipeleft`, `slideup`, `circleopen`, `pixelize`, `zoomin`, `smoothleft`… Corte seco é o padrão; transição é exceção com motivo.
- **Punch-in** (`punch` no segmento) — `1.12` para zoom fixo, `{"from":1.0,"to":1.12}` para push lento, `{"zoom":1.2,"x":0.5,"y":0.35}` para foco fora do centro. É o truque que faz jump cut parecer intencional.
- **Speed ramp** (`speed` no segmento) — `1.25` corta enrolação sem cortar conteúdo; `0.5` estica um beat. Vídeo e áudio andam juntos (`setpts` + `atempo`), e a legenda já compensa.
- Receitas de whip pan, glitch, zoom blur e split-screen em `references/transitions.md`.

## Animações

Animação combina com o conteúdo e a marca. **Pegue paleta, fonte e linguagem visual da conversa** — nunca assuma um padrão. Se o usuário não disse, proponha na fase de estratégia e espere confirmação.

Motores: **HyperFrames** (HTML/CSS/GSAP, UI de produto, tipografia cinética), **Remotion** (React), **Manim** (diagrama formal, equação), **PIL + sequência PNG** (card simples, contador, typewriter — rápido de iterar).

Universais: easing sempre cúbico, nunca `linear`. Segure o frame final ≥ 1 s. Sobre narração, duração ≥ `narração + 1s`. Nunca revele dois elementos independentes em paralelo. Texto digitando centraliza na largura da string **completa**, senão desliza.

Detalhes, briefs de sub-agente e o padrão de sincronia com a palavra-chave: `references/animations.md`.

## Formato do EDL

```json
{
  "version": 1,
  "sources": {"C0103": "/abs/path/C0103.MP4", "C0108": "/abs/path/C0108.MP4"},
  "ranges": [
    {"source": "C0103", "start": 2.42, "end": 6.85,
     "beat": "GANCHO", "quote": "...", "reason": "Melhor entrega, para antes do escorregão em 38.46.",
     "punch": {"from": 1.0, "to": 1.08}},
    {"source": "C0108", "start": 14.30, "end": 28.90,
     "beat": "SOLUÇÃO", "speed": 1.15, "punch": 1.12}
  ],
  "transitions": [
    {"after": 0, "type": "dissolve", "duration": 0.4}
  ],
  "grade": "skin_safe",
  "overlays": [
    {"file": "animations/slot_1/render.mp4", "start_in_output": 0.0, "duration": 5.0, "x": 0, "y": 0}
  ],
  "music": {"file": "trilha.mp3", "db": -20, "duck": true, "fade_in": 1.0, "fade_out": 2.0},
  "subtitles": "master.ass",
  "total_duration_s": 87.4
}
```

- `grade`: nome de preset, filtro ffmpeg cru, ou `"auto"` (análise por clipe).
- `speed`: >1 acelera, <1 desacelera. Muda a duração de saída do segmento — o `captions.py` e o `qc.py` já compensam.
- `punch`: número, ou `{from,to}` para rampa, ou `{zoom,x,y}` para foco.
- `transitions[].after: i`: junção entre o segmento `i` e o `i+1`.
- `overlays[].x/y`: **declare sempre.** Sem geometria, o `qc.py` só consegue avisar que *pode* haver colisão com a legenda, em vez de provar que não há.
- `music`: aplicado depois do loudnorm, por Regra Dura 14.
- `subtitles`: `.ass` (estilo próprio) ou `.srt` (recebe `force_style`). Aplicado por último.

## Memória — `project.md`

Acrescente um bloco por sessão em `<edit>/project.md`:

```markdown
## Sessão N — AAAA-MM-DD

**Camada:** qual ASR/visão/MCP estava disponível
**Estratégia:** um parágrafo
**Decisões:** takes, cortes, grade, legenda, animações + porquê
**Log de raciocínio:** uma linha por decisão não óbvia
**Pendências:** o que ficou para depois
```

Na abertura, leia `project.md` se existir e resuma a última sessão em uma frase antes de perguntar se é para continuar.

## Anti-patterns

Coisas que falham de forma consistente, independentemente de estilo:

- **Formato de codec pré-computado e hierárquico** com tags de usabilidade/tom/camada. Over-engineering. Derive do transcript na hora.
- **Função de score de momento afinada na mão.** O LLM escolhe melhor que qualquer heurística que você escreva.
- **Whisper em modo SRT/frase.** Perde o dado de gap sub-segundo. Sempre word-level.
- **Queimar legenda na base antes de compor overlay.** O overlay esconde. (Regra 1.)
- **Filtergraph único quando há overlay.** Recodifica duas vezes. (Regra 2.)
- **Corte seco de áudio na junção.** Estala. (Regra 3.)
- **Easing linear.** Parece robô. Sempre cúbico.
- **Texto digitando centralizado na string parcial.** Desliza para a esquerda enquanto cresce.
- **Sub-agentes em série para várias animações.** Sempre paralelo.
- **Transição em toda junção.** Transição vira ruído quando é padrão. Corte seco é o padrão.
- **Auto-reframe com rastreio em material parado.** `--static` é melhor. Câmera que não precisa se mexer não deve.
- **Trilha somada antes do loudnorm.** (Regra 14.)
- **Mostrar preview sem rodar `qc.py`.** (Regra 17.)
- **Aceitar a proposta do `autocut.py` sem ler.** Ele não sabe qual "né" era a piada.
- **Editar antes de confirmar a estratégia.** Nunca.
- **Re-transcrever fonte já em cache.** Saída imutável de entrada imutável.
- **Presumir o tipo do vídeo.** Olhe, pergunte, então edite.
