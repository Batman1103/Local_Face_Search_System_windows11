#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/facesearch"
VENV="$DATA_DIR/python-env"

command -v python3 >/dev/null || { echo "Python 3 is required."; exit 1; }
command -v node >/dev/null || { echo "Node.js is required for the first installation."; exit 1; }
command -v npm >/dev/null || { echo "npm is required for the first installation."; exit 1; }

mkdir -p "$DATA_DIR"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$APP_DIR/backend/requirements.txt"

(cd "$APP_DIR/frontend" && npm install && npm run build)
(cd "$APP_DIR/desktop" && npm install)

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/facesearch.desktop" <<EOF
[Desktop Entry]
Name=FaceSearch
Comment=Private local face search
Exec=$APP_DIR/scripts/run-linux.sh
Icon=applications-graphics
Terminal=false
Type=Application
Categories=Graphics;Photography;Utility;
StartupWMClass=FaceSearch
EOF

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/facesearch.desktop" <<EOF
[Desktop Entry]
Name=FaceSearch
Comment=Start FaceSearch in the background at login
Exec=$APP_DIR/scripts/run-linux.sh --background
Terminal=false
Type=Application
X-GNOME-Autostart-enabled=false
EOF

chmod +x "$APP_DIR/scripts/run-linux.sh"
echo
printf 'FaceSearch installed. Launch it from your Applications menu or run:\n  %s\n' "$APP_DIR/scripts/run-linux.sh"
printf '\nData/index location: %s\n' "$DATA_DIR"
printf 'Autostart file is installed but disabled by default.\n'
