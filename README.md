# ManciaSolutions — Editor de Vídeo

Skill de edição de vídeo conversacional para agentes de IA (Claude Code, Codex e compatíveis). Joga o material bruto numa pasta, conversa com o agente, recebe o vídeo final — transcrito, cortado, corrigido de cor, legendado, reenquadrado para o formato certo.

Leia `SKILL.md` para o funcionamento completo. Este README é sobre linhagem, arquitetura e o que exatamente mudou em relação ao ponto de partida.

## Linhagem

Esta skill é um **fork de [video-use](https://github.com/browser-use/video-use)** (browser-use, MIT, ~24 mil estrelas). O pipeline de composição — extração por segmento, concat sem perdas, overlays deslocados por PTS, legendas por último, loudness normalization — é herdado quase integralmente, porque já estava correto e testado.

Três enxertos vieram de ideias **publicamente descritas** (não de código copiado — os repositórios abaixo não foram clonados, só documentados publicamente o suficiente para reimplementar o conceito do zero):

- **[edvid](https://github.com/fillrochaa/edvid)** — motor de transcrição local (WhisperX, sem chave de API) e a ideia de formato de saída como parâmetro explícito (vertical vs. horizontal a partir do mesmo corte).
- **[6missedcalls/video-editing-skill](https://github.com/6missedcalls/video-editing-skill)** — a existência de uma biblioteca de estilos de legenda nomeados (estilo Hormozi/bold incluso).
- **[silvabyte/skills — edit-video](https://skills.lc/silvabyte/skills)** — reforço da ideia de EDL explícito e revisável antes de renderizar (já presente no video-use, mantido e documentado com mais ênfase).

## O que é herdado do video-use, praticamente sem mudança

- `pack_transcripts.py` — empacota transcripts em markdown por frase.
- `timeline_view.py` — filmstrip + waveform para inspeção visual sob demanda.
- `grade.py` — correção de cor via cadeia de filtro ffmpeg.
- O modelo mental ASC CDL, as regras de easing, o briefing de sub-agente para seleção de tomadas, a auto-avaliação pós-render.
- Todas as 12 regras rígidas de correção de produção do documento original (subtítulos por último, fade de 30ms, extração por segmento, etc.) — mantidas integralmente e numeradas junto com as 2 novas.

## O que é novo

| Arquivo | O que faz | Por quê |
|---|---|---|
| `helpers/transcribe_common.py` | Schema comum de transcript, compartilhado pelos dois motores | Deixa os dois motores intercambiáveis sem tocar em `pack_transcripts.py`/`render.py` |
| `helpers/transcribe_local.py` | Transcrição local via WhisperX — sem chave, sem custo, sem upload | O maior ganho puxado da edvid. Inclui `--verbatim` (prompt inicial que reduz a normalização de hesitações do Whisper — ver `SKILL.md`) |
| `helpers/transcribe_elevenlabs.py` | O motor Scribe original, refatorado para o schema comum | Mantido como opção — diarização e tags de evento de áudio de fábrica ainda valem o custo em alguns casos |
| `helpers/transcribe.py` | Despachante entre os dois motores | Ponto único de entrada, `--engine local\|elevenlabs` |
| `helpers/captions_presets.py` | Biblioteca de 4 estilos de legenda nomeados | `bold-overlay` (estilo Hormozi/6missedcalls), `natural-sentence`, `minimal-clean`, `karaoke-word` |
| `helpers/format_targets.py` | Presets de reenquadramento vertical/horizontal/quadrado, com estratégia blur-pad ou crop | A mesma edição vira Reels e YouTube a partir do mesmo `edl.json` |
| `helpers/voiceover.py` | Narração por TTS (ElevenLabs), opcional, só sobre roteiro revisado | Substituir tomada ruim, ou narrar B-roll sem fala original |
| `helpers/soundtrack.py` | Mixagem de trilha sonora com duck automático, agnóstica de fonte | Funciona com qualquer música — licenciada ou gerada por IA |
| `helpers/render.py` | Adaptado: `--caption-style`, `--format`, `--reframe-strategy` novos; comportamento padrão preservado byte-a-byte quando nenhuma flag nova é passada | Zero regressão para quem só quer o comportamento original |

## O que conscientemente NÃO foi replicado

- **Voz sintética como padrão** (diferente do `affaan-m/everything-claude-code`) — narração por IA aqui é sempre opt-in e sobre roteiro revisado (Regra Rígida 14 do `SKILL.md`), nunca o caminho automático.
- **Múltiplos motores de animação simultâneos** (o `video-use` já cobre HyperFrames/Remotion/Manim/PIL bem; não havia necessidade de adicionar mais um só por completude).
- **Geração de trilha sonora por IA embutida** — deliberadamente deixada de fora do `soundtrack.py`, que só mixa. A geração fica a cargo de qualquer ferramenta que o usuário já use (Suno incluso), porque acoplar isso a um provedor específico envelheceria mal.

## Trade-off que vale entender antes de escolher motor de transcrição

O `video-use` original lista "nunca rode Whisper localmente" como anti-padrão, e a razão é real: o decoder do Whisper tende a normalizar (apagar) hesitações. `transcribe_local.py` ataca isso com um `initial_prompt` verbatim, mas não elimina o efeito por completo — é uma mitigação, não uma solução perfeita. Para transcrição onde capturar toda hesitação é crítico e o orçamento permite, o motor ElevenLabs ainda é mais confiável nesse ponto específico. Os dois motores continuam disponíveis exatamente por isso — não é indecisão, é a troca certa dependendo do projeto.

## Instalação

Ver `install.md`.

## Licença

MIT — ver `LICENSE`. Mantém o aviso de copyright original da Browser Use (autora do video-use) conforme exigido pela licença, com aviso adicional para as partes originais desta skill.
