---
name: manciasolutions-editor-de-video-install
description: Instala a skill ManciaSolutions — Editor de Vídeo no agente atual (Claude Code, Codex, etc.) e prepara ffmpeg + motor de transcrição local, para o usuário começar a editar imediatamente. Nenhuma chave de API é obrigatória.
---

# Instalação — ManciaSolutions Editor de Vídeo

Use este arquivo só na primeira instalação ou reconexão. Para edição do dia a dia, leia `SKILL.md`. Sempre leia `helpers/` — é onde os scripts moram.

## O que você está fazendo

Você está configurando um editor de vídeo conversacional. Depois de instalado, o usuário joga o material bruto em qualquer pasta, roda seu agente (`claude`, `codex` etc.) nela, e diz algo como "edita isso num Reels". Você faz o resto lendo `SKILL.md`.

Três coisas precisam existir nesta máquina:

1. O repositório clonado em algum lugar estável.
2. `ffmpeg` no `$PATH`.
3. As dependências Python instaladas — o motor local (`whisperx`) é o único obrigatório; a chave da ElevenLabs é opcional (só para o motor de nuvem e para narração).

E uma coisa precisa ser verdade sobre o agente atual:

4. Ele consegue descobrir o `SKILL.md` — via um diretório global de skills (`~/.claude/skills/`, `~/.codex/skills/`) ou via importação de `CLAUDE.md`/system prompt.

## Contrato do prompt de instalação

- Faça tudo você mesmo. Só pergunte ao usuário coisas que você não pode gerar — as chaves opcionais, e confirmação antes de `brew install`/`apt install`.
- Prefira um caminho de clone estável como `~/Developer/manciasolutions-editor-de-video` (não `/tmp`, não `~/Downloads`).
- A skill referencia os helpers pelo nome puro (`transcribe.py`, `render.py`). Isso funciona porque `SKILL.md` e `helpers/` viajam juntos — mantenha-os como irmãos ao registrar a skill.
- Depois de instalar, verifique rodando um comando real contra um arquivo real. Não declare sucesso só com checagem de existência de arquivo.
- **Detecte o hardware antes de escolher o modelo Whisper padrão**: GPU NVIDIA disponível → `large-v3` é rápido o suficiente. Só CPU → sugira `--model medium` nas primeiras transcrições, e avise que a primeira transcrição de um vídeo longo pode demorar.

## Passos

### 1. Clonar para um caminho estável

```bash
test -d ~/Developer/manciasolutions-editor-de-video || \
  git clone <URL_DO_SEU_REPOSITORIO> ~/Developer/manciasolutions-editor-de-video
cd ~/Developer/manciasolutions-editor-de-video
```

Se o repositório já existir ali, `git pull --ff-only` e continue.

### 2. Instalar dependências Python

```bash
# Prefira uv se disponível; caia para pip.
command -v uv >/dev/null && uv sync --extra local-transcription || \
  pip install -e ".[local-transcription]"
```

Isso instala `requests`, `librosa`, `matplotlib`, `pillow`, `numpy` (base) + `whisperx`, `torch` (motor local). Sem console scripts — os helpers são invocados diretamente como `python helpers/<nome>.py`.

Se o usuário só quiser o motor ElevenLabs e nunca pretende rodar transcrição local, `pip install -e .` sem o extra `local-transcription` é suficiente e economiza um download grande (torch é pesado).

Diarização local é outro extra, só instale se `--diarize` for pedido:
```bash
pip install -e ".[diarization]"
```

### 3. Instalar ffmpeg

```bash
# macOS
command -v ffmpeg >/dev/null || brew install ffmpeg

# Debian / Ubuntu
command -v ffmpeg >/dev/null || sudo apt-get install -y ffmpeg

# Windows (via winget)
where ffmpeg >nul 2>nul || winget install --id Gyan.FFmpeg
```

`yt-dlp` é opcional, só necessário se o usuário quiser puxar fontes de URLs:
```bash
command -v yt-dlp >/dev/null || pip install yt-dlp
```

### 4. Chaves opcionais (perguntar só se o caso de uso pedir)

Copie `.env.example` para `.env` na raiz do repositório e preencha apenas o que for necessário:

- **`ELEVENLABS_API_KEY`** — só se o usuário quiser `--engine elevenlabs` (diarização de fábrica, tags de evento de áudio) ou `helpers/voiceover.py` (narração por TTS). **Não pergunte isso de cara** — o motor padrão (local) não precisa dela. Pergunte só quando o pedido do usuário claramente precisar de nuvem.
- **`HF_TOKEN`** — só se o usuário quiser `--diarize` no motor local. Peça para criar um token gratuito em huggingface.co/settings/tokens e aceitar os termos do modelo `pyannote/speaker-diarization-3.1`.

```bash
cp .env.example .env
# editar .env manualmente, ou:
echo "ELEVENLABS_API_KEY=sk_..." >> .env   # só se necessário
```

Nunca escreva a chave no `<videos_dir>` do usuário — sempre no `.env` da raiz do repositório da skill.

### 5. Primeiro download de modelo (motor local)

Não precisa fazer isso durante a instalação — o primeiro `transcribe_local.py` real do usuário baixa o modelo Whisper (`large-v3` por padrão, alguns GB) e o modelo de alinhamento do idioma detectado, uma vez, depois fica cacheado. Avise o usuário que a primeira transcrição vai ser mais lenta por causa disso.

### 6. Node.js (só se a sessão for usar HyperFrames ou Remotion)

```bash
node --version  # precisa ser 22+ para HyperFrames
```

HyperFrames e Remotion são instalados lazy, na primeira vez que um slot de animação realmente precisar deles — não instale antecipadamente.

### 7. Registrar a skill no agente

**Claude Code:**
```bash
mkdir -p ~/.claude/skills
ln -sfn ~/Developer/manciasolutions-editor-de-video ~/.claude/skills/manciasolutions-editor-de-video
```

**Codex:**
```bash
mkdir -p ~/.codex/skills
ln -sfn ~/Developer/manciasolutions-editor-de-video ~/.codex/skills/manciasolutions-editor-de-video
```

O symlink é o que faz uma edição no repositório clonado valer imediatamente na próxima sessão do agente — não precisa reinstalar depois de mexer em `SKILL.md` ou em `helpers/`.

### 8. Verificação real

Não declare sucesso sem rodar algo de verdade. Se o usuário tiver um vídeo de teste à mão:

```bash
cd ~/Developer/manciasolutions-editor-de-video
python helpers/transcribe_local.py /caminho/para/um/video_curto.mp4 --language pt
```

Se isso produzir `edit/transcripts/<nome>.json` com uma lista de `words`, a instalação está funcional. Se não houver vídeo de teste, pelo menos confirme:

```bash
python helpers/captions_presets.py     # lista os estilos, sem dependências pesadas
python helpers/format_targets.py --format vertical-reel --source 1920x1080
ffmpeg -version | head -1
```

## Solução de problemas comuns

- **`whisperx` falha ao instalar** — geralmente é uma incompatibilidade de versão do `torch` com o CUDA da máquina. Confira a versão do CUDA (`nvidia-smi`) e instale o `torch` correspondente primeiro, seguindo pytorch.org/get-started/locally, depois `pip install whisperx`.
- **Primeira transcrição muito lenta em CPU** — normal, especialmente com `large-v3`. Sugira `--model medium` ou `--model small` para iteração rápida, subindo para `large-v3` só na passada final.
- **`--diarize` não faz nada** — confira se `HF_TOKEN` está no `.env` e se os termos do modelo pyannote foram aceitos no Hugging Face (é um clique único na página do modelo, não basta ter o token).
