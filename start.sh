#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="venv"
ACTIVATE_PATH="$VENV_DIR/bin/activate"
VENV_PY="$VENV_DIR/bin/python3"


echo "Starting Marketing Command Centre Discord Bot..."
echo

# Check if Python 3 is installed
if ! command -v python3 >/dev/null 2>&1; then
	  echo "[ERROR] Python 3 is not installed!"
	    echo "Please install Python 3.8+ from https://python.org"
	      exit 1
fi

# .env present?
if [ ! -f ".env" ]; then
	  echo "[ERROR] .env file not found!"
	    echo "Please copy .env.example to .env and add your bot token and server ID."
	      exit 1
fi

# Create venv if missing
if [ ! -d "venv" ]; then
	  echo "[INFO] Creating virtual environment..."
	    python3 -m venv venv
fi

# Activate
echo "[INFO] Activating virtual environment..."
# shellcheck disable=SC1090
source "$ACTIVATE_PATH"

# Install/update deps only if requirements changed or venv is new
if [ ! -f "$VENV_DIR/.deps_installed" ] || [ "requirements.txt" -nt "$VENV_DIR/.deps_installed" ]; then
    echo "[INFO] Installing/updating dependencies..."
    "$VENV_PY" -m pip install --upgrade pip
    "$VENV_PY" -m pip install -r requirements.txt
    touch "$VENV_DIR/.deps_installed"
else
    echo "[INFO] Dependencies up to date, skipping install"
fi

echo "[INFO] Environment ready!"
echo

echo "[INFO] Starting bot..."
"$VENV_PY" main.py