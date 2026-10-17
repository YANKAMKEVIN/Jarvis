"""Run with python -m jarvis.desktop [--demo] [--compact]."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Jarvis Desktop")
    parser.add_argument("--demo", action="store_true", help="Simulation sans modèle ni action système")
    parser.add_argument("--compact", action="store_true", help="Ouvrir le panneau compact")
    args = parser.parse_args()
    if sys.platform != "darwin" and not args.demo:
        parser.error("Les actions Jarvis exigent macOS. Utilisez --demo pour découvrir l’interface.")
    try:
        from jarvis.desktop.app import run
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("PySide6"):
            parser.exit(1, 'Installez l’interface : python -m pip install -e ".[desktop]"\n')
        raise
    return run(demo=args.demo, compact=args.compact)


if __name__ == "__main__":
    sys.exit(main())
