#!/bin/bash
# Aurora Companion - macOS / Linux setup (double-click, or run ./Setup.command)
cd "$(dirname "$0")"
PY=""
for c in python3.11 python3.12 python3.10 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys,tkinter,venv; sys.exit(0 if (3,10)<=sys.version_info[:2]<(3,14) else 1)" 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10-3.13 (with Tk) is needed. Install it from https://www.python.org/downloads/macos/"
  echo "then double-click Setup.command again."
  read -p "Press Enter to close..."; exit 1
fi
echo "Using $($PY --version)"
"$PY" setup/aurora_setup.py "$@"
read -p "Press Enter to close..."
