"""Contract: every tool is classified read / local / mac / outward (idea 23)."""
from jarvis.live.registry import SAFE_MODE_ALLOWED, create_live_registry
from jarvis.live.tool_effects import FAMILIES, LOCAL, MAC, OUTWARD, READ, effect_of


def registry_tool_names():
    registry = create_live_registry()
    names = {tool.info.name for tool in registry.livekit_tools()}
    return names | {tool.info.name for tool in registry.planner_tools}


def test_every_registry_tool_has_exactly_one_effect():
    names = registry_tool_names()
    unclassified = sorted(name for name in names if effect_of(name) is None)
    assert not unclassified, f"Classez ces tools dans live/tool_effects.py : {unclassified}"
    families = list(FAMILIES.values())
    for index, family in enumerate(families):
        for other in families[index + 1:]:
            assert not family & other, family & other
    assert set().union(*families) <= names, "tool_effects.py lists a tool that no longer exists"


def test_read_tools_are_usable_in_safe_mode():
    assert READ <= SAFE_MODE_ALLOWED, sorted(READ - SAFE_MODE_ALLOWED)


def test_mac_and_outward_tools_are_blocked_in_safe_mode():
    assert not (MAC | OUTWARD) & SAFE_MODE_ALLOWED, sorted((MAC | OUTWARD) & SAFE_MODE_ALLOWED)


def test_safe_mode_allows_only_classified_read_or_local_tools():
    assert SAFE_MODE_ALLOWED <= READ | LOCAL
