"""Capture every page of the desktop UI offscreen, into one folder (CI preview).

    QT_QPA_PLATFORM=offscreen python scripts/capture_all.py --output captures

Runs the existing capture scripts in demo mode (no microphone, network or
user preferences) with JARVIS_CAPTURE_DIR pointing at --output, so docs/ is
never modified. Exits non-zero if a capture fails or writes nothing.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ("capture_desktop_preview.py", ["--samples", "--output", "{output}"]),
    ("capture_desktop_menu.py", []),
    ("capture_companion_preview.py", []),
    ("capture_desktop_experience.py", []),
    ("capture_experience_twenty.py", []),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "captures")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
               JARVIS_CAPTURE_DIR=str(output), PYTHONPATH=str(ROOT / "src"))
    failures = []
    for script, extra in SCRIPTS:
        command = [sys.executable, str(ROOT / "scripts" / script), *(a.format(output=output) for a in extra)]
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            failures.append(f"{script}: délai dépassé")
            continue
        if result.returncode != 0:
            failures.append(f"{script}: code {result.returncode}\n{result.stderr[-800:]}")
    images = sorted(output.rglob("*.png"))
    print(f"{len(images)} capture(s) dans {output}")
    for failure in failures:
        print("ÉCHEC", failure, file=sys.stderr)
    return 1 if failures or not images else 0


if __name__ == "__main__":
    raise SystemExit(main())
