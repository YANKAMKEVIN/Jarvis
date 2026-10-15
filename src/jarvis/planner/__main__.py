"""Run one planner task on the real Mac, outside the voice session.

    PYTHONPATH=src .venv/bin/python -m jarvis.planner "Quel est le volume actuel ?"
    PYTHONPATH=src .venv/bin/python -m jarvis.planner --model ministral-3:3b "..."

Uses the local Ollama model (free, private). Outward actions are only ever
prepared: a task that reaches one stops with status needs_confirmation, and
the pending action is cancelled on exit.
"""

import argparse
import asyncio
import json
import sys
import time

from jarvis.live.registry import create_live_tools
from jarvis.planner.engine import PlannerEngine
from jarvis.planner.models import OllamaPlannerModel


def main() -> int:
    parser = argparse.ArgumentParser(description="Lance une tache du planificateur Jarvis.")
    parser.add_argument("goal", help="objectif en langage naturel")
    parser.add_argument("--model", help="modele Ollama (defaut : JARVIS_PLANNER_MODEL ou granite4:3b)")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args()

    tools = create_live_tools()
    by_name = {tool.info.name: tool for tool in tools}
    engine = PlannerEngine(OllamaPlannerModel(model=args.model), tools, max_steps=args.max_steps)

    started = time.monotonic()
    outcome = asyncio.run(engine.run(args.goal))
    elapsed = time.monotonic() - started

    if outcome.pending:
        # Never leave a prepared outward action behind from a CLI run.
        asyncio.run(by_name["cancel_action"](outcome.pending["token"]))

    report = outcome.to_dict() | {"model": engine.model.name, "seconds": round(elapsed, 1)}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Modele : {report['model']}  ({report['seconds']} s)")
        for index, step in enumerate(report["steps"], 1):
            mark = "ok " if step["ok"] else "ECH"
            extra = f"  [{step['error_code']}]" if step.get("error_code") else ""
            print(f"  {index:2d}. {mark} {step['tool']}{extra}")
        print(f"Statut : {report['status']}")
        print(f"Resume : {report['summary']}")
    return 0 if outcome.status in ("completed", "needs_confirmation") else 1


if __name__ == "__main__":
    sys.exit(main())
