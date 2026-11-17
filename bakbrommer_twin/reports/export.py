"""Export a run: CSV of all signals, printable HTML report, PDF report."""

from __future__ import annotations

import html
import io
import re
import unicodedata
from collections.abc import Sequence

import matplotlib

matplotlib.use("Agg")  # draw without a screen (server use)

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from bakbrommer_twin.i18n import t
from bakbrommer_twin.reports import style, tables
from bakbrommer_twin.reports.chart_defs import CHARTS_BY_KEY, REPORT_CHARTS, ChartDef
from bakbrommer_twin.reports.figures import chart_title, route_map, thin, time_series
from bakbrommer_twin.sim.result import RunResult

_A4 = (8.27, 11.69)  # inches
_CHARTS_PER_PAGE = 4
_TABLE_ROWS_PER_PAGE = 38
_CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;color:#0b0b0b;margin:24px;max-width:1100px}
h1{font-size:24px;margin-bottom:4px} h2{font-size:18px;margin-top:28px}
table{border-collapse:collapse;font-size:13px;margin:8px 0}
td,th{border:1px solid #e6e5e0;padding:4px 10px;text-align:left}
th{background:#f4f3ef} .warn{background:#fff4d6;border:1px solid #fab219;padding:10px;margin:12px 0}
.meta{color:#52514e;font-size:13px}
@media print{.plotly-graph-div{break-inside:avoid} h2{break-after:avoid}}
"""


def file_stem(result: RunResult) -> str:
    """Run name as a plain file name, e.g. ``City_stop-and-go_-_Default_bakbrommer``.

    Only ASCII letters, digits, ``-``, ``_`` and ``.`` are kept, so every browser
    and file system accepts it (an em dash becomes ``-``, accents are dropped).
    """
    text = result.meta.name.replace("—", "-").replace("–", "-")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return stem or "run"


def csv_text(result: RunResult) -> str:
    """All recorded signals as CSV text (friendly units, one row per sample)."""
    return str(result.to_dataframe().to_csv(index=False, float_format="%.6g"))


def _report_charts(result: RunResult) -> list[ChartDef]:
    return [CHARTS_BY_KEY[key] for key in REPORT_CHARTS
            if all(name in result.data for name in CHARTS_BY_KEY[key].channels)]


def _meta_lines(result: RunResult) -> list[str]:
    meta = result.meta
    return [
        f"{t('report.scenario')}: {meta.scenario_name}",
        f"{t('report.profile')}: {meta.profile_name or '—'}",
        f"{t('report.controller')}: {meta.controller}",
        f"{t('report.created')}: {meta.created}",
        f"{t('report.ended')}: {t('end.' + meta.end_reason)} "
        f"({meta.duration:.1f} s, {t('report.time_step')} {meta.time_step * 1000:g} ms)",
    ]


def _frame_html(frame: pd.DataFrame) -> str:
    return str(frame.to_html(index=False, border=0, escape=True))


def html_report(result: RunResult) -> str:
    """A self-contained, printable HTML page for one run (charts are interactive)."""
    meta = result.meta
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>"
             f"{html.escape(meta.name)}</title><style>{_CSS}</style></head><body>",
             f"<h1>{html.escape(meta.name)}</h1>",
             "<div class='meta'>" + "<br>".join(html.escape(x) for x in _meta_lines(result))
             + "</div>"]
    if not meta.validated:
        parts.append(f"<div class='warn'>{html.escape(t('app.not_validated'))}</div>")
    if meta.metrics:
        parts += [f"<h2>{t('report.scenario_results')}</h2>",
                  _frame_html(tables.metrics_table(meta.metrics))]
    parts += [f"<h2>{t('report.safety')}</h2>",
              _frame_html(tables.events_table(result)) if meta.events
              else f"<p>{t('report.no_events')}</p>",
              f"<h2>{t('report.summary')}</h2>", _frame_html(tables.metrics_table(meta.summary)),
              f"<h2>{t('report.route')}</h2>",
              route_map([result]).to_html(full_html=False, include_plotlyjs=True),
              f"<h2>{t('report.charts')}</h2>",
              time_series([result], _report_charts(result)).to_html(
                  full_html=False, include_plotlyjs=False),
              "</body></html>"]
    return "\n".join(parts)


def _text_page(pdf: PdfPages, title: str, lines: Sequence[str]) -> None:
    figure = Figure(figsize=_A4)
    figure.text(0.08, 0.95, title, fontsize=15, weight="bold", va="top")
    figure.text(0.08, 0.91, "\n".join(lines), fontsize=9, va="top", family="monospace",
                linespacing=1.35)
    pdf.savefig(figure)  # type: ignore[no-untyped-call]


def _table_lines(frame: pd.DataFrame) -> list[str]:
    return frame.to_string(index=False, max_colwidth=46).splitlines() if len(frame) else []


def pdf_report(result: RunResult) -> bytes:
    """A printable PDF report for one run (A4, static charts)."""
    meta = result.meta
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        head = _meta_lines(result)
        if not meta.validated:
            head += ["", *_wrap(t("app.not_validated"), 90)]
        if meta.metrics:
            head += ["", t("report.scenario_results"), *_table_lines(
                tables.metrics_table(meta.metrics))]
        head += ["", t("report.summary"), *_table_lines(tables.metrics_table(meta.summary))]
        _text_page(pdf, meta.name, head)
        events = _table_lines(tables.events_table(result)) or [t("report.no_events")]
        for start in range(0, len(events), _TABLE_ROWS_PER_PAGE * 2):
            _text_page(pdf, t("report.safety"), events[start:start + _TABLE_ROWS_PER_PAGE * 2])
        charts = _report_charts(result)
        time = thin(result["time"])
        for start in range(0, len(charts), _CHARTS_PER_PAGE):
            page = charts[start:start + _CHARTS_PER_PAGE]
            figure, axes = plt.subplots(len(page), 1, figsize=_A4, sharex=True, squeeze=False)
            for axis, chart in zip(axes[:, 0], page, strict=True):
                for colour, name in zip(style.SERIES, chart.channels, strict=False):
                    axis.plot(time, thin(result.display(name)), color=colour, linewidth=1.2,
                              label=result.info(name).label)
                axis.set_title(chart_title(chart, result), fontsize=10, loc="left")
                axis.grid(color=style.GRID, linewidth=0.6)
                if len(chart.channels) > 1:
                    axis.legend(fontsize=7, loc="upper right", frameon=False)
                axis.tick_params(labelsize=8)
            axes[-1, 0].set_xlabel(f"{result.info('time').label} [s]", fontsize=9)
            figure.tight_layout()
            pdf.savefig(figure)
            plt.close(figure)
    return buffer.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return [*lines, line]
