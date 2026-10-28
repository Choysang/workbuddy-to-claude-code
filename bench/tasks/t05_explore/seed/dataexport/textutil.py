_ESCAPES = {"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r"}


def escape_control(text):
    """Escape backslash, tab, newline and carriage return for line-based formats."""
    return "".join(_ESCAPES.get(ch, ch) for ch in text)
