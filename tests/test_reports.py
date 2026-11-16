"""Charts, tables, animation and exports."""

import io

import numpy as np
import pandas as pd
import pytest
from helpers import library_run

from bakbrommer_twin import i18n
from bakbrommer_twin.reports import export, tables
from bakbrommer_twin.reports.animation import animation
from bakbrommer_twin.reports.chart_defs import (
    CHARTS,
    CHARTS_BY_KEY,
    DEFAULT_CHARTS,
    REPORT_CHARTS,
    charts_for_channels,
)
from bakbrommer_twin.reports.figures import route_map, thin, time_series
from bakbrommer_twin.sim.result import RunResult


@pytest.fixture(scope="module")
def run() -> RunResult:
    return library_run("slalom")


def test_every_chart_uses_existing_channels_of_one_unit(run: RunResult) -> None:
    english = i18n.load_language("en")
    for chart in CHARTS:
        units = {run.info(name).unit for name in chart.channels}
        assert len(units) == 1, f"chart '{chart.key}' mixes units {units}"
        assert f"chart.{chart.key}" in english, f"add chart.{chart.key} to en.yaml"
        assert len(chart.channels) <= 4
    assert set(DEFAULT_CHARTS) | set(REPORT_CHARTS) <= set(CHARTS_BY_KEY)


def test_every_event_kind_and_end_reason_has_a_text(run: RunResult) -> None:
    english = i18n.load_language("en")
    for result in (run, library_run("emergency_brake_dry"), library_run("steady_circle")):
        assert f"end.{result.meta.end_reason}" in english
        for event in result.meta.events:
            assert f"event.{event.kind}" in english
            assert not event.subject or f"subject.{event.subject}" in english


def test_time_series_shares_the_time_axis(run: RunResult) -> None:
    charts = [CHARTS_BY_KEY[key] for key in DEFAULT_CHARTS]
    figure = time_series([run], charts)
    assert len(figure.data) == sum(len(c.channels) for c in charts)
    bottom = f"x{len(charts)}"  # all charts follow the bottom axis: zoom one, zoom all
    assert figure.layout.xaxis.matches == bottom and figure.layout.xaxis2.matches == bottom
    assert "Wheel loads [N]" in [a.text for a in figure.layout.annotations]
    speed = next(trace for trace in figure.data if trace.name == "Speed")
    assert max(speed.y) == pytest.approx(run["speed"].max() * 3.6, rel=1e-6)  # shown in km/h


def test_runs_share_colours_and_differ_by_line_style(run: RunResult) -> None:
    other = library_run("roundabout")
    figure = time_series([run, other], [CHARTS_BY_KEY["wheel_loads"]], x_channel="distance")
    assert len(figure.data) == 6 + 2  # six signal lines plus two entries of the run key
    first, second = figure.data[0], figure.data[1]  # same signal, two runs
    assert first.line.color == second.line.color
    assert (first.line.dash, second.line.dash) == ("solid", "dash")
    assert first.showlegend and not second.showlegend  # the signal is named once
    key = figure.data[-2:]
    assert [trace.name for trace in key] == [run.meta.name, other.meta.name]
    assert [trace.line.dash for trace in key] == ["solid", "dash"]


def test_long_runs_are_thinned_for_the_browser() -> None:
    values = np.arange(50_000, dtype=float)
    reduced = thin(values, 4000)
    assert len(reduced) <= 4001 and reduced[0] == 0.0 and reduced[-1] == 49_999.0
    assert thin(values[:100]) is not None and len(thin(values[:100])) == 100


def test_custom_channels_are_grouped_by_unit(run: RunResult) -> None:
    charts = charts_for_channels(run, ["speed", "load_fl", "wheel_speed_fl", "load_r"])
    assert [c.channels for c in charts] == [("speed", "wheel_speed_fl"), ("load_fl", "load_r")]
    assert len(time_series([run], charts).data) == 4


def test_route_map_shows_route_path_and_lift_markers(run: RunResult) -> None:
    figure = route_map([run])
    names = [trace.name for trace in figure.data]
    assert names[0] == "Planned route" and run.meta.name in names
    assert any("Wheel lift" in name for name in names)  # the slalom lifts a wheel once
    assert figure.layout.yaxis.scaleanchor == "x"  # true to scale


def test_animation_marks_lifted_wheels(run: RunResult) -> None:
    figure = animation(run, max_frames=60)
    assert 30 <= len(figure.frames) <= 60
    assert len(figure.layout.sliders[0].steps) == len(figure.frames)
    texts = [text for frame in figure.frames for text in (frame.data[-1].text or ())]
    assert "LIFT" in texts
    lift = next(e for e in run.meta.events if e.kind == "wheel_lift")
    frame = min(figure.frames, key=lambda f: abs(float(f.name) - 0.5 * (lift.start + lift.end)))
    assert "LIFT" in frame.data[-1].text
    calm = figure.frames[0]
    assert not calm.data[-1].text
    hover = calm.data[2].text  # first wheel
    assert "front-left wheel" in hover and "Load" in hover and "Torque" in hover


def test_tables(run: RunResult) -> None:
    events = tables.events_table(run)
    assert len(events) == len(run.meta.events)
    assert events["Event"].iloc[0] == "Wheel lifted off the ground"
    summary = tables.metrics_table(run.meta.summary)
    assert "Top speed reached" in set(summary["Quantity"])
    assert tables.format_value(None) == "—" and tables.format_value(12.3456) == "12.35"


def test_comparison_highlights_what_changed() -> None:
    normal = library_run("accel_0_50")
    loaded = library_run("accel_0_50", "full_cargo")
    table = tables.comparison_table([normal, loaded])
    row = table[table["Quantity"] == "Time 0–50 km/h"].iloc[0]
    assert row["notable"] and row["Δ 2"].startswith("+")
    same = table[table["Quantity"] == "Top speed reached"].iloc[0]
    assert not same["notable"]
    changed = tables.parameter_differences([normal, loaded])
    assert set(changed["Parameter"]) == {"mass.cargo.mass", "mass.cargo.height",
                                         "mass.cargo.stack_height"}


def test_csv_export_round_trips(run: RunResult) -> None:
    frame = pd.read_csv(io.StringIO(export.csv_text(run)))
    assert len(frame) == len(run["time"])
    assert frame["speed [km/h]"].iloc[-1] == pytest.approx(run["speed"][-1] * 3.6, rel=1e-4)


def test_html_report_is_self_contained_and_labelled(run: RunResult) -> None:
    page = export.html_report(run)
    assert page.startswith("<!doctype html>") and "Plotly.newPlot" in page
    assert "NOT VALIDATED" in page  # the profile has not been calibrated
    assert "Safety report" in page and "Wheel lifted off the ground" in page
    assert "<script src=" not in page  # plotly is embedded: works without internet


def test_pdf_report_is_a_pdf_with_several_pages(run: RunResult) -> None:
    data = export.pdf_report(run)
    assert data[:5] == b"%PDF-" and len(data) > 20_000
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 3
