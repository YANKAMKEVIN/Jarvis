"""One AppleScript escaping helper, used everywhere (idea 16)."""
import inspect

import pytest

from jarvis.tools import browser, claude_cli, keyboard, macos
from jarvis.tools.applescript import escape_applescript, quote_applescript


@pytest.mark.parametrize("raw,expected", [
    ('Safari', 'Safari'),
    ('a"b', 'a\\"b'),
    ('C:\\dir', 'C:\\\\dir'),
    ('fin\\', 'fin\\\\'),
    ('ligne 1\nligne 2', 'ligne 1\\nligne 2'),
    ('a\r\nb\tc', 'a\\r\\nb\\tc'),
    ('« titre » “cité”', '« titre » “cité”'),
    ('bip\x07\x00', 'bip'),
])
def test_escape(raw, expected):
    assert escape_applescript(raw) == expected


def literal_end(script_literal):
    """Index where an AppleScript string literal starting at 0 ends."""
    index = 1
    while index < len(script_literal):
        char = script_literal[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index
        index += 1
    return None


@pytest.mark.parametrize("payload", [
    'x" & (do shell script "id") & "', 'x\\" to quit\ndo shell script "id"', '\\', '"' * 5, 'a\\\\"b',
])
def test_quoted_payload_cannot_close_the_literal_early(payload):
    quoted = quote_applescript(payload)
    assert literal_end(quoted) == len(quoted) - 1
    assert "\n" not in quoted and "\r" not in quoted


def test_every_tool_uses_the_shared_helper():
    for module in (macos, browser, keyboard, claude_cli):
        source = inspect.getsource(module)
        assert '.replace("\\\\", "\\\\\\\\")' not in source, module.__name__
    assert macos.MacOSTools._escape_applescript('a"b') == 'a\\"b'
    assert keyboard.KeyboardTools._applescript_string('x"') == '"x\\""'
    assert claude_cli._osa_quote("echo \"hi\"\nls") == '"echo \\"hi\\"\\nls"'
