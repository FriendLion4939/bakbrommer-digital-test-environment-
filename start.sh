#!/usr/bin/env bash
# One-click start for Linux / macOS.  Usage:  ./start.sh
# First run: creates a private Python environment in .venv and installs the
# program (needs internet once). Later runs start immediately.
set -e
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "Python 3.12 or newer is required. Install it from https://www.python.org/downloads/"
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "First start: installing (this takes a few minutes)..."
    "$PYTHON" -m venv .venv
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet -e ".[dev]"
fi

echo "Starting Bakbrommer Twin. Open http://localhost:8501 in your browser."
echo "Press Ctrl+C in this window to stop."
exec .venv/bin/python -m bakbrommer_twin.cli ui "$@"
