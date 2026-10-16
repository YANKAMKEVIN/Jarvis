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
from datetime import datetime, timedelta
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
    "whatsapp": ("accessibility", "screen_unlocked"),
    "vision_click": ("accessibility", "screen_unlocked"),
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


def group_whatsapp(ctx: Context, step) -> None:
    # Live recipient verification against the real WhatsApp UI, WITHOUT sending.
    # Opt-in: set JARVIS_SMOKE_WHATSAPP_CONTACT to a SAFE contact (yourself or a
    # test contact). prepare_send_message runs the full verify + navigate path
    # and only REGISTERS a pending send; we cancel it immediately, so nothing is
    # ever sent (the send would happen only on confirm_action, never called).
    contact = os.environ.get("JARVIS_SMOKE_WHATSAPP_CONTACT", "").strip()
    state = {}

    def prepare_and_verify():
        if not contact:
            raise Skipped(
                "definis JARVIS_SMOKE_WHATSAPP_CONTACT=<contact sur> pour activer ce test")
        result = call(
            ctx, "prepare_send_message", "WhatsApp",
            "Test smoke Jarvis - ne pas envoyer.", contact,
        )
        if result.get("error_code") == "recipient_not_verified":
            raise CheckFailed(
                "conversation non verifiee : la bonne discussion n'a pas pu etre ouverte")
        expect(result.get("ok") is True,
               f"prepare -> {result.get('error_code')} : {result.get('message')}")
        expect(result.get("requires_confirmation") is True, "confirmation non requise")
        expect(bool(result.get("token")), "token absent")
        expect(result.get("recipient_verified") is True, "destinataire non marque verifie")
        state["token"] = result["token"]

    def cancel_without_sending():
        if "token" not in state:
            raise Skipped("pas de token (verification ignoree ou echouee)")
        result = call_ok(ctx, "cancel_action", state["token"])
        expect(result.get("cancelled") is True, f"annulation non effective : {result}")

    step("verif destinataire + composer (sans envoi)", prepare_and_verify, critical=True)
    step("annulation (rien n'est envoye)", cancel_without_sending)


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


def group_knowledge(ctx: Context, step) -> None:
    # Exercises the real production search path (SearXNG if up, else keyless
    # Google News / DuckDuckGo). Read-only, no Mac UI, no LLM synthesis -- fast.
    # Needs the network; without it the steps SKIP rather than fail.
    from jarvis.knowledge.keyless import FallbackProvider, KeylessWebProvider
    from jarvis.knowledge.models import SearchMode
    from jarvis.knowledge.searxng import SearXNGProvider

    provider = FallbackProvider(SearXNGProvider(), KeylessWebProvider())

    def news():
        try:
            results = provider.search("France", mode=SearchMode.NEWS)
        except Exception as error:
            raise Skipped(f"pas de reseau : {error}")
        expect(len(results) >= 1, "aucun resultat d'actualite")
        first = results[0]
        expect(first.url.startswith("http"), f"url invalide : {first.url}")
        expect(bool(first.title.strip()), "titre vide")
        expect(first.published_date is not None, "date d'actualite non normalisee")

    def general():
        try:
            results = provider.search("Wikipedia", mode=SearchMode.GENERAL)
        except Exception as error:
            raise Skipped(f"pas de reseau : {error}")
        # General scraping is best effort; tolerate zero but verify shape if any.
        if not results:
            raise Skipped("aucun resultat general (scraping best effort)")
        expect(results[0].url.startswith("http"), f"url invalide : {results[0].url}")

    step("recherche actus (chemin live)", news)
    step("recherche generale (best effort)", general)


def group_compute(ctx: Context, step) -> None:
    def calc():
        result = call_ok(ctx, "calculate", "(12 + 8) * 3")
        expect(result.get("result") == 60, f"calcul faux : {result.get('result')}")

    def convert():
        result = call_ok(ctx, "convert_units", 10, "km", "mi")
        expect(abs(result.get("result", 0) - 6.2137) < 0.01, f"conversion fausse : {result}")

    def rejects_code():
        result = call(ctx, "calculate", "__import__('os')")
        expect(result.get("ok") is False, "expression dangereuse acceptee")

    step("calculate", calc)
    step("convert_units", convert)
    step("calculate rejette du code", rejects_code)


def group_webread(ctx: Context, step) -> None:
    def summarize():
        result = call(ctx, "summarize_url", "https://example.com", "de quoi parle cette page ?")
        if result.get("error_code") in ("fetch_failed", "model_error"):
            raise Skipped(f"reseau ou modele indisponible : {result.get('error_code')}")
        expect(result.get("ok") is True, f"summarize -> {result.get('error_code')}")
        expect(bool(result.get("message")), "resume vide")

    step("summarize_url (reseau + modele)", summarize)


def group_context(ctx: Context, step) -> None:
    def remember():
        call_ok(ctx, "remember_context", "on teste le smoke du contexte")

    def recall():
        result = call_ok(ctx, "recall_context")
        expect("on teste le smoke du contexte" in result.get("context", []),
               "le contexte retenu n'est pas rappele")

    step("remember_context", remember, critical=True)
    step("recall_context", recall)


def group_shortcuts(ctx: Context, step) -> None:
    # Reads the shortcuts list (safe) and verifies an unknown shortcut is
    # refused. Never runs a real user shortcut (could do anything).
    def listed():
        try:
            result = call(ctx, "list_shortcuts")
        except Exception as error:
            raise Skipped(f"shortcuts indisponible : {error}")
        if not result.get("ok"):
            raise Skipped(f"liste indisponible : {result.get('error_code')}")
        expect("count" in result, "count manquant")

    def run_unknown():
        result = call(ctx, "run_shortcut", "RaccourciInexistantSmokeXYZ")
        expect(result.get("ok") is False, "un raccourci inexistant ne doit pas reussir")

    step("list_shortcuts", listed)
    step("run_shortcut (inconnu -> refus)", run_unknown)


def group_macros(ctx: Context, step) -> None:
    # Save/list/delete against the throwaway store; never runs a macro (that
    # would launch a real planner task driving the Mac).
    def save():
        result = call_ok(ctx, "save_macro", "SmokeMacro", "ouvre Safari")
        expect(result.get("name") == "SmokeMacro", f"macro non enregistree : {result}")

    def listed():
        result = call_ok(ctx, "list_macros")
        names = [m["name"] for m in result.get("macros", [])]
        expect("SmokeMacro" in names, "macro absente de la liste")

    def run_unknown():
        result = call(ctx, "run_macro", "macro_inexistante_smoke")
        expect(result.get("error_code") == "macro_not_found", f"macro inconnue acceptee : {result}")

    def delete():
        result = call_ok(ctx, "delete_macro", "SmokeMacro")
        expect(result.get("ok") is True, f"suppression : {result}")

    step("save_macro", save, critical=True)
    step("list_macros", listed)
    step("run_macro (inconnue -> refus)", run_unknown)
    step("delete_macro", delete)


def group_diagnostics(ctx: Context, step) -> None:
    def check():
        result = call_ok(ctx, "self_check")
        checks = result.get("checks", {})
        for name in ("accessibility", "vision", "local_model", "imap_mail"):
            expect(name in checks, f"verification {name} absente")
            expect("ok" in checks[name], f"{name} sans champ ok")

    step("self_check", check)


def group_notes(ctx: Context, step) -> None:
    # Writes to the throwaway notes dir set in main(), not the real Documents.
    state = {}

    def save():
        result = call_ok(ctx, "save_note", "Acheter du pain et appeler le plombier.", "Courses")
        expect(bool(result.get("path")), "chemin de note absent")
        state["path"] = result["path"]
        expect(Path(state["path"]).exists(), "le fichier de note n'existe pas")

    def listed():
        result = call_ok(ctx, "list_notes")
        names = [n["name"] for n in result.get("notes", [])]
        expect(any(Path(state["path"]).name == n for n in names), "note absente de la liste")

    step("save_note", save, critical=True)
    step("list_notes", listed)


def group_storage(ctx: Context, step) -> None:
    def status():
        result = call_ok(ctx, "get_storage_status")
        expect(isinstance(result.get("free_gb"), (int, float)), "free_gb manquant")
        expect(isinstance(result.get("total_gb"), (int, float)), "total_gb manquant")
        expect(result.get("percent_free") is not None, "percent_free manquant")

    step("get_storage_status", status)


def group_search(ctx: Context, step) -> None:
    def spotlight():
        # Spotlight should find at least this project's own files for 'jarvis'.
        try:
            result = call(ctx, "search_files_by_content", "jarvis")
        except Exception as error:
            raise Skipped(f"spotlight indisponible : {error}")
        expect(result.get("ok") is True, f"recherche -> {result.get('error_code')}")
        expect(result.get("result_count", 0) >= 0, "result_count manquant")

    step("search_files_by_content", spotlight)


def group_reminders(ctx: Context, step) -> None:
    # Uses the throwaway reminders DB set in main(); never the real store.
    state = {}

    def set_one():
        when = (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")
        result = call_ok(ctx, "set_reminder", "Rappel smoke test", when)
        expect("requires_confirmation" not in result, "un rappel ne doit pas demander de confirmation")
        state["id"] = result["reminder_id"]

    def list_them():
        result = call_ok(ctx, "list_reminders")
        ids = [r["id"] for r in result.get("reminders", [])]
        expect(state["id"] in ids, "le rappel cree n'apparait pas dans la liste")

    def cancel_it():
        result = call_ok(ctx, "cancel_reminder", state["id"])
        expect(result.get("ok") is True, f"annulation : {result}")

    def reject_past():
        result = call(ctx, "set_reminder", "trop tard", "2000-01-01T09:00")
        expect(result.get("error_code") == "due_in_past", f"passe accepte : {result}")

    step("set_reminder", set_one, critical=True)
    step("list_reminders", list_them)
    step("cancel_reminder", cancel_it)
    step("set_reminder refuse le passe", reject_past)


def group_clipboard_rewrite(ctx: Context, step) -> None:
    def rewrite():
        call_ok(ctx, "set_clipboard_text", "jai manger une pomme")
        result = call(ctx, "rewrite_clipboard", "corrige l'orthographe")
        if result.get("error_code") == "model_error":
            raise Skipped("modele local indisponible (Ollama)")
        expect(result.get("ok") is True, f"rewrite -> {result.get('error_code')}")
        expect(result.get("transformed_length", 0) > 0, "texte transforme vide")
        # The clipboard now holds the transformed text (not the original).
        after = call_ok(ctx, "get_clipboard_text")
        expect(after.get("has_text") is True, "presse-papiers vide apres transformation")

    step("rewrite_clipboard (modele local)", rewrite)


def group_calendar(ctx: Context, step) -> None:
    # Read-only: never creates an event in the user's real calendar.
    def read_today():
        try:
            result = call(ctx, "list_calendar_events", 0)
        except Exception as error:
            raise Skipped(f"agenda indisponible : {error}")
        if not result.get("ok"):
            raise Skipped(f"agenda non lisible : {result.get('error_code')}")
        expect("event_count" in result, "event_count manquant")

    step("list_calendar_events (lecture)", read_today)


def group_briefing(ctx: Context, step) -> None:
    # The briefing runs in the background and is announced by voice; from the
    # tool call we can only confirm it started (its result is not returned here).
    def start():
        result = call_ok(ctx, "morning_briefing")
        expect(result.get("briefing_started") is True, "briefing non demarre")

    step("morning_briefing (demarrage)", start)


def group_document(ctx: Context, step) -> None:
    def ask():
        doc = ctx.workdir / "smoke_doc.txt"
        doc.write_text("La reunion est prevue le 20 octobre 2026 a 14 heures.")
        result = call(ctx, "ask_about_document", str(doc), "Quelle est la date de la reunion ?")
        if result.get("error_code") == "model_error":
            raise Skipped("modele local indisponible (Ollama)")
        expect(result.get("ok") is True, f"ask -> {result.get('error_code')}")
        expect(bool(result.get("message")), "reponse vide")

    step("ask_about_document (modele local)", ask)


def group_vision_click(ctx: Context, step) -> None:
    # Safe check: a nonexistent target must be refused (no coordinates -> no
    # blind click). We never auto-click a real element in the smoke test.
    def refuses_unknown():
        result = call(ctx, "click_element", "element_inexistant_smoke_xyz_123")
        # The point: it must REFUSE (no blind click). Any failure code that means
        # "couldn't ground a target" is acceptable.
        expect(result.get("ok") is False, "un element inexistant ne doit pas etre clique")
        expect(result.get("error_code") in (
            "ui_element_not_found", "no_grounded_target", "ambiguous_ui_element",
            "focused_window_unavailable", "accessibility_denied",
        ), f"code inattendu : {result.get('error_code')}")

    step("click_element refuse une cible inconnue", refuses_unknown)


def group_scheduled(ctx: Context, step) -> None:
    # Schedule -> confirm -> list -> cancel, against the throwaway store set in
    # main(). Never delivers (no send): delivery is the runner's job, not here.
    state = {}

    def schedule():
        when = (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")
        prep = call_ok(ctx, "schedule_message", "ContactSmokeTest", "ne pas envoyer", when)
        expect(prep.get("requires_confirmation") is True, "pas de confirmation requise")
        expect(bool(prep.get("token")), "token absent")
        confirmed = call_ok(ctx, "confirm_action", prep["token"])
        expect(confirmed.get("scheduled_id") is not None, f"non planifie : {confirmed}")
        state["id"] = confirmed["scheduled_id"]

    def recurring_rejects_bad_value():
        when = (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")
        result = call(ctx, "schedule_message", "X", "y", when, "WhatsApp", "hourly")
        expect(result.get("error_code") == "invalid_recurrence", f"recurrence invalide acceptee : {result}")

    def list_them():
        result = call_ok(ctx, "list_scheduled_messages")
        ids = [m["id"] for m in result.get("scheduled", [])]
        expect(state["id"] in ids, "le message planifie n'apparait pas")

    def cancel_it():
        result = call_ok(ctx, "cancel_scheduled_message", state["id"])
        expect(result.get("ok") is True, f"annulation : {result}")

    step("schedule_message + confirm (sans envoi)", schedule, critical=True)
    step("schedule_message refuse une recurrence invalide", recurring_rejects_bad_value)
    step("list_scheduled_messages", list_them)
    step("cancel_scheduled_message", cancel_it)


def group_privacy(ctx: Context, step) -> None:
    def overview():
        result = call_ok(ctx, "privacy_overview")
        for key in ("memory_count", "scheduled_count", "reminder_count", "activity_count"):
            expect(isinstance(result.get(key), int), f"{key} manquant")

    step("privacy_overview", overview)


def group_mail(ctx: Context, step) -> None:
    # Read-only: never creates a draft in the user's real Mail.
    def read_unread():
        try:
            result = call(ctx, "list_unread_emails", 5)
        except Exception as error:
            raise Skipped(f"messagerie indisponible : {error}")
        if not result.get("ok"):
            raise Skipped(f"mails non lisibles : {result.get('error_code')}")
        expect("unread_count" in result, "unread_count manquant")

    step("list_unread_emails (lecture)", read_unread)


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
    "whatsapp": group_whatsapp,
    "memory": group_memory,
    "knowledge": group_knowledge,
    "compute": group_compute,
    "webread": group_webread,
    "context": group_context,
    "shortcuts": group_shortcuts,
    "macros": group_macros,
    "diagnostics": group_diagnostics,
    "notes": group_notes,
    "storage": group_storage,
    "search": group_search,
    "reminders": group_reminders,
    "clipboard_rewrite": group_clipboard_rewrite,
    "calendar": group_calendar,
    "mail": group_mail,
    "document": group_document,
    "briefing": group_briefing,
    "vision_click": group_vision_click,
    "scheduled": group_scheduled,
    "privacy": group_privacy,
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
    # Never touch the user's real long-term memory or scheduled stores.
    os.environ["JARVIS_MEMORY_PATH"] = str(workdir / "memory.db")
    os.environ["JARVIS_SCHEDULE_PATH"] = str(workdir / "scheduled.db")
    os.environ["JARVIS_REMINDERS_PATH"] = str(workdir / "reminders.db")
    os.environ["JARVIS_NOTES_DIR"] = str(workdir / "notes")
    os.environ["JARVIS_MACROS_PATH"] = str(workdir / "macros.db")
    os.environ["JARVIS_CONTEXT_PATH"] = str(workdir / "context.db")

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
