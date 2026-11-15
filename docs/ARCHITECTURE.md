# Architecture

A map of the code for maintainers. Decisions and their reasons are in
`docs/PLAN.md`; equations are in `docs/PHYSICS.md`; step-by-step recipes are
in `docs/HOW_TO_CHANGE.md`.

## Module map

| Path | What it does |
|---|---|
| `bakbrommer_twin/params/units.py` | The only unit conversion table (friendly unit ↔ SI). |
| `bakbrommer_twin/params/types.py` | `ParamDef`, `Status`, `Kind`. |
| `bakbrommer_twin/params/registry.py` | `Registry`: declares and validates parameters. |
| `bakbrommer_twin/params/definitions/*.py` | **Every parameter is declared here**, one file per category. |
| `bakbrommer_twin/params/paramset.py` | `ParamSet`: one complete set of values (SI) with typed accessors. |
| `bakbrommer_twin/params/profile.py` | Profiles as YAML: load/save, inheritance, history, compare. |
| `bakbrommer_twin/params/derived.py` | Calculated values shown in the UI (mass, balance, stability…). |
| `bakbrommer_twin/physics/mass.py` | Mass properties from components; static loads; rigid-vehicle stability limits. |
| `bakbrommer_twin/ui/app.py` | Web interface entry point and page list. |
| `bakbrommer_twin/ui/i18n.py`, `ui/translations/en.yaml` | All interface texts. |
| `bakbrommer_twin/ui/state.py` | Session state helpers (working profile). |
| `bakbrommer_twin/ui/param_form.py` | Widgets generated from the registry. |
| `bakbrommer_twin/ui/pages/parameters.py` | Parameter editor page. |
| `bakbrommer_twin/paths.py` | Where data and results are stored. |
| `bakbrommer_twin/cli.py` | Command line (`bakbrommer-twin ui`, `params`, `derived`). |
| `data/profiles/*.yaml` | Vehicle profiles. |
| `tests/` | pytest suite; `test_project_rules.py` enforces the maintainability rules. |

(The table grows with each phase; see `docs/PROGRESS.md`.)

## How a parameter travels

```
params/definitions/*.py ──► REGISTRY ──► ParamSet (defaults)
                                           ▲
data/profiles/*.yaml ── ProfileStore.load ─┘ (base profile first, then overrides)
                                           │
              physics / control / sensors read values in their constructors
              UI builds its form from REGISTRY and edits the ParamSet
```

## Where does a change belong?

| I want to… | Go to |
|---|---|
| add or change a parameter | `params/definitions/<category>.py` |
| add a unit | `params/units.py` |
| change how mass/CoG is computed | `physics/mass.py` |
| add a calculated value to the UI | `params/derived.py` |
| change a UI text | `ui/translations/en.yaml` |
| add a UI page | `ui/pages/` + `PAGES` in `ui/app.py` |
