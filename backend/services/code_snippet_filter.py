import re


_PYTHON_KEYWORDS = {
    "if", "elif", "else", "for", "while", "return", "yield", "class", "def",
    "try", "except", "finally", "with", "from", "import", "raise", "assert",
    "break", "continue", "pass", "lambda",
}


def is_actual_code(snippet: str | None) -> bool:
    """Return True when a fill-in snippet is executable Python, not teaching text."""
    s = (snippet or "").strip()
    if not s:
        return False

    lowered = s.lower().strip()
    if lowered.startswith((
        '"""', "'''", "#", "//", "/*", "*", ":return", ":param", ":type",
        "input:", "output:", "example:", "goal:", "key idea:", "return:",
    )):
        return False

    if re.match(r"^[a-z][a-z\s`'\",.-]+[.!?]?$", s, flags=re.IGNORECASE):
        return False

    if re.match(
        r"^(find|return|check|get|set|the|a|an|this|calculate|compute|determine|given|initialize|store|track|update|increment|decrement)\b",
        s,
        flags=re.IGNORECASE,
    ):
        return False

    if "`" in s and not any(token in s for token in ("=", "(", "[", "{", "}", ":", "+", "-", "*", "/")):
        return False

    first_word = re.match(r"^[A-Za-z_][A-Za-z0-9_]*", s)
    if first_word and first_word.group(0) in _PYTHON_KEYWORDS:
        return True

    code_patterns = [
        r"^[A-Za-z_][A-Za-z0-9_\.]*\s*=",
        r"^[A-Za-z_][A-Za-z0-9_\.]*\s*(\+=|-=|\*=|/=|//=|%=)",
        r"^[A-Za-z_][A-Za-z0-9_\.]*\s*\(",
        r"\[[^\]]*\]",
        r"\{.*\}",
        r"\.[A-Za-z_][A-Za-z0-9_]*\(",
        r"\b(range|len|enumerate|zip|sorted|min|max|sum|Counter|defaultdict|deque|heappush|heappop)\(",
        r"(==|!=|<=|>=|<|>)",
    ]
    return any(re.search(pattern, s) for pattern in code_patterns)
