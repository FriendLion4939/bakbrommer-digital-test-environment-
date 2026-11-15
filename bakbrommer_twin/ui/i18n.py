"""Interface texts. All labels live in ``translations/<language>.yaml``.

Use the function ``t`` with a key for every text shown in the UI. To add a language, copy
``translations/en.yaml`` to e.g. ``nl.yaml`` and translate the values; it then
appears in the language picker automatically. Missing keys fall back to
English. Parameter labels and descriptions come from the registry (English)
and can be overridden per language under ``param.<name>.label`` /
``param.<name>.description``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from bakbrommer_twin.params.types import ParamDef

TRANSLATIONS_DIR = Path(__file__).parent / "translations"
DEFAULT_LANGUAGE = "en"
ENV_LANGUAGE = "BAKBROMMER_LANG"

_active_language = os.environ.get(ENV_LANGUAGE, DEFAULT_LANGUAGE)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{full}."))
        else:
            flat[full] = str(value)
    return flat


@lru_cache(maxsize=8)
def load_language(language: str) -> dict[str, str]:
    """Read one translation file into a flat ``key -> text`` dictionary."""
    path = TRANSLATIONS_DIR / f"{language}.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _flatten(data)


def available_languages() -> list[str]:
    """Language codes for which a translation file exists."""
    return sorted(p.stem for p in TRANSLATIONS_DIR.glob("*.yaml"))


def set_language(language: str) -> None:
    """Choose the language used by :func:`t`."""
    global _active_language
    _active_language = language


def get_language() -> str:
    """The language currently used by :func:`t`."""
    return _active_language


def t(key: str, **values: object) -> str:
    """Translated text for ``key``; ``{name}`` placeholders are filled from ``values``."""
    text = load_language(_active_language).get(key)
    if text is None:
        text = load_language(DEFAULT_LANGUAGE).get(key, key)
    return text.format(**values) if values else text


def param_label(definition: ParamDef) -> str:
    """Label of a parameter in the active language (registry text as fallback)."""
    return load_language(_active_language).get(f"param.{definition.name}.label", definition.label)


def param_description(definition: ParamDef) -> str:
    """Description of a parameter in the active language (registry text as fallback)."""
    return load_language(_active_language).get(
        f"param.{definition.name}.description", definition.description
    )
