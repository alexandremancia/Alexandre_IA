# Aceleradores via MCP — Magnific, Higgsfield, ElevenLabs

**Nada aqui é obrigatório.** Todo item desta página tem um caminho local equivalente ou
um "não dá, e tudo bem". A skill inteira funciona só com ffmpeg.

## Antes de usar qualquer um deles: duas regras

1. **Enviar material para um serviço externo é publicar.** O arquivo sai da máquina do
   usuário e pode ficar em cache ou log do fornecedor mesmo depois de apagado. Antes do
   primeiro upload de cada sessão, **diga o que vai subir e pergunte**. Material de cliente,
   gravação interna e qualquer coisa com pessoa identificável exigem um "pode" explícito.
2. **Crédito é dinheiro do usuário.** Upscale de 4K e geração de vídeo custam caro. Diga o
   que vai gastar antes de gastar, e prefira testar num trecho de 5 segundos antes de rodar
   o vídeo inteiro.

## Mapa: o que usar para quê

| Preciso de… | MCP | Alternativa local |
|---|---|---|
| Upscale / restauração | `Magnific: video_upscale`, `Higgsfield: upscale_video` | `scale=...:flags=lanczos` + `unsharp` — melhora pouco, mas não custa nada |
| HDR / faixa dinâmica | `Magnific: video_hdr` | Nenhuma boa. É um caso legítimo de MCP |
| Dublagem / tradução | `Magnific: video_dubbing`, `Higgsfield: dubbing` | Nenhuma. Sem isso, só legenda traduzida |
| Locução TTS | `Magnific: audio_tts`, `audio_tts_direction` | `say`/`espeak` — qualidade de robô |
| Clone de voz | `Higgsfield: create_voice`, `Magnific: audio_voice_change` | Nenhuma |
| Isolar voz do ruído | `Magnific: audio_isolate` | `afftdn`+`anlmdn` no `audio_post.py --clean rescue` — resolve a maioria dos casos |
| Efeito sonoro | `Magnific: audio_sfx_generate` | Biblioteca própria do usuário |
| Trilha original | `Magnific: audio_music_generate` | Biblioteca/licença do usuário |
| B-roll gerado | `Magnific: video_generate`, `Higgsfield: generate_video` | Stock: `Magnific: stock_search`/`stock_download` |
| Lipsync numa foto | `Magnific: video_speak` | Nenhuma |
| Remover fundo (vídeo) | `Higgsfield: remove_background` | `chromakey` — só funciona com fundo verde de verdade |
| Imagem para capa | `Magnific: images_generate` | `thumbnail.py` a partir de um frame real — quase sempre melhor |
| Prever retenção | `Higgsfield: virality_predictor` | Nenhuma. Trate como palpite, não como verdade |
| Publicar no TikTok | `Higgsfield: tiktok_prepare_publish` | Upload manual |
| Música em alta | `Higgsfield: tiktok_music_trending` | Nenhuma |

## ElevenLabs Scribe

É o único serviço externo no caminho **padrão**, usado pelo `transcribe.py`. Vale o custo
(~US$0,40/hora de áudio) porque entrega três coisas que o Whisper local não entrega:

- **Diarização** — quem falou o quê. Sem isso, legenda colorida por falante e corte de
  entrevista ficam no braço.
- **Eventos de áudio** — `(laughs)`, `(applause)`, `(sighs)`. São marcadores de batida
  editorial; o `autocut.py` os usa.
- **Fillers verbatim** — o "né" continua no transcript, então dá para decidir se ele sai ou
  fica. O Whisper normaliza e a decisão desaparece antes de você vê-la.

Sem a chave, o `transcribe.py --engine local` roda `faster-whisper` na CPU. Funciona,
é grátis, e perde as três coisas acima. **Avise qual dos dois rodou** (Regra Dura 19).

## Padrão de uso

Um acelerador entra em **um ponto específico** do pipeline, não substitui o pipeline:

```
origem → [audio_isolate?] → transcribe → autocut → EDL → render
                                                          ↓
                                              [video_upscale?] → entrega
                                                          ↓
                                              [video_dubbing?] → versão PT/EN
```

Encaixar no meio quebra o cache e a reprodutibilidade: um `final.mp4` que passou por um
serviço externo não pode ser regenerado a partir do EDL sozinho. Quando usar, **registre em
`project.md`** qual ferramenta, em que etapa e com que parâmetros — senão a próxima sessão
não consegue refazer.

## Quando NÃO usar

- Para algo que o ffmpeg faz bem: corte, concat, crop, speed, extração de frame. Os MCPs
  têm `video_cut` e `video_concatenate`, mas mandar o arquivo para a nuvem para cortar 2
  segundos é lento, caro e tira o controle de frame exato que o EDL te dá.
- Upscale para "consertar" material mal iluminado ou desfocado. Upscale amplia o que está
  lá; não inventa foco. Regrave ou aceite.
- Geração de b-roll quando existe material real. B-roll gerado chama atenção para si mesmo
  e envelhece rápido.
