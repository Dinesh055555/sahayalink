#!/usr/bin/env bash
# One command to start SahayaLink. Run from this folder:  bash run.sh
set -e
cd "$(dirname "$0")"

echo "==> Installing dependencies (first run only)..."
pip install -q -r requirements.txt

if [ ! -f sahayalink.db ]; then
  echo "==> Building the database from the analysis output..."
  python3 seed.py
fi

echo "==> Starting SahayaLink at http://127.0.0.1:8000"
echo "    Open that address in your browser. Press Ctrl+C to stop."
echo "    Logins:  asha13 / 1234   |   cho3 / 4321   |   supervisor / 0000"
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
