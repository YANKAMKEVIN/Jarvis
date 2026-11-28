"""Guard against god files: every Python file stays under MAX_LINES lines.

Files that are still above the limit are listed in ALLOWED_OVERSIZE with their
current line count as a ceiling. The list may only shrink:

- a new file above the limit fails;
- a listed file that grows past its ceiling fails;
- a listed file that shrank must have its ceiling lowered (or be removed once
  it is back under the limit), so the gain cannot be lost later.

Run: python scripts/check_file_sizes.py   (exit code 1 on any violation)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 400
SCANNED_DIRS = ("src", "scripts", "tests")

# Explicit, decreasing list of the files still above MAX_LINES (path: ceiling).
ALLOWED_OVERSIZE: dict[str, int] = {
    "scripts/smoke_test.py": 1735,
    "src/jarvis/capabilities/messaging.py": 569,
    "src/jarvis/desktop/app.py": 1739,
    "src/jarvis/desktop/charts.py": 923,
    "src/jarvis/desktop/companion.py": 411,
    "src/jarvis/desktop/live_audio.py": 470,
    "src/jarvis/desktop/live_runtime.py": 753,
    "src/jarvis/desktop/onboarding.py": 498,
    "src/jarvis/knowledge/service.py": 619,
    "src/jarvis/memory/store.py": 538,
    "src/jarvis/planner/tasks.py": 411,
    "src/jarvis/tools/browser.py": 509,
    "src/jarvis/tools/filesystem.py": 887,
    "src/jarvis/tools/keyboard.py": 465,
    "src/jarvis/tools/mouse.py": 445,
    "src/jarvis/usage/store.py": 506,
    "tests/test_accessibility_tools.py": 590,
    "tests/test_desktop_live_runtime.py": 647,
    "tests/test_desktop_ui.py": 690,
    "tests/test_filesystem_tools.py": 441,
    "tests/test_interaction_capability.py": 1299,
    "tests/test_knowledge.py": 1656,
    "tests/test_live_poc.py": 3937,
    "tests/test_macos_tools.py": 1442,
    "tests/test_memory_capability.py": 425,
    "tests/test_messaging_capability.py": 496,
    "tests/test_planner.py": 472,
    "tests/test_planner_tasks.py": 427,
}


def line_counts(root: Path = ROOT) -> dict[str, int]:
    counts: dict[str, int] = {}
    for directory in SCANNED_DIRS:
        for path in sorted((root / directory).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            with path.open("rb") as handle:
                counts[path.relative_to(root).as_posix()] = sum(1 for _ in handle)
    return counts


def violations(counts: dict[str, int],
               allowed: dict[str, int] = ALLOWED_OVERSIZE,
               limit: int = MAX_LINES) -> list[str]:
    problems: list[str] = []
    for path, lines in sorted(counts.items()):
        ceiling = allowed.get(path)
        if ceiling is None:
            if lines > limit:
                problems.append(f"{path}: {lines} lines > {limit}; split it into cohesive modules")
        elif lines > ceiling:
            problems.append(f"{path}: {lines} lines, above its ceiling of {ceiling}; it must not grow")
        elif lines <= limit:
            problems.append(f"{path}: now {lines} lines; remove it from ALLOWED_OVERSIZE")
        elif lines < ceiling:
            problems.append(f"{path}: now {lines} lines; lower its ceiling from {ceiling} to {lines}")
    for path in sorted(allowed.keys() - counts.keys()):
        problems.append(f"{path}: listed in ALLOWED_OVERSIZE but no longer exists; remove it")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    counts = line_counts()
    problems = violations(counts)
    for problem in problems:
        print(problem)
    largest = max(counts.items(), key=lambda item: item[1])
    print(f"{len(counts)} files scanned, {len(ALLOWED_OVERSIZE)} allowed above {MAX_LINES} lines, "
          f"largest: {largest[0]} ({largest[1]} lines)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
