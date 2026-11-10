#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export FACESEARCH_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/facesearch"
exec npm --prefix "$APP_DIR/desktop" start -- "$@"
