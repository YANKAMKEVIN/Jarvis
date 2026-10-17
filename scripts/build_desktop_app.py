#!/usr/bin/env python3
"""Build a development .app linked to this checkout and Python environment.

This is a double-click launcher, not a standalone or signed distribution.
"""
import argparse
from pathlib import Path
import plistlib
import shlex
import sys


def build_app(destination: Path, python: Path, source: Path, demo=False) -> Path:
    destination = destination.expanduser().resolve()
    if destination.suffix != ".app":
        raise ValueError("La destination doit se terminer par .app")
    if destination.exists():
        raise FileExistsError(f"L’application existe déjà : {destination}")
    destination.mkdir(parents=True)
    contents = destination / "Contents"
    executable = contents / "MacOS" / "Jarvis"
    executable.parent.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump({
            "CFBundleExecutable": "Jarvis",
            "CFBundleIdentifier": "local.jarvis.desktop",
            "CFBundleName": "Jarvis",
            "CFBundleDisplayName": "Jarvis",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "0.9.0",
            "NSHighResolutionCapable": True,
        }, stream)
    # Shell quoting must preserve spaces in both checkout and interpreter paths.
    launcher = (
        "#!/bin/sh\n"
        f"export PYTHONPATH={shlex.quote(str(source.resolve()))}\n"
        f"exec {shlex.quote(str(python.absolute()))} -m jarvis.desktop"
        + (" --demo" if demo else "") + ' "$@"\n'
    )
    executable.write_text(launcher, encoding="utf-8")
    executable.chmod(0o755)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path.home() / "Applications" / "Jarvis.app")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Le lanceur .app est destiné à macOS.")
    source = Path(__file__).resolve().parents[1] / "src"
    try:
        from PySide6 import QtWidgets  # noqa: F401
        path = build_app(args.destination, Path(sys.executable), source, args.demo)
    except (ImportError, ValueError, OSError) as error:
        parser.exit(1, f"Impossible de créer le lanceur : {error}\n")
    print(f"Application créée : {path}")
    print("Gardez le dépôt et son environnement Python à leur emplacement actuel.")


if __name__ == "__main__":
    main()
