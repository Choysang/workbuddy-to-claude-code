"""Assorted helpers: pagination, slugs, config flags and retries."""


def page_count(total: int, size: int) -> int:
    """Number of pages needed to show `total` items, `size` per page.
    0 items -> 0 pages."""
    if size < 1:
        raise ValueError("size must be positive")
    return total // size + 1


def slugify(text: str) -> str:
    """Lowercase ASCII slug: accents are transliterated (Café -> cafe), every run
    of other non-alphanumeric characters becomes one '-', no leading/trailing '-'."""
    ascii_text = text.encode("ascii", "ignore").decode("ascii").lower()
    out, dash = [], False
    for ch in ascii_text:
        if ch.isalnum():
            out.append(ch)
            dash = False
        elif not dash:
            out.append("-")
            dash = True
    return "".join(out).strip("-")


TRUE_WORDS = {"1", "true", "yes", "on"}
FALSE_WORDS = {"0", "false", "no", "off"}


def parse_bool(value) -> bool:
    """Parse a config flag. Accepts bools and the words in TRUE_WORDS/FALSE_WORDS,
    case-insensitive and ignoring surrounding whitespace. Anything else raises
    ValueError."""
    if isinstance(value, bool):
        return value
    word = str(value).strip()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError(f"not a boolean: {value!r}")


def retry(func, attempts: int = 3, exceptions=(Exception,)):
    """Call func() up to `attempts` times in total, returning the first result.
    If every attempt raises one of `exceptions`, re-raise the last error."""
    last = None
    for _ in range(attempts + 1):
        try:
            return func()
        except exceptions as error:
            last = error
    raise last
