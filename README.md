# Alexandre_IA

Skills próprias para o Claude Code.

## `/manciasolutions-editor-de-video`

Editor de vídeo completo, por conversa. Você descreve o que quer em português; o agente
transcreve, propõe um corte, você confirma, ele executa, verifica sozinho e itera.

Derivado do [`browser-use/video-use`](https://github.com/browser-use/video-use) (MIT), com o
que faltava para chegar perto de um editor de verdade: legenda karaokê animada, remoção
automática de silêncio e vício de linguagem, reenquadramento vertical seguindo o sujeito,
sincronia com a batida, ducking de trilha, transições, punch-in, speed ramp, QC automatizado
e geração de capa.

### Instalar

```bash
git clone https://github.com/alexandremancia/Alexandre_IA ~/Developer/Alexandre_IA
bash ~/Developer/Alexandre_IA/.claude/skills/manciasolutions-editor-de-video/install.sh
```

O script instala as dependências, mostra quais camadas de capacidade ficaram disponíveis e
cria o symlink em `~/.claude/skills/`. **Editar o clone é editar a skill** — o symlink reflete
na hora, não existe "reinstalar". Detalhes e instalação manual em
[`install.md`](.claude/skills/manciasolutions-editor-de-video/install.md).

Requisito duro: `ffmpeg` e `ffprobe` no PATH. Sem eles, nada funciona.

### Usar

Abra o Claude Code na pasta onde estão seus vídeos e descreva o que quer:

> corta esse podcast em 3 reels verticais com legenda amarela

Ou chame pelo nome: `/manciasolutions-editor-de-video`.

### Camadas

A skill degrada de forma declarada — e sempre diz em qual camada está rodando.

| Camada | Requer | Habilita |
|---|---|---|
| Base | ffmpeg | Corte, grade, transição, punch, speed, reframe por movimento, mix, QC, capa |
| Transcrição local | `faster-whisper` | Auto-cut e legenda, sem diarização nem evento de áudio |
| Transcrição completa | `ELEVENLABS_API_KEY` | O mesmo com diarização, `(laughs)` e fillers verbatim |
| Visão | `opencv-python-headless` | Reframe seguindo rosto, score de rosto na capa |
| Música | `librosa` | BPM e batidas melhores (há fallback em numpy) |
| Aceleradores | MCP Magnific / Higgsfield | Upscale, dublagem, TTS, b-roll, SFX, publicação |

Nada acima da Base é obrigatório.

### Testes

```bash
python -m pytest tests/ -q
```

Cobrem a matemática que erra em silêncio: offset da timeline de saída, `-ss`/`-t` na extração,
handles de transição, geometria uniforme do concat, margem por aspecto, quebra de linha,
suavização do reframe e parsing de legenda.

### Licença

MIT, herdada do `video-use`. Veja
[`NOTICE`](.claude/skills/manciasolutions-editor-de-video/NOTICE) para o que foi herdado,
o que foi modificado e o que foi escrito do zero.
