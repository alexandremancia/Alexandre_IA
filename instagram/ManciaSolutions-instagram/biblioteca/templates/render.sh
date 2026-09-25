#!/usr/bin/env bash
# Renderiza os slides de um carrossel em PNG quadrado 1080x1080.
#
#   bash ../../biblioteca/templates/render.sh carrossel.html instagram
#
# Usa o Chromium que o Playwright já baixou nesta máquina, sem instalar
# pacote npm nenhum. Cada slide é isolado pela query ?s=N (ver isolar.js).
set -euo pipefail

HTML="${1:-carrossel.html}"
SAIDA="${2:-instagram}"
LARGURA=1080
ALTURA=${ALTURA:-1080}

if [ ! -f "$HTML" ]; then
  echo "arquivo não encontrado: $HTML" >&2
  exit 1
fi

CHROME=""
for c in \
  "$HOME/AppData/Local/ms-playwright"/chromium-*/chrome-win64/chrome.exe \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  "${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"/chromium \
  "${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"/chromium-*/chrome-linux/chrome \
  "$HOME/.cache/ms-playwright"/chromium-*/chrome-linux/chrome \
  /usr/bin/chromium /usr/bin/chromium-browser /usr/bin/google-chrome
do
  [ -x "$c" ] && CHROME="$c" && break
done

if [ -z "$CHROME" ]; then
  echo "Chromium não encontrado. Rode: npx playwright install chromium" >&2
  exit 1
fi

TOTAL=$(grep -c 'class="slide' "$HTML")
if [ "$TOTAL" -lt 1 ]; then
  echo "nenhum elemento .slide em $HTML" >&2
  exit 1
fi

mkdir -p "$SAIDA"
ABS=$(cd "$(dirname "$HTML")" && pwd)/$(basename "$HTML")
URL_BASE="file:///$(echo "$ABS" | sed 's|^/\([a-zA-Z]\)/|\1:/|')"

echo "chromium: $CHROME"
echo "slides:   $TOTAL"

for i in $(seq 1 "$TOTAL"); do
  N=$(printf "%02d" "$i")
  PNG="$SAIDA/slide-$N.png"
  "$CHROME" \
    --headless=new \
    ${CHROME_EXTRA_FLAGS:-} \
    --disable-gpu \
    --hide-scrollbars \
    --force-device-scale-factor=1 \
    --default-background-color=00000000 \
    --virtual-time-budget=4000 \
    --window-size=$LARGURA,$ALTURA \
    --screenshot="$(echo "$(pwd)/$PNG" | sed 's|^/\([a-zA-Z]\)/|\1:/|')" \
    "${URL_BASE}?s=$i" >/dev/null 2>&1
  echo "  $PNG"
done

echo "pronto: $TOTAL slides em $SAIDA/"
