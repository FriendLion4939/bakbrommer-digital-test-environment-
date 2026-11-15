#!/bin/sh
# Copies the shipped profiles, scenarios and examples into the data volume
# (never overwriting files that already exist there), then runs the program.
set -e
mkdir -p "$BAKBROMMER_DATA_DIR" "$BAKBROMMER_RUNS_DIR"
cp -rn /app/data/. "$BAKBROMMER_DATA_DIR"/ 2>/dev/null || true
if [ "$1" = "test" ]; then
    shift
    exec env BAKBROMMER_DATA_DIR=/app/data python -m pytest "$@"
fi
exec python -m bakbrommer_twin.cli "$@"
