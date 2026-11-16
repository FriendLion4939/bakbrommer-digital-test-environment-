"""Tables shared by the UI and the exported reports (pandas data frames)."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from bakbrommer_twin.i18n import t
from bakbrommer_twin.sim.result import Metric, RunResult

NOTABLE_CHANGE = 0.05  # relative difference above which a comparison row is highlighted


def format_value(value: float | None) -> str:
    """A number with four significant digits, or a dash when unknown."""
    return "—" if value is None else f"{value:.4g}"


def metrics_table(metrics: Sequence[Metric]) -> pd.DataFrame:
    """Label / value / unit rows for a list of metrics."""
    return pd.DataFrame({
        t("table.quantity"): [m.label for m in metrics],
        t("table.value"): [format_value(m.display()) for m in metrics],
        t("table.unit"): [m.unit if m.unit != "-" else "" for m in metrics],
    })


def events_table(result: RunResult) -> pd.DataFrame:
    """The safety report: one row per event, in time order."""
    events = result.meta.events
    return pd.DataFrame({
        t("table.start"): [f"{e.start:.2f}" for e in events],
        t("table.end"): [f"{e.end:.2f}" for e in events],
        t("table.duration"): [f"{e.end - e.start:.2f}" for e in events],
        t("table.event"): [t(f"event.{e.kind}") for e in events],
        t("table.where"): [t(f"subject.{e.subject}") if e.subject else "" for e in events],
        t("table.peak"): [f"{e.peak:.3g} {e.unit}".strip() for e in events],
    })


def comparison_table(results: Sequence[RunResult]) -> pd.DataFrame:
    """Metrics of several runs side by side, with the change relative to the first run.

    The column ``notable`` is True where a run differs from the first by more
    than 5 %, so the UI can highlight the row.
    """
    first = results[0]
    keys = [m.key for m in (*first.meta.metrics, *first.meta.summary)]
    by_run = [{m.key: m for m in (*r.meta.metrics, *r.meta.summary)} for r in results]
    rows = []
    for key in dict.fromkeys(keys):
        base = by_run[0][key]
        row: dict[str, object] = {t("table.quantity"): base.label,
                                  t("table.unit"): base.unit if base.unit != "-" else ""}
        notable = False
        for index, (result, metrics) in enumerate(zip(results, by_run, strict=True)):
            metric = metrics.get(key)
            shown = metric.display() if metric is not None else None
            row[f"{index + 1}: {result.meta.name}"] = format_value(shown)
            if index == 0:
                continue
            reference = base.display()
            if shown is None or reference is None:
                row[f"Δ {index + 1}"] = "—" if shown is None and reference is None else "≠"
                notable = notable or (shown is None) != (reference is None)
                continue
            delta = shown - reference
            relative = delta / abs(reference) if reference != 0 else (0.0 if delta == 0 else 1.0)
            row[f"Δ {index + 1}"] = f"{delta:+.3g} ({relative:+.0%})"
            notable = notable or abs(relative) > NOTABLE_CHANGE
        row["notable"] = notable
        rows.append(row)
    return pd.DataFrame(rows)


def parameter_differences(results: Sequence[RunResult]) -> pd.DataFrame:
    """Parameters whose value differs between the runs (friendly units)."""
    names = [name for name in results[0].meta.params
             if len({repr(r.meta.params.get(name)) for r in results}) > 1]
    data: dict[str, list[object]] = {t("table.parameter"): list(names)}
    for index, result in enumerate(results):
        data[f"{index + 1}: {result.meta.name}"] = [str(result.meta.params.get(n)) for n in names]
    return pd.DataFrame(data)
