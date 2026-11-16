"""The web interface starts and each page renders without an error.

``AppTest`` cannot re-run an ``st.navigation`` app, so the full app is only
started once here; page behaviour is tested by running each page's
``render()`` on its own (see ``_page``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from bakbrommer_twin import paths

APP = str(paths.PROJECT_ROOT / "bakbrommer_twin" / "ui" / "app.py")


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the UI against a copy of data/ so tests never touch real files."""
    shutil.copytree(paths.PROJECT_ROOT / "data", tmp_path / "data")
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv(paths.ENV_RUNS_DIR, str(tmp_path / "runs"))


def _page(module: str) -> AppTest:
    """Run one page module (``bakbrommer_twin.ui.views.<module>``) by itself."""
    script = f"from bakbrommer_twin.ui.views import {module}\n{module}.render()\n"
    app = AppTest.from_string(script, default_timeout=120).run()
    assert not app.exception, [e.value for e in app.exception]
    return app


def test_whole_app_starts() -> None:
    app = AppTest.from_file(APP, default_timeout=120).run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.title, "the default page should draw a title"
    assert any("NOT VALIDATED" in w.value for w in app.sidebar.warning)


def test_parameters_page_renders_and_saves() -> None:
    app = _page("parameters")
    assert app.title[0].value == "Vehicle parameters"
    wheelbase = next(w for w in app.number_input if "Wheelbase" in w.label)
    wheelbase.set_value(1.7).run()
    assert not app.exception
    assert any("1 unsaved change" in c.value for c in app.caption)
    next(b for b in app.button if b.label == "Save").click().run()
    assert not app.exception
    saved = (paths.data_dir() / "profiles" / "default.yaml").read_text(encoding="utf-8")
    assert "geometry.wheelbase" in saved and "1.7" in saved


def test_invalid_value_shows_message_instead_of_crashing() -> None:
    app = _page("parameters")
    wheelbase = next(w for w in app.number_input if "Wheelbase" in w.label)
    wheelbase.set_value(99.0).run()
    assert not app.exception
    assert any("outside the allowed range" in e.value for e in app.error)


def test_switching_profile_updates_calculated_values() -> None:
    app = _page("parameters")
    next(s for s in app.selectbox if s.label == "Profile").select("full_cargo").run()
    assert not app.exception
    tables = [str(d.value) for d in app.dataframe]
    assert any("307" in table for table in tables), "total mass of the full-cargo profile"


def test_home_page() -> None:
    app = _page("home")
    assert app.title[0].value == "Bakbrommer Twin"
    assert any(m.label == "Scenarios" and int(m.value) >= 17 for m in app.metric)


def test_run_page_runs_a_scenario_and_shows_the_result() -> None:
    app = _page("run")
    next(s for s in app.selectbox if s.label == "Scenario").select("slalom").run()
    next(b for b in app.button if b.label == "Run").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert any(h.value.startswith("Slalom") for h in app.header)
    assert any("Safety report (1 events)" in s.value for s in app.subheader)
    assert any("NOT VALIDATED" in w.value for w in app.warning)
    assert len(list(paths.runs_dir().iterdir())) == 1  # saved automatically
    labels = {m.label for m in app.metric}
    assert {"Time to finish", "Top speed reached"} <= labels


def test_results_page_lists_saved_runs() -> None:
    app = _page("results")
    assert any("No saved runs yet" in i.value for i in app.info)
    from helpers import library_run  # a finished run to save

    library_run("slalom").save(paths.runs_dir())
    library_run("roundabout").save(paths.runs_dir())
    app = _page("results")
    table = app.dataframe[0].value
    assert len(table) == 2 and set(table["Scenario"]) == {"Slalom", "Roundabout"}


def test_scenarios_page_previews_and_saves() -> None:
    app = _page("scenarios")
    assert not app.error, [e.value for e in app.error]
    assert any("Route length" in c.value for c in app.caption)
    next(s for s in app.selectbox if s.label == "Scenario").select("__new__").run()
    assert not app.exception and not app.error
    next(i for i in app.text_input if i.label.startswith("File name")).set_value("my_ride").run()
    next(b for b in app.button if b.label == "Save scenario").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert (paths.scenarios_dir() / "my_ride.yaml").exists()


def test_batch_page_renders_and_runs_a_small_sweep() -> None:
    app = _page("batch")
    assert not app.exception
    next(s for s in app.selectbox if s.key == "sweep_scenario").select("accel_0_50").run()
    next(n for n in app.number_input if n.key == "sweep_a_count").set_value(2).run()
    next(b for b in app.button if b.key == "sweep_run").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    assert any(s.key == "sweep_metric" for s in app.selectbox)


def test_import_page_reads_example_csv_and_replays() -> None:
    app = _page("import_replay")
    assert any("Choose a file" in i.value for i in app.info)
    next(s for s in app.selectbox if s.label.startswith("... or try")).select(
        "example_ride_sd.csv").run()
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    assert any("Recording length" in c.value for c in app.caption)
    quality = next(d.value for d in app.dataframe if "Usable [%]" in d.value.columns)
    assert len(quality) == 20 and quality["Impossible values removed"].sum() == 1
    next(b for b in app.button if b.label == "Replay this ride").click().run()
    assert not app.exception, [e.value for e in app.exception]
    fit = next(d.value for d in app.dataframe if "r_squared" in d.value.columns)
    speed = fit[fit["channel"] == "Vehicle speed"].iloc[0]
    assert speed["r_squared"] > 0.8
    assert any("synthetic example" in i.value for i in app.info)


def test_import_page_decodes_can_logs() -> None:
    app = _page("import_replay")
    next(s for s in app.selectbox if s.label.startswith("... or try")).select(
        "example_ride_can.log").run()
    assert not app.exception and not app.error, [e.value for e in app.error]
    assert any("frames read" in c.value and "20 channels" in c.value for c in app.caption)
    quality = next(d.value for d in app.dataframe if "Gaps" in d.value.columns)
    assert quality["Gaps"].sum() == 2  # the hole in the battery message (voltage + current)


def test_calibration_page_fits_and_accepts() -> None:
    from test_replay_calibration import _short  # a short piece of the example recording

    _short(12.0).save(paths.recordings_dir(), "short_example")
    app = _page("calibration")
    assert not app.exception
    picks = {m.label: m for m in app.multiselect}
    picks["Parameters to fit"].set_value(["battery.internal_resistance"])
    picks["Measured channels to match"].set_value(["battery_voltage"])
    app.run()
    next(s for s in app.slider if s.label == "Simulation budget").set_value(6).run()
    next(b for b in app.button if b.label == "Calibrate").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    values = next(d.value for d in app.dataframe if "Fitted" in d.value.columns)
    assert values["Before"].iloc[0] == 60.0 and values["Fitted"].iloc[0] > 62.0
    next(b for b in app.button if b.label.startswith("Accept")).click().run()
    assert any("accepted" in s.value for s in app.success)
