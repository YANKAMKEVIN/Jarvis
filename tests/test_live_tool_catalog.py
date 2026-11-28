"""Caracterisation du catalogue de tools Live.

Fige, dans tests/fixtures/live_tool_catalog.json, la liste ordonnee des tools
exposes a la voix et au planificateur, leur description et leur schema JSON,
ainsi que l'API publique de jarvis.live.registry. Tout decoupage du registre
doit laisser ce catalogue strictement identique.

Pour regenerer le fichier apres un changement VOLONTAIRE du catalogue :
    JARVIS_UPDATE_TOOL_CATALOG=1 python -m pytest tests/test_live_tool_catalog.py
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace

from livekit.agents.llm.utils import build_legacy_openai_schema

import jarvis.live.registry as registry_module
from jarvis.live.registry import SAFE_MODE_ALLOWED, ToolRegistry, create_live_registry

FIXTURE = Path(__file__).parent / "fixtures" / "live_tool_catalog.json"
PUBLIC_NAMES = ("DIRECT_PROMPT_APPS", "SAFE_MODE_ALLOWED", "ToolRegistry",
                "create_live_registry", "create_live_tools")


def _describe(tools):
    return [build_legacy_openai_schema(tool)["function"] for tool in tools]


def _catalog():
    registry = create_live_registry(
        memory_capability=SimpleNamespace(log_action=lambda *a, **k: None))
    voice = registry.livekit_tools()
    return {
        "voice_tools": _describe(voice),
        "planner_tools": [tool.info.name for tool in registry.planner_tools],
        "safe_mode_allowed": sorted(SAFE_MODE_ALLOWED),
        "direct_prompt_apps": sorted(registry_module.DIRECT_PROMPT_APPS),
        "registry_members": sorted(
            name for name in dir(ToolRegistry) if not name.startswith("__")),
    }


def test_public_api_is_still_importable_from_registry():
    for name in PUBLIC_NAMES:
        assert hasattr(registry_module, name), name


def test_tool_catalog_matches_snapshot():
    current = _catalog()
    if os.environ.get("JARVIS_UPDATE_TOOL_CATALOG") == "1":
        FIXTURE.write_text(json.dumps(current, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert [t["name"] for t in current["voice_tools"]] == [
        t["name"] for t in expected["voice_tools"]]
    for got, want in zip(current["voice_tools"], expected["voice_tools"]):
        assert got == want, got["name"]
    assert current == expected


def test_tool_names_are_unique():
    names = [t["name"] for t in _catalog()["voice_tools"]]
    assert len(names) == len(set(names))
