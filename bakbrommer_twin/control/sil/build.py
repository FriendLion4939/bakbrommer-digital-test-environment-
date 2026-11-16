"""Compiles a controller C file into a shared library for the PC."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SIL_DIR = Path(__file__).parent
EXAMPLE_SOURCE = SIL_DIR / "example_controller.c"
ENV_COMPILER = "CC"
_COMPILERS = ("cc", "gcc", "clang")


class SilBuildError(RuntimeError):
    """Raised when the C code cannot be compiled (no compiler, or compile errors)."""


def find_compiler() -> str | None:
    """Path of a C compiler, or None if the machine has none."""
    for name in (os.environ.get(ENV_COMPILER), *_COMPILERS):
        if name and shutil.which(name):
            return shutil.which(name)
    return None


def _library_suffix() -> str:
    if sys.platform == "win32":
        return ".dll"
    return ".dylib" if sys.platform == "darwin" else ".so"


def build(source: Path = EXAMPLE_SOURCE, output_dir: Path | None = None) -> Path:
    """Compile ``source`` and return the path of the shared library.

    The library is cached by the content of the source and header: compiling
    happens only when one of them changed.
    """
    if not source.exists():
        raise SilBuildError(f"C source file not found: {source}")
    compiler = find_compiler()
    if compiler is None:
        raise SilBuildError(
            "No C compiler found. Install gcc (Linux: 'apt install gcc', Windows: MinGW-w64) "
            "or use the Docker image, which contains one.")
    header = SIL_DIR / "bb_controller.h"
    digest = hashlib.sha256(source.read_bytes() + header.read_bytes()).hexdigest()[:16]
    folder = output_dir or Path(tempfile.gettempdir()) / "bakbrommer_twin_sil"
    folder.mkdir(parents=True, exist_ok=True)
    library = folder / f"{source.stem}_{digest}{_library_suffix()}"
    if library.exists():
        return library
    command = [compiler, "-shared", "-fPIC", "-O2", "-Wall", f"-I{SIL_DIR}", str(source),
               "-o", str(library)]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SilBuildError(f"Compiling {source.name} failed:\n{done.stderr.strip()}")
    return library
