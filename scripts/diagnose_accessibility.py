"""Read an app's AX field metadata locally, without activation or field values.

Run from an Accessibility-authorized terminal with the target app already open:
    PYTHONPATH=src .venv/bin/python scripts/diagnose_accessibility.py --app Safari
    PYTHONPATH=src .venv/bin/python scripts/diagnose_accessibility.py --app TextEdit

Labels are printed only to stdout, never to debug_live. They may include site
metadata; AXValue and selected text are NEVER read. Window titles are omitted.

Output sections:
- "inspections": the filtered text-role view that inspect_ui exposes (what the
  live capabilities actually see), for two depth/element limits.
- "focused_ui_elements": the AXFocusedUIElement of the focused window and of the
  application process, i.e. what really holds keyboard focus. This answers why a
  per-element AXFocused check can fail even when a text area is focused.
- "raw_tree": every node (NOT filtered by should_include_element), with role,
  subrole, focused, enabled, settable AXValue, actions and, for editable
  candidates, the list of AX attribute NAMES available (names only, never
  values). This distinguishes "attribute absent/unsupported" (null) from
  "attribute present and false".

Nothing here mutates state: no activation, no set-focus, no AXPress, no AXValue.
"""

import argparse
import ctypes
import json
import subprocess

from jarvis.tools.accessibility import (
    SECURE_ROLES,
    AccessibilityError,
    AccessibilityTools,
    ApplicationServicesAccessibilityBackend,
    TEXT_ROLES,
)


# Roles that plausibly host an editable text target on macOS. Used only to decide
# which raw nodes get their AX attribute names listed (diagnostic verbosity),
# never to accept or reject a target.
TEXTISH_ROLES = {
    "AXTextArea",
    "AXTextField",
    "AXSearchField",
    "AXComboBox",
    "AXTextView",
}

RAW_TREE_MAX_DEPTH = 6
RAW_TREE_NODE_CAP = 250


class AppWindowBackend(ApplicationServicesAccessibilityBackend):
    def __init__(self, pid):
        super().__init__()
        self.pid = pid
        self._configure_attribute_names()

    def _configure_attribute_names(self):
        try:
            self.app_services.AXUIElementCopyAttributeNames.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            self.app_services.AXUIElementCopyAttributeNames.restype = ctypes.c_int32
        except Exception:
            pass

    def focused_window(self):
        self.ensure_trusted()
        app = self.create_application(self.pid)
        if not app:
            raise AccessibilityError("Application unavailable", "app_unavailable")
        try:
            return self.copy_attribute(app, "AXFocusedWindow")
        finally:
            self.release(app)

    def application_element(self):
        self.ensure_trusted()
        app = self.create_application(self.pid)
        if not app:
            raise AccessibilityError("Application unavailable", "app_unavailable")
        return app

    def attribute_names(self, element) -> list[str]:
        """List available AX attribute NAMES on an element (names only)."""
        names = ctypes.c_void_p()
        try:
            status = self.app_services.AXUIElementCopyAttributeNames(
                element, ctypes.byref(names)
            )
        except Exception:
            return []
        if status != 0 or not names.value:
            return []
        try:
            value = self.cf_to_python(names.value)
            return value if isinstance(value, list) else []
        finally:
            self.release(names.value)


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


def node_descriptor(backend, element, with_attributes=False):
    """Non-sensitive descriptor of a single AX node. Never reads AXValue.

    Booleans are kept as None when the attribute is absent/unsupported, so the
    caller can tell "attribute missing" (null) from "present and false".
    """
    role = _safe_text(backend, element, "AXRole")
    subrole = _safe_text(backend, element, "AXSubrole")
    descriptor = {
        "role": role,
        "subrole": subrole,
        "description": _safe_text(backend, element, "AXDescription"),
        "identifier": _safe_text(backend, element, "AXIdentifier"),
        "focused": _safe_bool(backend, element, "AXFocused"),
        "enabled": _safe_bool(backend, element, "AXEnabled"),
        "selected": _safe_bool(backend, element, "AXSelected"),
        "secure": role in SECURE_ROLES,
        "settable_value": _safe_settable(backend, element),
        "actions": _safe_actions(backend, element),
    }

    is_candidate = (
        descriptor["settable_value"] is True
        or role in TEXTISH_ROLES
        or descriptor["focused"] is True
    )

    if with_attributes or is_candidate:
        descriptor["available_attributes"] = backend.attribute_names(element)

    return descriptor


def focused_ui_element_descriptors(backend):
    """Report what actually holds focus, via AXFocusedUIElement."""
    results = []

    for label, getter in (
        ("focused_window", backend.focused_window),
        ("application", backend.application_element),
    ):
        entry = {"source": label, "focused_ui_element": None}
        try:
            source = getter()
        except AccessibilityError as error:
            entry["error_code"] = error.code
            results.append(entry)
            continue

        try:
            focused = backend.copy_attribute(source, "AXFocusedUIElement")
        except AccessibilityError as error:
            entry["error_code"] = error.code
            focused = None

        if focused:
            try:
                entry["focused_ui_element"] = node_descriptor(
                    backend, focused, with_attributes=True
                )
            finally:
                backend.release(focused)

        backend.release(source)
        results.append(entry)

    return results


def raw_tree(backend):
    """DFS of the focused window, unfiltered by should_include_element."""
    root = backend.focused_window()
    nodes = []
    diagnostics = []
    truncated = {"value": False}

    def visit(element, path, depth):
        if len(nodes) >= RAW_TREE_NODE_CAP:
            truncated["value"] = True
            return

        try:
            descriptor = node_descriptor(backend, element)
        except AccessibilityError as error:
            diagnostics.append({"path": path, "error_code": error.code})
            return

        descriptor["path"] = path

        try:
            children = backend.children(element)
        except AccessibilityError as error:
            descriptor["child_count"] = None
            diagnostics.append({"path": path, "error_code": error.code})
            nodes.append(descriptor)
            return

        descriptor["child_count"] = len(children)
        nodes.append(descriptor)

        if depth >= RAW_TREE_MAX_DEPTH:
            for child in children:
                backend.release(child)
            return

        for index, child in enumerate(children):
            try:
                visit(child, [*path, index], depth + 1)
            finally:
                backend.release(child)

    try:
        visit(root, [], 0)
    finally:
        backend.release(root)

    return {
        "max_depth": RAW_TREE_MAX_DEPTH,
        "node_cap": RAW_TREE_NODE_CAP,
        "count": len(nodes),
        "truncated": truncated["value"],
        "diagnostics": diagnostics,
        "nodes": nodes,
    }


def _safe_text(backend, element, attribute):
    try:
        return backend.copy_attribute_text(element, attribute)
    except AccessibilityError:
        return None


def _safe_bool(backend, element, attribute):
    try:
        return backend.copy_attribute_bool(element, attribute)
    except AccessibilityError:
        return None


def _safe_actions(backend, element):
    try:
        return backend.action_names(element)
    except AccessibilityError:
        return []


def _safe_settable(backend, element):
    try:
        return backend.value_is_settable(element)
    except Exception:
        return None


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

    pid = int(pids[0])
    output = {"app": args.app}

    try:
        output["inspections"] = inspect_limits(AppWindowBackend(pid))
    except AccessibilityError as error:
        print(json.dumps({"error_code": error.code}))
        return 1

    try:
        output["focused_ui_elements"] = focused_ui_element_descriptors(
            AppWindowBackend(pid)
        )
    except AccessibilityError as error:
        output["focused_ui_elements_error"] = error.code

    try:
        output["raw_tree"] = raw_tree(AppWindowBackend(pid))
    except AccessibilityError as error:
        output["raw_tree_error"] = error.code

    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
