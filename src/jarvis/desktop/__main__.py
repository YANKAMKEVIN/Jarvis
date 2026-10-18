"""Run with python -m jarvis.desktop [--demo] [--compact]."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Jarvis Desktop")
    parser.add_argument("--demo", action="store_true", help="Simulation sans modèle ni action système")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--compact", action="store_true", help="Ouvrir le panneau compact")
    mode.add_argument("--orb", action="store_true", help="Ouvrir uniquement l’orbe flottant")
    args = parser.parse_args()
    if sys.platform != "darwin" and not args.demo:
        parser.error("Les actions Jarvis exigent macOS. Utilisez --demo pour découvrir l’interface.")
    try:
        from jarvis.desktop.app import run
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("PySide6"):
            parser.exit(1, 'Installez l’interface : python -m pip install -e ".[desktop]"\n')
        raise
    return run(demo=args.demo, compact=args.compact, orb=args.orb)


if __name__ == "__main__":
    sys.exit(main())
