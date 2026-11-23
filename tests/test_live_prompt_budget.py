"""The Live system prompt stays bounded (idea 10).

Every turn re-sends it: tool-specific guidance belongs in the tool's own
description. Raise these limits only with a reason, after deduplicating.
"""
from jarvis.live.prompts import LIVE_SYSTEM_PROMPT

MAX_PROMPT_CHARS = 33_000
MAX_LINE_CHARS = 1_500


def test_prompt_size_is_bounded():
    assert len(LIVE_SYSTEM_PROMPT) <= MAX_PROMPT_CHARS, len(LIVE_SYSTEM_PROMPT)


def test_no_line_is_a_wall_of_text_and_none_is_repeated():
    lines = [line for line in LIVE_SYSTEM_PROMPT.splitlines() if line.strip()]
    assert max(len(line) for line in lines) <= MAX_LINE_CHARS
    assert len(lines) == len(set(lines))


def test_guidance_moved_into_tool_descriptions():
    from jarvis.live.registry import create_live_registry
    tools = {tool.info.name: tool.info.description for tool in create_live_registry().livekit_tools()}
    assert "facture au token" in tools["token_usage"]
    assert "imap_not_configured" in tools["summarize_unread_emails"]
    assert "mode securite" in tools["run_claude_task"]
    assert "Ne danse jamais sans demande" in tools["dance_avatar"]
