"""Guards for the maintainability rules in CLAUDE.md."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from bakbrommer_twin import i18n, paths

PACKAGE = paths.PROJECT_ROOT / "bakbrommer_twin"
MAX_LINES = 400
# Prefixes of translation keys that are built at run time, e.g. t(f"status.{x}").
DYNAMIC_KEY_PREFIXES = ("status.", "param.", "subject.", "event.", "end.", "chart.")


def _sources() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def test_no_file_is_too_long() -> None:
    too_long = {
        str(p.relative_to(paths.PROJECT_ROOT)): n
        for p in [*_sources(), *sorted((paths.PROJECT_ROOT / "tests").glob("*.py"))]
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > MAX_LINES
    }
    assert not too_long, f"Split these files (limit {MAX_LINES} lines): {too_long}"


def test_every_module_and_public_function_has_a_docstring() -> None:
    missing = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not ast.get_docstring(tree):
            missing.append(str(path.relative_to(paths.PROJECT_ROOT)))
        # module-level functions and classes, and the methods of those classes
        public = [n for n in tree.body if isinstance(n, ast.FunctionDef | ast.ClassDef)]
        public += [m for c in public if isinstance(c, ast.ClassDef)
                   for m in c.body if isinstance(m, ast.FunctionDef)]
        for node in public:
            if not node.name.startswith("_") and not ast.get_docstring(node):
                missing.append(f"{path.name}:{node.name}")
    assert not missing, f"Add docstrings: {missing}"


def _translation_keys_in_code() -> set[str]:
    keys: set[str] = set()
    for path in _sources():
        pattern = r"""\bt\(\s*["']([a-z0-9_.]+)["']\s*[,)]"""
        keys.update(re.findall(pattern, path.read_text("utf-8")))
        # keys kept in constants such as AXIS_LABELS = {"time": "result.axis_time"}
        constants = r""":\s*"((?:result|batch|curves)\.[a-z_]+)\""""
        keys.update(re.findall(constants, path.read_text("utf-8")))
    # titles referenced as plain strings in ui/app.py PAGES
    keys.update(re.findall(r'"(nav\.[a-z_]+)"', (PACKAGE / "ui" / "app.py").read_text("utf-8")))
    return keys


def test_every_translation_key_used_in_code_exists() -> None:
    english = i18n.load_language("en")
    missing = sorted(k for k in _translation_keys_in_code() if k not in english)
    assert not missing, f"Add these keys to translations/en.yaml: {missing}"


def test_no_unused_translation_keys() -> None:
    used = _translation_keys_in_code()
    unused = sorted(
        k for k in i18n.load_language("en")
        if k not in used and not k.startswith(DYNAMIC_KEY_PREFIXES)
    )
    assert not unused, f"Remove these unused keys from translations/en.yaml: {unused}"


def test_other_languages_have_no_unknown_keys() -> None:
    english = i18n.load_language("en")
    for language in i18n.available_languages():
        extra = [k for k in i18n.load_language(language)
                 if k not in english and not k.startswith("param.")]
        assert not extra, f"{language}.yaml has keys that en.yaml lacks: {extra}"
