#!/usr/bin/env bash
# Startup command used by the hosting service (Render).
# Builds the database on first boot, then starts the web server on the host's port.
set -e
cd "$(dirname "$0")"
if [ ! -f sahayalink.db ]; then
  python3 seed.py
fi
exec python3 -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
