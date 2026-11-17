#!/bin/bash
# Aurora Companion - macOS launcher
cd "$(dirname "$0")"
export AURORA_ROOT="$(pwd)"
if [ ! -x .venv/bin/python ]; then
  echo "Aurora is not set up yet - running Setup.command"
  exec ./Setup.command
fi
exec .venv/bin/python Aurora_Companion.py
