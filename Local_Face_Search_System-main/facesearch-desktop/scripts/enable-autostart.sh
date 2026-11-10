#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/.config/autostart"
sed "s|^X-GNOME-Autostart-enabled=.*|X-GNOME-Autostart-enabled=true|" \
  "$HOME/.config/autostart/facesearch.desktop" > "$HOME/.config/autostart/facesearch.desktop.tmp"
mv "$HOME/.config/autostart/facesearch.desktop.tmp" "$HOME/.config/autostart/facesearch.desktop"
echo "FaceSearch will start automatically at login."
