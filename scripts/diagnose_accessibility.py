"""Read an app's AX field metadata locally, without activation or field values.

Run from an Accessibility-authorized terminal with the target app already open:
    PYTHONPATH=src .venv/bin/python scripts/diagnose_accessibility.py --app Safari

Labels are printed only to stdout, never to debug_live. They may include site
metadata; AXValue and selected text are never read. Window titles are omitted.
"""

import argparse
import json
import subprocess

from jarvis.tools.accessibility import (
    AccessibilityError,
    AccessibilityTools,
    ApplicationServicesAccessibilityBackend,
    TEXT_ROLES,
)


class AppWindowBackend(ApplicationServicesAccessibilityBackend):
    def __init__(self, pid):
        super().__init__()
        self.pid = pid

    def focused_window(self):
        self.ensure_trusted()
        app = self.create_application(self.pid)
        if not app:
            raise AccessibilityError("Application unavailable", "app_unavailable")
        try:
            return self.copy_attribute(app, "AXFocusedWindow")
        finally:
            self.release(app)

def inspect_limits(backend):
    tools = AccessibilityTools(backend=backend)
    reports = []
    for depth, count in ((4, 80), (6, 150)):
        snapshot = tools.inspect_ui(depth, count)
        reports.append({
            "max_depth": depth,
            "max_elements": count,
            "count": snapshot["count"],
            "truncated": snapshot["truncated"],
            "diagnostics": snapshot["diagnostics"],
            "fields": [
                {key: element[key] for key in (
                    "role", "subrole", "title", "description", "identifier", "actions", "path",
                    "focused", "enabled", "editable",
                ) if key in element}
                for element in snapshot["elements"]
                if element.get("role") in TEXT_ROLES
                and element.get("role") != "AXSecureTextField"
            ],
        })
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    args = parser.parse_args()
    processes = subprocess.run(
        ["pgrep", "-x", "--", args.app], capture_output=True, text=True, check=False,
    )
    pids = processes.stdout.split()
    if len(pids) != 1:
        print(json.dumps({"error_code": "app_missing_or_ambiguous", "count": len(pids)}))
        return 1
    try:
        reports = inspect_limits(AppWindowBackend(int(pids[0])))
    except AccessibilityError as error:
        print(json.dumps({"error_code": error.code}))
        return 1
    print(json.dumps({"inspections": reports}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
