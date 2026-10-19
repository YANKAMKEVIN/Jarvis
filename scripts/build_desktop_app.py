#!/usr/bin/env python3
"""Build a development .app linked to this checkout and Python environment.

This is a double-click launcher, not a standalone or signed distribution.
"""
import argparse
from pathlib import Path
import plistlib
import shlex
import subprocess
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


def sign_app(destination: Path, identity: str = "-") -> tuple[bool, str]:
    """Code-sign the bundle so macOS keeps a STABLE TCC identity for it.

    Default is ad-hoc ("-"): free, no Apple account. macOS then ties the
    Calendar / Automation / Microphone grants to the bundle's code hash, which
    stays identical across rebuilds of the same install (same checkout and
    interpreter paths) — so the grants are not re-prompted or silently dropped
    on every rebuild. Ad-hoc does NOT clear Gatekeeper on another Mac; that
    still needs a Developer ID and notarization. Pass a real identity name to
    use a self-signed or Developer ID certificate instead.

    Best-effort: returns (ok, detail) and never raises, so a missing codesign
    (e.g. a non-macOS build host) does not fail the build.
    """
    try:
        signed = subprocess.run(
            ["codesign", "--force", "--sign", identity,
             "--identifier", "local.jarvis.desktop", str(destination)],
            capture_output=True, text=True,
        )
        if signed.returncode != 0:
            return False, (signed.stderr or signed.stdout).strip() or "codesign a echoue"
        verify = subprocess.run(
            ["codesign", "--verify", "--strict", str(destination)],
            capture_output=True, text=True,
        )
        if verify.returncode != 0:
            return False, (verify.stderr or verify.stdout).strip() or "verification refusee"
        return True, "ad-hoc" if identity == "-" else identity
    except (OSError, ValueError) as error:
        return False, str(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path.home() / "Applications" / "Jarvis.app")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--update", action="store_true", help="Actualiser un lanceur Jarvis existant sans supprimer ses autres fichiers")
    parser.add_argument("--no-sign", action="store_true", help="Ne pas signer le lanceur (par défaut : signature ad-hoc pour stabiliser les autorisations macOS)")
    parser.add_argument("--sign-identity", default="-", help="Identité codesign à utiliser (défaut : '-' ad-hoc ; ou le nom d'un certificat auto-signé / Developer ID)")
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
    if args.no_sign:
        print("Lanceur non signé (--no-sign). Les autorisations macOS peuvent être redemandées à chaque reconstruction.")
    else:
        ok, detail = sign_app(path, args.sign_identity)
        if ok:
            print(f"Signé ({detail}) : les autorisations macOS (Calendrier, Automation, Micro) resteront stables entre les reconstructions.")
        else:
            print(f"Avertissement : signature impossible ({detail}). Le lanceur fonctionne, mais les autorisations macOS peuvent être redemandées.")
    print("Gardez le dépôt et son environnement Python à leur emplacement actuel.")


if __name__ == "__main__":
    main()
