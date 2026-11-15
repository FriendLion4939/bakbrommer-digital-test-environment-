"""Command line entry point: ``bakbrommer-twin <command>``.

Commands are small wrappers; the real work lives in the packages.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from bakbrommer_twin import paths
from bakbrommer_twin.params import REGISTRY
from bakbrommer_twin.params.derived import compute_derived
from bakbrommer_twin.params.profile import ProfileStore


def _cmd_ui(args: argparse.Namespace) -> int:
    """Start the web interface."""
    app = Path(__file__).parent / "ui" / "app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app),
               "--server.port", str(args.port), "--server.address", args.address,
               "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    return subprocess.call(command)


def _cmd_params(args: argparse.Namespace) -> int:
    """Print all parameters of a profile."""
    params = ProfileStore(paths.profiles_dir(), REGISTRY).load(args.profile).params
    for d in REGISTRY:
        print(f"{d.name:45s} {params.display(d.name)!s:>22s} {d.unit:8s} "
              f"[{params.status(d.name).value}]")
    return 0


def _cmd_derived(args: argparse.Namespace) -> int:
    """Print the calculated values of a profile."""
    params = ProfileStore(paths.profiles_dir(), REGISTRY).load(args.profile).params
    for value in compute_derived(params):
        print(f"{value.label:45s} {value.display:12.4g} {value.unit}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all sub-commands."""
    parser = argparse.ArgumentParser(prog="bakbrommer-twin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ui = sub.add_parser("ui", help="start the web interface")
    ui.add_argument("--port", type=int, default=8501)
    ui.add_argument("--address", default="0.0.0.0")
    ui.set_defaults(func=_cmd_ui)

    for name, func, text in (("params", _cmd_params, "list all parameters"),
                             ("derived", _cmd_derived, "show calculated values")):
        command = sub.add_parser(name, help=text)
        command.add_argument("--profile", default="default")
        command.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
