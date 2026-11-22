#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "HEALTHBERG · Démonstration avec données fictives uniquement"
echo ""
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 requis : https://www.python.org/downloads/"
  exit 1
fi
if ! command -v tesseract >/dev/null 2>&1; then
  echo "Tesseract est requis pour les scans. Installer : brew install tesseract tesseract-lang"
  exit 1
fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -r requirements.txt
(sleep 2; open http://127.0.0.1:8765) &
python -m app
