#!/usr/bin/env python3
"""Build a development .app linked to this checkout and Python environment.

This is a double-click launcher, not a standalone or signed distribution.
"""
import argparse
from pathlib import Path
import plistlib
import shlex
import sys


def build_app(destination: Path, python: Path, source: Path, demo=False, update=False) -> Path:
    destination = destination.expanduser()
    if destination.is_symlink():
        raise ValueError("Le lanceur ne peut pas être un lien symbolique.")
    destination = destination.resolve()
    if destination.suffix != ".app":
        raise ValueError("La destination doit se terminer par .app")
    contents = destination / "Contents"
    executable = contents / "MacOS" / "Jarvis"
    info = {}
    if destination.exists():
        if not update:
            raise FileExistsError(f"L’application existe déjà : {destination}. Utilisez --update pour actualiser ce lanceur Jarvis.")
        info_path = contents / "Info.plist"
        if contents.is_symlink() or executable.parent.is_symlink() or executable.is_symlink() or info_path.is_symlink():
            raise ValueError("Mise à jour refusée : liens symboliques dans le lanceur.")
        try:
            with info_path.open("rb") as stream:
                info = plistlib.load(stream)
        except (OSError, ValueError):
            raise ValueError("La destination n’est pas un lanceur Jarvis valide.") from None
        if info.get("CFBundleIdentifier") != "local.jarvis.desktop":
            raise ValueError("La destination appartient à une autre application.")
    executable.parent.mkdir(parents=True, exist_ok=True)
    with (contents / "Info.plist").open("wb") as stream:
        info.update({
            "CFBundleExecutable": "Jarvis",
            "CFBundleIdentifier": "local.jarvis.desktop",
            "CFBundleName": "Jarvis",
            "CFBundleDisplayName": "Jarvis",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "0.9.0",
            "NSHighResolutionCapable": True,
            # Menu-bar / orb companion: no Dock icon.
            "LSUIElement": True,
            "NSMicrophoneUsageDescription": "Jarvis utilise le micro uniquement quand vous activez le vocal pour parler avec Gemini Live.",
            # Needed so EventKit can actually prompt for Calendar/Reminders in a
            # real .app (a bare interpreter never gets the prompt).
            "NSCalendarsUsageDescription": "Jarvis lit et cree des evenements dans votre agenda uniquement a votre demande.",
            "NSRemindersUsageDescription": "Jarvis lit et cree des rappels uniquement a votre demande.",
            # Needed so AppleScript automations (Calendar, Mail, WhatsApp, etc.)
            # can prompt for the Automation permission instead of being denied.
            "NSAppleEventsUsageDescription": "Jarvis pilote d'autres applications (Mail, WhatsApp, Calendrier...) uniquement pour executer ce que vous demandez.",
        })
        plistlib.dump(info, stream)
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
    parser.add_argument("--update", action="store_true", help="Actualiser un lanceur Jarvis existant sans supprimer ses autres fichiers")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Le lanceur .app est destiné à macOS.")
    source = Path(__file__).resolve().parents[1] / "src"
    try:
        from PySide6 import QtWidgets  # noqa: F401
        path = build_app(args.destination, Path(sys.executable), source, args.demo, args.update)
    except (ImportError, ValueError, OSError) as error:
        parser.exit(1, f"Impossible de créer le lanceur : {error}\n")
    print(f"Application créée : {path}")
    print("Gardez le dépôt et son environnement Python à leur emplacement actuel.")


if __name__ == "__main__":
    main()
