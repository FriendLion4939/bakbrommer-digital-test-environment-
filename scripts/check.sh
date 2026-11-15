#!/usr/bin/env bash
# Full quality gate for maintainers: style, types, tests. Run before every commit.
set -e
cd "$(dirname "$0")/.."
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
"$PY" -m ruff check .
"$PY" -m mypy
"$PY" -m pytest "$@"
