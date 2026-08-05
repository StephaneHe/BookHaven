#!/usr/bin/env bash
# Lance BookHaven sur le port 8097 depuis WSL Ubuntu-20.04
# Prérequis: venv créé avec pip install -r requirements.txt
set -e
PROJ="/mnt/i/Dev/BookHaven"
VENV="$PROJ/.venv"

cd "$PROJ"

if [ ! -d "$VENV" ]; then
  echo "[BookHaven] création du venv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r requirements.txt
fi

export BOOKHAVEN_PORT=8097
export BOOKS_ROOT=/mnt/h/Books
export BOOKHAVEN_DATA_DIR=/mnt/i/Dev/BookHaven/data

exec "$VENV/bin/python" bookhaven.py
