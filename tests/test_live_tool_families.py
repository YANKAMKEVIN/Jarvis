"""livekit_tools() is assembled from one module per tool family (idea 9)."""
import importlib
from pathlib import Path

from jarvis.live.registry import create_live_registry

FAMILIES = ("system", "office", "insights", "windows", "files", "input",
            "messages", "memory", "web", "missions", "schedule", "privacy")


def test_each_family_defines_distinct_tools_all_exposed():
    registry = create_live_registry()
    exposed = {tool.info.name for tool in registry.livekit_tools()}
    seen = {}
    for family in FAMILIES:
        module = importlib.import_module(f"jarvis.live.tools_{family}")
        tools = getattr(module, f"{family}_tools")(registry)
        assert tools, family
        for name, tool in tools.items():
            assert tool.info.name == name
            assert name not in seen, f"{name} in {seen.get(name)} and {family}"
            seen[name] = family
    assert set(seen) - {"web_answer"} <= exposed
    assert "web_answer" in {tool.info.name for tool in registry.planner_tools}


def test_registry_module_stays_reviewable():
    source = Path(__file__).resolve().parents[1] / "src/jarvis/live/registry.py"
    assert len(source.read_text().splitlines()) < 1500
