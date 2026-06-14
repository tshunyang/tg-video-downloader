#!/bin/sh
set -eu

APP_DIR="${1:-/opt/tg-video-downloader}"
cd "$APP_DIR"

if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif python3 -m venv .venv >/tmp/tg-video-downloader-venv.log 2>&1; then
    PY=".venv/bin/python"
else
    echo "python3 venv is unavailable; installing dependencies into $APP_DIR/.python"
    mkdir -p "$APP_DIR/.python"
    python3 -m pip install --no-cache-dir --target "$APP_DIR/.python" -r requirements.txt
    exit 0
fi

"$PY" -m pip install --upgrade pip
"$PY" -m pip install --no-cache-dir -r requirements.txt
