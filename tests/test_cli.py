"""The terminal commands named in README.md and CLAUDE.md work."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bakbrommer_twin import cli, paths


@pytest.fixture(autouse=True)
def _isolated_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a copy of data/ and an empty runs folder."""
    shutil.copytree(paths.PROJECT_ROOT / "data", tmp_path / "data")
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv(paths.ENV_RUNS_DIR, str(tmp_path / "runs"))


def test_ui_command_starts_the_app_without_streamlit_developer_buttons() -> None:
    command = cli.ui_command(8501, "0.0.0.0")
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert Path(command[4]).name == "app.py" and Path(command[4]).exists()
    options = dict(zip(command[5::2], command[6::2], strict=True))
    assert options["--server.port"] == "8501"
    assert options["--client.toolbarMode"] == "minimal"
    assert options["--browser.gatherUsageStats"] == "false"


def test_listing_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["scenarios"]) == 0
    assert "slalom" in capsys.readouterr().out
    assert cli.main(["params"]) == 0
    assert "battery.capacity" in capsys.readouterr().out
    assert cli.main(["derived", "--profile", "full_cargo"]) == 0
    assert capsys.readouterr().out.strip()


def test_run_prints_the_result_and_saves_it(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "accel_0_50", "--save"]) == 0
    out = capsys.readouterr().out
    assert "NOT VALIDATED" in out and "Safety report" in out and "Saved to" in out
    assert len(list(paths.runs_dir().iterdir())) == 1
