#!/usr/bin/env bash
# Instalador da skill ManciaSolutions — Editor de Vídeo.
# Idempotente: pode rodar de novo sem quebrar nada.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="manciasolutions-editor-de-video"
TARGET="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/$SKILL_NAME"

echo "── ManciaSolutions — Editor de Vídeo ──"
echo "origem:  $SKILL_DIR"
echo "destino: $TARGET"
echo

# 1. ffmpeg -----------------------------------------------------------------
if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then
  echo "✓ ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3)"
else
  echo "✗ ffmpeg/ffprobe não encontrados — SEM ELES NADA FUNCIONA."
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "  instale com:  brew install ffmpeg"
  else
    echo "  instale com:  sudo apt-get install ffmpeg"
  fi
  exit 1
fi

# 2. Python ------------------------------------------------------------------
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null; then
  echo "✗ python3 não encontrado"; exit 1
fi
echo "✓ $("$PY" --version)"

echo
echo "→ instalando dependências Python"

# Ordem: uv dentro de um venv (rápido) → pip → pip sem os extras pesados.
# Falhar aqui NÃO aborta o install: só o ffmpeg é requisito duro, e o resto
# apenas liga camadas. Melhor terminar com o symlink no lugar e dizer o que
# ficou faltando do que largar a instalação pela metade.
deps_ok=0
if command -v uv >/dev/null && [[ -n "${VIRTUAL_ENV:-}" ]]; then
  (cd "$SKILL_DIR" && uv pip install -q -e ".[full]") && deps_ok=1
fi
if [[ $deps_ok -eq 0 ]]; then
  "$PY" -m pip install -q -e "$SKILL_DIR[full]" 2>/dev/null && deps_ok=1
fi
if [[ $deps_ok -eq 0 ]]; then
  echo "  extras não instalaram; tentando só o essencial"
  "$PY" -m pip install -q -e "$SKILL_DIR" 2>/dev/null && deps_ok=2
fi
case $deps_ok in
  1) echo "✓ dependências instaladas (com extras)" ;;
  2) echo "⚠ só o essencial instalou — camadas de visão/música/ASR local ficam de fora" ;;
  0) echo "⚠ não consegui instalar as dependências Python."
     echo "  Rode à mão:  $PY -m pip install -e \"$SKILL_DIR[full]\""
     echo "  A skill ainda funciona na camada base (ffmpeg)." ;;
esac

# 3. O que ficou disponível --------------------------------------------------
echo
echo "── camadas disponíveis ──"
SKILL_DIR="$SKILL_DIR" "$PY" - <<'PYCHECK'
import importlib, os
from pathlib import Path

def has(mod):
    try:
        importlib.import_module(mod); return True
    except Exception:
        return False

def scribe_key() -> bool:
    if os.environ.get("ELEVENLABS_API_KEY"):
        return True
    env = Path(os.environ.get("SKILL_DIR", ".")) / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("ELEVENLABS_API_KEY="):
                return bool(line.split("=", 1)[1].strip().strip('"').strip("'"))
    return False

print("  base (ffmpeg)            ✓  corte, grade, transição, reframe por movimento, QC, capa")
print(f"  visão (opencv)           {'✓' if has('cv2') else '—'}  auto-reframe seguindo rosto")
print(f"  música (librosa)         {'✓' if has('librosa') else '—'}  BPM e batidas (há fallback em numpy)")
print(f"  ASR local (whisper)      {'✓' if has('faster_whisper') else '—'}  transcrição sem chave")
print(f"  ASR completo (Scribe)    {'✓' if scribe_key() else '—'}  diarização + eventos de áudio + fillers")

# O OpenCV 5 removeu os Haar cascades: sem o modelo YuNet, o reframe só segue
# movimento. Vale dizer isso no install, não na primeira vez que o usuário
# tentar reenquadrar um talking head.
if has("cv2"):
    import cv2
    modelo = Path.home() / ".cache" / "manciasolutions" / "face_detection_yunet.onnx"
    if not hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "FaceDetectorYN") and not modelo.exists():
        print()
        print(f"  Nota: OpenCV {getattr(cv2, '__version__', '5.x')} não traz Haar cascade.")
        print(f"  Para rastrear ROSTO no reframe (em vez de só movimento):")
        print(f"    mkdir -p {modelo.parent} && \\\\")
        print(f"    curl -L -o {modelo} \\\\")
        print(f"      https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx")
PYCHECK

# 4. .env --------------------------------------------------------------------
if [[ ! -f "$SKILL_DIR/.env" ]]; then
  cat > "$SKILL_DIR/.env.example" <<'ENVEOF'
# Transcrição com diarização, eventos de áudio e fillers verbatim.
# Sem esta chave a skill usa faster-whisper local (grátis, sem diarização).
ELEVENLABS_API_KEY=
ENVEOF
  echo
  echo "→ criado .env.example — copie para .env e preencha se for usar o Scribe"
fi

# 5. symlink -----------------------------------------------------------------
echo
mkdir -p "$(dirname "$TARGET")"
if [[ -L "$TARGET" ]]; then
  CURRENT="$(readlink "$TARGET")"
  if [[ "$CURRENT" == "$SKILL_DIR" ]]; then
    echo "✓ symlink já aponta para cá"
  else
    ln -sfn "$SKILL_DIR" "$TARGET"
    echo "✓ symlink reapontado (era $CURRENT)"
  fi
elif [[ -e "$TARGET" ]]; then
  echo "✗ $TARGET já existe e NÃO é um symlink."
  echo "  Mova ou remova antes de continuar — não vou apagar nada sozinho."
  exit 1
else
  ln -s "$SKILL_DIR" "$TARGET"
  echo "✓ symlink criado"
fi

echo
echo "Pronto. Abra o Claude Code e chame:  /$SKILL_NAME"
echo "Editar a skill = editar os arquivos em $SKILL_DIR (o symlink reflete na hora)."
