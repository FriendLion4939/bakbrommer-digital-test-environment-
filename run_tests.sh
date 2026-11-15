#!/usr/bin/env bash
# Runs every automated test.  Usage:  ./run_tests.sh   (extra arguments go to pytest)
set -e
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
exec "$PY" -m pytest "$@"
