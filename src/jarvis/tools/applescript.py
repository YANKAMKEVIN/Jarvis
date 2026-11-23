"""The one way to put untrusted text inside an AppleScript string literal.

Every script built from a name, URL, title or typed text goes through here:
a stray double quote or backslash would otherwise end the literal and let
the rest of the text run as AppleScript.
"""

_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",   # one physical line: the script stays a single `osascript -e`
    "\r": "\\r",
    "\t": "\\t",
}


def escape_applescript(value) -> str:
    """Content of a double-quoted AppleScript literal, without the quotes.

    Typographic quotes (“ ” « ») are ordinary characters inside a literal and
    are kept as typed; other control characters are dropped.
    """
    text = str(value)
    out = []
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 32 or ord(char) == 127:
            continue
        else:
            out.append(char)
    return "".join(out)


def quote_applescript(value) -> str:
    """A complete AppleScript string literal, quotes included."""
    return '"' + escape_applescript(value) + '"'
