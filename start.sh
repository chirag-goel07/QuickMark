#!/usr/bin/env bash
# QuickMark launcher for Mac / Linux:  ./start.sh   (or: bash start.sh)
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then python3 start.py "$@"
elif command -v python >/dev/null 2>&1; then python start.py "$@"
else echo "Python was not found. Install Python 3.10+ from https://www.python.org/downloads/ and run this again."; exit 1; fi
