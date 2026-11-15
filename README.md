# Bakbrommer Twin

A driving simulator and digital twin for a hybrid three-wheeled cargo moped
(two electric front wheels, petrol rear wheel). You operate it in a web
browser — no programming needed.

> **Status:** under construction, phase by phase. See `docs/PROGRESS.md` for
> what works today. This README is completed and tested step by step in the
> final phase.

## Start

| Where | How |
|---|---|
| Windows PC | Double-click `start.bat` |
| Linux / macOS | `./start.sh` |
| Home server (Docker / Proxmox) | `docker compose up -d --build` |

Then open <http://localhost:8501> (or `http://<server-address>:8501`).

## Run the tests

`./run_tests.sh` (Linux/macOS), `run_tests.bat` (Windows) or
`docker compose run --rm bakbrommer-twin test`.
