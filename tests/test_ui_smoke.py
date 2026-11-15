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
    """Run one page module (``bakbrommer_twin.ui.pages.<module>``) by itself."""
    script = f"from bakbrommer_twin.ui.pages import {module}\n{module}.render()\n"
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
