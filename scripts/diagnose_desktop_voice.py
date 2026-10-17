#!/usr/bin/env python3
"""Offline voice setup diagnosis. Never opens devices or starts Gemini."""
import asyncio
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import platform
import sys

# Works without editable installation when run from this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jarvis.desktop.live_runtime import VoiceSetupError, create_components, prepare_environment


def package_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "non installé"


async def diagnose():
    print("DIAGNOSTIC VOCAL JARVIS — aucun micro, aucune connexion Gemini")
    print(f"Système : {platform.system()} / {platform.machine()}")
    print(f"Python : {platform.python_version()}")
    for package in ("PySide6", "livekit-agents", "livekit-plugins-google", "sounddevice", "python-dotenv"):
        print(f"{package} : {package_version(package)}")
    components = None
    try:
        prepare_environment()
        print("Configuration Gemini : présente (clé masquée)")
        components = create_components()
        print("Préparation : OK")
        print("Le diagnostic ne teste ni la connexion Gemini, ni le son, ni l’autorisation du micro.")
        return 0
    except VoiceSetupError as error:
        print(f"ÉCHEC : {error.stage}")
        print(str(error))
        if error.error_type:
            print(f"Type : {error.error_type}")
        for frame in error.frames:
            print(f"  {frame}")
        return 1
    except Exception as error:
        # Never print raw exception text, env values, or an HTTP error payload.
        print(f"ÉCHEC : diagnostic ({type(error).__name__})")
        return 1
    finally:
        if components is not None:
            for closer in (components.assistant.registry.aclose,
                           components.session.aclose, components.model.aclose):
                try:
                    await closer()
                except Exception:
                    pass


if __name__ == "__main__":
    sys.exit(asyncio.run(diagnose()))
