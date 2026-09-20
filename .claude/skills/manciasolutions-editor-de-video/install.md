# Instalação

## Rápido

```bash
git clone https://github.com/alexandremancia/Alexandre_IA ~/Developer/Alexandre_IA
bash ~/Developer/Alexandre_IA/.claude/skills/manciasolutions-editor-de-video/install.sh
```

O script instala as dependências Python, mostra quais camadas de capacidade ficaram
disponíveis e cria o symlink em `~/.claude/skills/`. É idempotente — rode de novo à vontade.

**O symlink é o ponto.** A pasta de skills aponta para o seu clone, então qualquer edição
que você fizer aqui já vale na próxima sessão do agente. Não existe "reinstalar".

## Manual

### 1. ffmpeg (obrigatório)

```bash
brew install ffmpeg          # macOS
sudo apt-get install ffmpeg  # Debian/Ubuntu
```

Sem `ffmpeg` e `ffprobe` no PATH, nada funciona. Confira com `ffmpeg -version`.

### 2. Dependências Python

```bash
cd .claude/skills/manciasolutions-editor-de-video
uv pip install -e ".[full]"      # ou: pip install -e ".[full]"
```

O extra `full` traz `librosa` (batidas), `opencv-python-headless` (rastreio de rosto),
`faster-whisper` (transcrição local) e `matplotlib`. Sem ele, só o essencial é instalado
e a skill cai para os caminhos degradados — que funcionam, mas entregam menos.

Extras individuais: `.[music]`, `.[vision]`, `.[local-asr]`, `.[viz]`, `.[animations]`.

### 3. Chave da ElevenLabs (opcional, recomendado)

```bash
cp .env.example .env
# edite .env e preencha ELEVENLABS_API_KEY
```

Sem a chave, a transcrição roda local com `faster-whisper`. Funciona e é grátis, mas perde
diarização (quem falou), eventos de áudio (`(laughs)`, `(applause)`) e fillers verbatim.
Para vídeo de uma pessoa só, a diferença é pequena. Para entrevista e podcast, é grande.

Nunca escreva o `.env` dentro da pasta de vídeos do usuário — ele fica aqui, na skill.

### 4. Symlink

```bash
ln -sfn "$(pwd)" ~/.claude/skills/manciasolutions-editor-de-video
```

### 5. Opcionais, só no primeiro uso

```bash
brew install yt-dlp                 # baixar vídeo de fonte online
npx --yes hyperframes --version     # animações HTML/CSS/GSAP (Node 22+)
npx create-video@latest             # animações Remotion (dentro do slot, nunca na raiz)
pip install manim                   # diagramas formais
```

## Verificar

```bash
python helpers/grade.py --list-presets
python helpers/captions.py --list-styles
python helpers/audio_post.py --list-chains
python -m pytest tests/ -q          # da raiz do repositório
```

## Usar

No Claude Code, dentro da pasta onde estão seus vídeos:

```
/manciasolutions-editor-de-video
```

Ou simplesmente descreva o que quer ("corta esse podcast em 3 reels verticais com legenda")
— a skill dispara pela descrição.

## Atualizar

```bash
git pull
bash install.sh     # só para repuxar dependências novas
```

Suas customizações no `SKILL.md` e nos helpers são commits seus. Se pretende manter
modificações grandes, trabalhe numa branch própria para o `git pull` não conflitar.
