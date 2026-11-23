"""The single version of Jarvis, written once in pyproject.toml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def jarvis_version() -> str:
    """Installed package metadata, else pyproject.toml of this checkout."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("jarvis")
    except PackageNotFoundError:
        pass
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        import tomllib

        return str(tomllib.loads(pyproject.read_text())["project"]["version"])
    except (OSError, KeyError, ValueError):
        return "0+inconnue"
