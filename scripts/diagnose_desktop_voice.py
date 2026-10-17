#!/usr/bin/env python3
"""Offline voice setup diagnosis. Never opens devices or starts Gemini."""
import argparse
import asyncio
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import platform
import sys

# Works without editable installation when run from this checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jarvis.desktop.live_runtime import VoiceSetupError, create_components, prepare_environment, setup_step, preload_live_plugins


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
        setup_step("environment", prepare_environment)
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


def run_in_worker(coroutine_factory=diagnose):
    # Same QApplication + QThread + asyncio.run combination as the GUI. No
    # session.start/audio.open: this remains an offline preparation-only test.
    from PySide6.QtCore import QThread, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    class DiagnosticWorker(QThread):
        code = 1
        def run(self):
            try:
                self.code = asyncio.run(coroutine_factory())
            except Exception as error:
                print(f"ÉCHEC : thread desktop ({type(error).__name__})", flush=True)
    worker = DiagnosticWorker()
    worker.finished.connect(app.quit)
    QTimer.singleShot(0, worker.start)
    app.exec()
    worker.wait()
    return worker.code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help="Reproduire la préparation dans le thread Qt utilisé par l’interface")
    args = parser.parse_args()
    print("Mode : thread Qt desktop" if args.worker else "Mode : thread principal", flush=True)
    if args.worker:
        try:
            preload_live_plugins()
        except VoiceSetupError as error:
            print(str(error))
            return 1
        return run_in_worker()
    return asyncio.run(diagnose())


if __name__ == "__main__":
    sys.exit(main())
