"""Command line for scheduled messages.

    python -m jarvis.schedule deliver   # send any due, deliverable messages
    python -m jarvis.schedule list      # show pending scheduled messages
    python -m jarvis.schedule install   # print the launchd agent + instructions
    python -m jarvis.schedule status    # agent present? last delivery? late items?

`deliver` is what the launchd agent runs every minute. `install` only prints the
agent file and the commands to enable it -- it changes nothing on the system, so
you stay in control of the persistent background agent.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import jarvis
from jarvis.capabilities.messaging import MessagingCapability
from jarvis.schedule.reminders import ReminderStore, deliver_reminders
from jarvis.schedule.runner import deliver_due, macos_notifier, macos_screen_unlocked
from jarvis.schedule.store import ScheduledMessageStore


from jarvis.schedule.agent import LAUNCHD_LABEL, agent_plist_path, scheduler_agent_status

# A pending item this long past its due time means the agent did not run.
LATE_AFTER_SECONDS = 180


def _paths() -> tuple[str, str]:
    src_dir = Path(jarvis.__file__).resolve().parents[1]
    project_root = src_dir.parent
    return str(src_dir), str(project_root)


def cmd_deliver() -> int:
    store = ScheduledMessageStore()
    messaging = MessagingCapability()
    results = deliver_due(
        store,
        messaging,
        screen_unlocked=macos_screen_unlocked,
        notifier=macos_notifier,
    )
    reminders = deliver_reminders(ReminderStore(), notifier=macos_notifier)
    print(
        f"deliver: sent={len(results['sent'])} "
        f"deferred={len(results['deferred'])} failed={len(results['failed'])} "
        f"reminders={len(reminders)}"
    )
    return 0


def cmd_list() -> int:
    store = ScheduledMessageStore()
    uncertain = [row for row in store.list("failed") if (row.get("last_error") or "").startswith("envoi incertain")]
    rows = sorted(store.list("pending") + store.list("sending") + uncertain, key=lambda row: row["due_at"])
    if not rows:
        print("Aucun message planifie en attente.")
        return 0
    for row in rows:
        when = datetime.fromtimestamp(row["due_at"]).isoformat(timespec="minutes")
        if row["status"] != "pending":
            print("A verifier : envoi interrompu ou en cours ; aucune relance automatique.")
        print(f"[{row['id']}] {when}  ->  {row['recipient']} ({row['app']})")
    return 0


def cmd_install() -> int:
    src_dir, project_root = _paths()
    python = sys.executable
    log = str(Path(project_root) / "scheduler.log")
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>jarvis.schedule</string>
        <string>deliver</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict><key>PYTHONPATH</key><string>{src_dir}</string></dict>
    <key>WorkingDirectory</key><string>{project_root}</string>
    <key>StartInterval</key><integer>60</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>{log}</string>
    <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>"""
    target = f"$HOME/Library/LaunchAgents/{LAUNCHD_LABEL}.plist"
    print(plist)
    print()
    print("# Pour activer (a lancer toi-meme) :")
    print(f"cat > {target} <<'PLIST'")
    print(plist)
    print("PLIST")
    print(f"launchctl bootstrap gui/$(id -u) {target}")
    print(f"# (macOS ancien, commande depreciee : launchctl load {target})")
    print()
    print("# Pour desactiver plus tard :")
    print(f"launchctl bootout gui/$(id -u)/{LAUNCHD_LABEL} && rm {target}")
    print()
    print("# Verifier ensuite : python -m jarvis.schedule status")
    return 0


def _when(timestamp) -> str:
    return datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="minutes") if timestamp else "jamais"


def schedule_status(now: float | None = None, home: Path | None = None, platform: str | None = None) -> dict:
    """Agent presence, last delivery and late items, read from the local stores."""
    now = time.time() if now is None else now
    messages = ScheduledMessageStore()
    reminders = ReminderStore()
    sent = [row.get("sent_at") or 0 for row in messages.list("sent", limit=500)]
    done = [row.get("done_at") or 0 for row in reminders.list("done", limit=500)]
    late_messages = [row for row in messages.list("pending", limit=500) if row["due_at"] < now - LATE_AFTER_SECONDS]
    late_reminders = [row for row in reminders.list("pending", limit=500) if row["due_at"] < now - LATE_AFTER_SECONDS]
    return {
        "agent": scheduler_agent_status(home, platform),
        "plist": str(agent_plist_path(home)),
        "last_message_sent": max(sent, default=0) or None,
        "last_reminder_delivered": max(done, default=0) or None,
        "late_messages": len(late_messages),
        "late_reminders": len(late_reminders),
    }


def cmd_status(now: float | None = None, home: Path | None = None, platform: str | None = None) -> int:
    status = schedule_status(now, home, platform)
    agent = {"installed": "installe", "missing": "ABSENT", "unsupported": "sans objet (pas macOS)"}[status["agent"]]
    print(f"Agent launchd {LAUNCHD_LABEL} : {agent} ({status['plist']})")
    print(f"Dernier message envoye : {_when(status['last_message_sent'])}")
    print(f"Dernier rappel livre : {_when(status['last_reminder_delivered'])}")
    print(f"En retard : {status['late_messages']} message(s), {status['late_reminders']} rappel(s)")
    late = status["late_messages"] or status["late_reminders"]
    if status["agent"] == "missing":
        print("Rien ne part sans l'agent : python -m jarvis.schedule install, puis la commande launchctl bootstrap affichee.")
    elif late and status["agent"] == "installed":
        print(f"L'agent est installe mais n'a pas livre : verifiez launchctl print gui/{os.getuid()}/{LAUNCHD_LABEL} et scheduler.log.")
    return 1 if status["agent"] == "missing" or (late and status["agent"] == "installed") else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis.schedule", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("deliver", help="Envoyer les messages dus et delivrables.")
    sub.add_parser("list", help="Lister les messages planifies en attente.")
    sub.add_parser("install", help="Imprimer l'agent launchd et les instructions.")
    sub.add_parser("status", help="Agent installe, derniere livraison, elements en retard.")
    args = parser.parse_args(argv)

    if args.command == "deliver":
        return cmd_deliver()
    if args.command == "list":
        return cmd_list()
    if args.command == "install":
        return cmd_install()
    if args.command == "status":
        return cmd_status()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
