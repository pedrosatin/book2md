import re

_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")
MAX_MESSAGE = 500


def sanitize(text: object) -> str:
    """Replace terminal control and escape characters; bound the length."""
    clean = _UNSAFE.sub(" ", str(text)).strip()
    return clean if len(clean) <= MAX_MESSAGE else clean[:MAX_MESSAGE] + "..."


class ConversionError(Exception):
    """Raised when book2md cannot safely complete a conversion."""

    def __init__(self, message: object = ""):
        super().__init__(sanitize(message))
