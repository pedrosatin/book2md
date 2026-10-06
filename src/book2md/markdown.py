import re

_ESCAPES = str.maketrans({"\\": "\\\\", "<": "&lt;", ">": "&gt;", "[": "\\[", "]": "\\]"})
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")
SAFE_SCHEMES = {"http", "https", "mailto"}


def escape_text(text: str) -> str:
    """Neutralize raw HTML and link syntax in prose coming from a book."""
    return text.translate(_ESCAPES)


def fence_block(text: str) -> str:
    """Wrap text in a backtick fence that no line of the text can close."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


def safe_url(url: str) -> str | None:
    """Return a link target that is safe to emit, or None to drop the link.

    Allows http, https, mailto, fragments and scheme-less relative paths.
    Every other scheme (javascript:, data:, vbscript:, file:) and
    protocol-relative URLs are rejected.
    """
    cleaned = re.sub(r"[\x00-\x20\x7f-\x9f]+", "", url)
    if cleaned.startswith(("//", "\\")):
        return None
    scheme = _SCHEME.match(cleaned)
    if scheme and scheme.group(1).lower() not in SAFE_SCHEMES:
        return None
    return quote_target(url.strip())


def quote_target(url: str) -> str:
    return "".join(
        f"%{ord(char):02X}" if char in " ()<>\"\\" or ord(char) < 32 or ord(char) == 127 else char
        for char in url
    )
