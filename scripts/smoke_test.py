"""Smoke test of real Jarvis commands on this Mac.

Calls the exact tools exposed to Gemini Live (create_live_tools), on the real
system, then checks the outcome with an observation that does not go through
Jarvis (osascript, pbpaste, lsappinfo, filesystem). Every scenario restores
the state it touched (volume, clipboard, mouse, apps, files).

Nothing outward is ever sent: the messaging scenario only prepares a send and
cancels it.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/smoke_test.py
    PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --group volume --group files
    PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --list
"""

import argparse
import asyncio
import ctypes
import json
import os
import sqlite3
import stat
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


SMOKE_TEXT = "Jarvis smoke test 42"
SAFARI_URL = "https://example.com/"


class CheckFailed(Exception):
    pass


class Skipped(Exception):
    pass


@dataclass
class StepResult:
    group: str
    name: str
    status: str  # pass | fail | skip
    detail: str = ""
    duration_ms: int = 0


@dataclass
class Context:
    tools: dict
    workdir: Path
    perms: dict = field(default_factory=dict)
    results: list[StepResult] = field(default_factory=list)


# --- macOS permissions -------------------------------------------------------


def permissions() -> dict[str, bool]:
    """TCC grants of the *responsible* app (Terminal, iTerm, Claude...)."""
    ax = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    ax.AXIsProcessTrusted.restype = ctypes.c_bool
    cg = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
    return {
        "accessibility": bool(ax.AXIsProcessTrusted()),
        "screen_recording": bool(cg.CGPreflightScreenCaptureAccess()),
        # Locked screen: keystrokes would land in the login window.
        "screen_unlocked": _screen_unlocked(),
    }


def _screen_unlocked() -> bool:
    try:
        return frontmost_app() != "loginwindow"
    except Exception:
        return False


# Groups that cannot work without a given permission are skipped, so a
# missing grant is never mistaken for a Jarvis regression.
REQUIRES = {
    "mouse": ("accessibility", "screen_unlocked"),
    "textedit": ("accessibility", "screen_unlocked"),
    "screenshot": ("screen_recording", "screen_unlocked"),
    "apps": ("screen_unlocked",),
    "safari": ("screen_unlocked",),
}


# --- independent observation helpers (never go through Jarvis) -------------


def sh(*args: str, check: bool = True) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if check and proc.returncode != 0:
        raise CheckFailed(f"{args[0]} a echoue : {proc.stderr.strip()}")
    return proc.stdout.strip()


def osascript(script: str, check: bool = True) -> str:
    return sh("osascript", "-e", script, check=check)


def system_volume() -> int:
    return int(osascript("output volume of (get volume settings)"))


def pbpaste() -> str:
    return sh("pbpaste")


def pbcopy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=10)


def frontmost_app() -> str:
    asn = sh("lsappinfo", "front")
    out = sh("lsappinfo", "info", "-only", "name", asn)
    # Output looks like: "LSDisplayName"="TextEdit"
    return out.split("=", 1)[-1].strip().strip('"')


def app_running(name: str) -> bool:
    return osascript(f'application "{name}" is running') == "true"


def wait_until(predicate, timeout: float = 5.0, interval: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


# --- Jarvis tool invocation -------------------------------------------------


def call(ctx: Context, tool: str, *args, **kwargs) -> dict:
    result = asyncio.run(ctx.tools[tool](*args, **kwargs))
    if not isinstance(result, dict):
        raise CheckFailed(f"{tool} n'a pas renvoye un dict : {result!r}")
    return result


def call_ok(ctx: Context, tool: str, *args, **kwargs) -> dict:
    result = call(ctx, tool, *args, **kwargs)
    expect(
        result.get("ok") is True,
        f"{tool} -> ok=false ({result.get('error_code')}) : {result.get('message')}",
    )
    return result


# --- scenarios --------------------------------------------------------------


def group_system(ctx: Context, step) -> None:
    step("get_battery_status", lambda: call_ok(ctx, "get_battery_status"))
    step("get_system_info", lambda: call_ok(ctx, "get_system_info"))


def group_volume(ctx: Context, step) -> None:
    original = system_volume()
    target = original - 7 if original >= 50 else original + 7

    def read():
        result = call_ok(ctx, "get_volume")
        expect(
            abs(int(result.get("volume", -1)) - original) <= 1,
            f"get_volume={result.get('volume')} mais le systeme dit {original}",
        )

    def set_and_verify():
        call_ok(ctx, "set_volume", target)
        actual = system_volume()
        expect(abs(actual - target) <= 1, f"volume systeme {actual}, attendu {target}")

    try:
        step("get_volume", read)
        step(f"set_volume {original}->{target}", set_and_verify)
    finally:
        osascript(f"set volume output volume {original}", check=False)


def group_clipboard(ctx: Context, step) -> None:
    original = pbpaste()

    def set_and_verify():
        call_ok(ctx, "set_clipboard_text", SMOKE_TEXT)
        expect(pbpaste() == SMOKE_TEXT, f"pbpaste={pbpaste()!r}")

    def read():
        result = call_ok(ctx, "get_clipboard_text")
        expect(SMOKE_TEXT in json.dumps(result, ensure_ascii=False), "texte absent du resultat")

    def clear():
        call_ok(ctx, "clear_clipboard")
        expect(pbpaste() == "", f"presse-papiers non vide : {pbpaste()!r}")

    try:
        step("set_clipboard_text", set_and_verify)
        step("get_clipboard_text", read)
        step("clear_clipboard", clear)
    finally:
        pbcopy(original)


def group_files(ctx: Context, step) -> None:
    base = ctx.workdir / "files"
    renamed = ctx.workdir / "files-renamed"
    dest_parent = ctx.workdir / "dest"

    def create():
        call_ok(ctx, "create_folder", str(base))
        expect(base.is_dir(), f"{base} n'existe pas")
        (base / "hello.txt").write_text("hello")

    def list_():
        result = call_ok(ctx, "list_files", str(base))
        expect("hello.txt" in json.dumps(result), "hello.txt absent du listing")

    def info():
        call_ok(ctx, "get_file_info", str(base / "hello.txt"))

    def rename():
        call_ok(ctx, "rename_file", str(base), renamed.name)
        expect(renamed.is_dir() and not base.exists(), "renommage non constate sur disque")

    def move():
        dest_parent.mkdir(exist_ok=True)
        call_ok(ctx, "move_file", str(renamed), str(dest_parent / renamed.name))
        expect((dest_parent / renamed.name / "hello.txt").exists(), "deplacement non constate")

    def move_into_folder():
        # Destination given as an existing folder: item goes inside it.
        moved = dest_parent / renamed.name / "hello.txt"
        call_ok(ctx, "move_file", str(moved), str(ctx.workdir))
        expect((ctx.workdir / "hello.txt").exists() and not moved.exists(),
               "deplacement dans le dossier non constate")

    step("create_folder", create, critical=True)
    step("list_files", list_)
    step("get_file_info", info)
    step("rename_file", rename)
    step("move_file (chemin complet)", move)
    step("move_file (vers un dossier)", move_into_folder)


def group_mouse(ctx: Context, step) -> None:
    start = call_ok(ctx, "get_mouse_position")
    x0, y0 = int(start["x"]), int(start["y"])
    tx, ty = x0 + 25, y0 + 25

    def move():
        call_ok(ctx, "move_mouse", tx, ty)
        pos = call_ok(ctx, "get_mouse_position")
        expect(
            abs(int(pos["x"]) - tx) <= 2 and abs(int(pos["y"]) - ty) <= 2,
            f"pointeur en {pos['x']},{pos['y']}, attendu {tx},{ty}",
        )

    try:
        step(f"move_mouse ({x0},{y0})->({tx},{ty})", move)
    finally:
        asyncio.run(ctx.tools["move_mouse"](x0, y0))


def _check_png(path: Path) -> None:
    expect(path.exists(), f"{path} absent")
    expect(path.stat().st_size > 1000, f"{path} trop petit ({path.stat().st_size} o)")
    expect(path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{path} n'est pas un PNG")


def group_screenshot(ctx: Context, step) -> None:
    def screen():
        path = ctx.workdir / "screen.png"
        call_ok(ctx, "capture_screen", str(path))
        _check_png(path)

    def region():
        path = ctx.workdir / "region.png"
        call_ok(ctx, "capture_region", 0, 0, 300, 200, str(path))
        _check_png(path)

    step("capture_screen", screen)
    step("capture_region", region)


def group_apps(ctx: Context, step) -> None:
    app = "Calculator"
    if app_running(app):
        step("open/close Calculator", lambda: (_ for _ in ()).throw(
            Skipped("Calculator deja ouverte, je n'y touche pas")))
        return

    def open_():
        call_ok(ctx, "open_app", app)
        expect(wait_until(lambda: app_running(app)), "Calculator ne tourne pas")

    def running():
        result = call_ok(ctx, "is_app_running", app)
        expect(result.get("running") is True or "true" in json.dumps(result).lower(),
               f"is_app_running : {result}")

    def close():
        call_ok(ctx, "close_app", app)
        expect(wait_until(lambda: not app_running(app)), "Calculator tourne encore")

    try:
        step("open_app Calculator", open_, critical=True)
        step("is_app_running Calculator", running)
        step("close_app Calculator", close)
    finally:
        if app_running(app):
            osascript(f'tell application "{app}" to quit', check=False)


def group_textedit(ctx: Context, step) -> None:
    was_running = app_running("TextEdit")
    doc = ctx.workdir / "smoke.txt"
    doc.write_text("")
    original_clipboard = pbpaste()

    def setup_and_focus():
        # Setup (not under test): open a throwaway document.
        sh("open", "-a", "TextEdit", str(doc))
        expect(wait_until(lambda: frontmost_app() == "TextEdit"), "TextEdit pas au premier plan")
        time.sleep(0.5)
        call_ok(ctx, "open_app", "TextEdit")
        expect(frontmost_app() == "TextEdit", f"app au premier plan : {frontmost_app()}")

    def active_window():
        # Lives here rather than in "system": System Events cannot read the
        # windows of the app hosting this process (e.g. Claude) when it is
        # frontmost, so the check needs a known, neutral frontmost app.
        result = call_ok(ctx, "get_active_window")
        expect(result.get("target_app") == "TextEdit", f"fenetre active : {result.get('target_app')}")

    def type_():
        # Re-check right before typing: never type into another app.
        expect(frontmost_app() == "TextEdit", f"app au premier plan : {frontmost_app()}")
        call_ok(ctx, "type_text", SMOKE_TEXT)
        time.sleep(0.3)
        text = osascript('tell application "TextEdit" to text of front document', check=False)
        if text:  # Automation permission granted: strongest check.
            expect(text.strip() == SMOKE_TEXT, f"document contient {text!r}")

    def copy():
        call_ok(ctx, "select_all_and_copy")
        expect(wait_until(lambda: pbpaste() == SMOKE_TEXT), f"pbpaste={pbpaste()!r}")

    def capture():
        if not ctx.perms.get("screen_recording"):
            raise Skipped("permission Enregistrement de l'ecran manquante")
        path = ctx.workdir / "textedit.png"
        call_ok(ctx, "capture_window", "TextEdit", str(path))
        _check_png(path)

    def delete():
        call_ok(ctx, "select_all_and_delete")
        time.sleep(0.3)
        text = osascript('tell application "TextEdit" to text of front document', check=False)
        expect(text.strip() == "", f"document non vide : {text!r}")

    try:
        step("open_app TextEdit (focus)", setup_and_focus, critical=True)
        step("get_active_window", active_window, critical=True)
        step("type_text", type_)
        step("select_all_and_copy", copy)
        step("capture_window TextEdit", capture)
        step("select_all_and_delete", delete)
    finally:
        osascript(
            'tell application "TextEdit" to close (every document whose path is '
            f'"{doc}") saving no',
            check=False,
        )
        pbcopy(original_clipboard)

    if not was_running:
        def close():
            call_ok(ctx, "close_app", "TextEdit")
            expect(wait_until(lambda: not app_running("TextEdit")), "TextEdit tourne encore")

        try:
            step("close_app TextEdit", close)
        finally:
            if app_running("TextEdit"):
                osascript('tell application "TextEdit" to quit saving no', check=False)


def group_safari(ctx: Context, step) -> None:
    was_running = app_running("Safari")
    state = {}

    def current_url() -> str:
        return osascript('tell application "Safari" to URL of current tab of front window')

    def open_():
        result = call_ok(ctx, "browse_open_url", SAFARI_URL, "Safari", True)
        expect(result.get("state_confirmed") is True, f"state_confirmed false : {result}")
        expect(wait_until(lambda: "example.com" in current_url()), f"URL active : {current_url()}")

    def active():
        result = call_ok(ctx, "browse_get_active_tab", "Safari")
        expect("example.com" in json.dumps(result), f"onglet actif : {result}")

    def list_():
        result = call_ok(ctx, "browse_list_tabs", "Safari")
        tabs = result.get("tabs") or []
        matches = [t for t in tabs if "example.com" in str(t.get("url", ""))]
        expect(matches, "onglet example.com absent de la liste")
        state["index"] = matches[-1].get("index")
        state["other"] = next(
            (t.get("index") for t in tabs if "example.com" not in str(t.get("url", ""))),
            None,
        )

    def activate():
        if state.get("other") is None:
            raise Skipped("un seul onglet, rien a basculer")
        call_ok(ctx, "browse_activate_tab", None, state["other"], "Safari")
        expect(wait_until(lambda: "example.com" not in current_url()), "bascule non constatee")
        call_ok(ctx, "browse_activate_tab", None, state["index"], "Safari")
        expect(wait_until(lambda: "example.com" in current_url()), "retour non constate")

    try:
        step("browse_open_url example.com", open_, critical=True)
        step("browse_get_active_tab", active)
        step("browse_list_tabs", list_)
        step("browse_activate_tab (index)", activate)
    finally:
        if not was_running:
            osascript('tell application "Safari" to quit', check=False)
        else:
            osascript(
                'tell application "Safari" to close (every tab of every window '
                'whose URL contains "example.com")',
                check=False,
            )


def group_messaging(ctx: Context, step) -> None:
    state = {}

    def prepare():
        # No recipient: no UI is touched; only a pending action is registered.
        result = call_ok(ctx, "prepare_send_message", "SmokeTestApp", "ne pas envoyer")
        expect(result.get("requires_confirmation") is True, "requires_confirmation absent")
        expect(bool(result.get("token")), "token absent")
        state["token"] = result["token"]

    def cancel():
        result = call_ok(ctx, "cancel_action", state["token"])
        expect(result.get("cancelled") is True, f"annulation non effective : {result}")

    def confirm_after_cancel():
        result = call(ctx, "confirm_action", state["token"])
        expect(result.get("error_code") == "no_pending_action",
               f"confirm apres annulation devrait echouer : {result}")

    step("prepare_send_message (sans envoi)", prepare, critical=True)
    step("cancel_action", cancel)
    step("confirm_action refuse apres annulation", confirm_after_cancel)


def group_memory(ctx: Context, step) -> None:
    # Runs against the throwaway DB set in main() (JARVIS_MEMORY_PATH), never
    # the user's real memory. Checked independently by reading SQLite directly.
    db = Path(os.environ["JARVIS_MEMORY_PATH"])
    state = {}

    def rows(sql, *params):
        with sqlite3.connect(db) as conn:
            return conn.execute(sql, params).fetchall()

    def remember():
        result = call_ok(ctx, "remember", "fact", "dentiste", "Dr Martin a Lyon")
        state["id"] = result["memory"]["id"]
        expect(rows("SELECT content FROM memories WHERE id = ?", state["id"])
               == [("Dr Martin a Lyon",)], "souvenir absent de la base")
        expect(stat.S_IMODE(db.stat().st_mode) == 0o600, "base lisible par d'autres")

    def recall():
        result = call_ok(ctx, "recall", "comment s'appelle mon dentiste")
        expect(result.get("count") == 1, f"recall : {result}")

    def secret():
        result = call(ctx, "remember", "fact", "wifi", "mot de passe hunter2")
        expect(result.get("error_code") == "secret_refused", f"secret accepte : {result}")
        expect(not rows("SELECT 1 FROM memories WHERE content LIKE '%hunter2%'"),
               "secret ecrit en base")

    def propose():
        result = call_ok(ctx, "propose_memory", "person", "Marie", "Marie Dupont")
        expect(not rows("SELECT 1 FROM memories WHERE subject = 'Marie'"),
               "enregistre avant confirmation")
        call_ok(ctx, "confirm_action", result["token"])
        expect(rows("SELECT source FROM memories WHERE subject = 'Marie'") == [("inferred",)],
               "non enregistre apres confirmation")

    def forget():
        call_ok(ctx, "forget", state["id"])
        expect(not rows("SELECT 1 FROM memories WHERE id = ?", state["id"]), "toujours en base")

    def journal():
        result = call_ok(ctx, "recent_activity", 5)
        tools = [e.get("tool") for e in result.get("episodes", [])]
        expect("remember" in tools, f"journal : {tools}")
        expect(not rows("SELECT 1 FROM episodes WHERE target LIKE '%Martin%'"),
               "contenu du souvenir dans le journal")

    step("remember", remember, critical=True)
    step("recent_activity (journal)", journal)
    step("recall", recall)
    step("remember refuse un secret", secret)
    step("propose_memory + confirm_action", propose)
    step("forget", forget)


GROUPS = {
    "system": group_system,
    "volume": group_volume,
    "clipboard": group_clipboard,
    "files": group_files,
    "mouse": group_mouse,
    "screenshot": group_screenshot,
    "apps": group_apps,
    "textedit": group_textedit,
    "safari": group_safari,
    "messaging": group_messaging,
    "memory": group_memory,
}


# --- runner -----------------------------------------------------------------


def run_group(ctx: Context, name: str) -> None:
    blocked: list[str] = []

    def step(step_name: str, fn, critical: bool = False) -> None:
        """Run one check. A failed critical step skips the rest of the group,
        so later steps never act on a state that was not reached (e.g. typing
        while the wrong app is frontmost)."""
        started = time.monotonic()
        try:
            if blocked:
                raise Skipped(f"etape prealable echouee : {blocked[0]}")
            fn()
            status, detail = "pass", ""
        except Skipped as skip:
            status, detail = "skip", str(skip)
        except CheckFailed as failure:
            status, detail = "fail", str(failure)
        except Exception as error:
            status, detail = "fail", f"{type(error).__name__}: {error}"
        if status == "fail" and critical:
            blocked.append(step_name)
        result = StepResult(name, step_name, status, detail,
                            int((time.monotonic() - started) * 1000))
        ctx.results.append(result)
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[status]
        line = f"  [{mark}] {step_name} ({result.duration_ms} ms)"
        print(line + (f"\n         {detail}" if detail else ""), flush=True)

    print(f"\n== {name}", flush=True)
    missing = [p for p in REQUIRES.get(name, ()) if not ctx.perms.get(p)]
    if missing:
        step("(groupe)", lambda: (_ for _ in ()).throw(
            Skipped(f"prerequis manquant(s) : {', '.join(missing)}")))
        return
    try:
        GROUPS[name](ctx, step)
    except Exception as error:
        step("(setup)", lambda: (_ for _ in ()).throw(error))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--group", action="append", choices=sorted(GROUPS),
                        help="groupe a lancer (repetable) ; defaut : tous")
    parser.add_argument("--list", action="store_true", help="liste les groupes")
    parser.add_argument("--json", type=Path, help="ecrit le rapport JSON ici")
    parser.add_argument("--keep", action="store_true",
                        help="garde le dossier de travail (captures, fichiers)")
    parser.add_argument("--yes", action="store_true", help="pas de compte a rebours")
    args = parser.parse_args()

    if args.list:
        for name in GROUPS:
            print(name)
        return 0

    groups = args.group or list(GROUPS)

    # Must be inside $HOME (FilesCapability refuses anything outside).
    workdir = Path.home() / f"jarvis-smoke-{time.strftime('%Y%m%d-%H%M%S')}"
    workdir.mkdir()
    # Never touch the user's real long-term memory.
    os.environ["JARVIS_MEMORY_PATH"] = str(workdir / "memory.db")

    from jarvis.live.registry import create_live_tools

    tools = {tool.info.name: tool for tool in create_live_tools()}
    ctx = Context(tools=tools, workdir=workdir, perms=permissions())
    print("Permissions : " + ", ".join(
        f"{k}={'oui' if v else 'NON'}" for k, v in ctx.perms.items()))

    if not args.yes and any(g in groups for g in ("textedit", "safari", "mouse", "apps")):
        print("Ce test pilote clavier, souris et apps. Ne touche pas au Mac.")
        for remaining in (3, 2, 1):
            print(f"  depart dans {remaining}...", flush=True)
            time.sleep(1)

    try:
        for name in groups:
            run_group(ctx, name)
    finally:
        if args.keep:
            print(f"\nDossier de travail conserve : {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    counts = {s: sum(r.status == s for r in ctx.results) for s in ("pass", "fail", "skip")}
    print(f"\n{counts['pass']} ok, {counts['fail']} echec(s), {counts['skip']} ignore(s)")

    if args.json:
        args.json.write_text(json.dumps(
            [r.__dict__ for r in ctx.results], ensure_ascii=False, indent=2))

    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
