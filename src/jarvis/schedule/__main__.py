"""Command line for scheduled messages.

    python -m jarvis.schedule deliver   # send any due, deliverable messages
    python -m jarvis.schedule list      # show pending scheduled messages
    python -m jarvis.schedule install   # print the launchd agent + instructions

`deliver` is what the launchd agent runs every minute. `install` only prints the
agent file and the commands to enable it -- it changes nothing on the system, so
you stay in control of the persistent background agent.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import jarvis
from jarvis.capabilities.messaging import MessagingCapability
from jarvis.schedule.reminders import ReminderStore, deliver_reminders
from jarvis.schedule.runner import deliver_due, macos_notifier, macos_screen_unlocked
from jarvis.schedule.store import ScheduledMessageStore


LAUNCHD_LABEL = "com.jarvis.scheduler"


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
    rows = store.list("pending")
    if not rows:
        print("Aucun message planifie en attente.")
        return 0
    for row in rows:
        when = datetime.fromtimestamp(row["due_at"]).isoformat(timespec="minutes")
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
    print(f"launchctl load {target}")
    print()
    print("# Pour desactiver plus tard :")
    print(f"launchctl unload {target} && rm {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis.schedule", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("deliver", help="Envoyer les messages dus et delivrables.")
    sub.add_parser("list", help="Lister les messages planifies en attente.")
    sub.add_parser("install", help="Imprimer l'agent launchd et les instructions.")
    args = parser.parse_args(argv)

    if args.command == "deliver":
        return cmd_deliver()
    if args.command == "list":
        return cmd_list()
    if args.command == "install":
        return cmd_install()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
