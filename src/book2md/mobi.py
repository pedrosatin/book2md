import shutil
import tempfile
from pathlib import Path

from .epub import convert_epub
from .errors import ConversionError
from .process import run_converter


def convert_mobi(source: Path, output: Path) -> None:
    ebook_convert = shutil.which("ebook-convert")
    if not ebook_convert:
        raise ConversionError(
            "MOBI conversion requires Calibre's 'ebook-convert'. Install Calibre and try again."
        )
    with tempfile.TemporaryDirectory(prefix="book2md-") as temporary:
        epub = Path(temporary) / "book.epub"
        result = run_converter([ebook_convert, str(source), str(epub)])
        if result.returncode:
            raise ConversionError(result.stderr.strip() or "ebook-convert could not convert the MOBI.")
        convert_epub(epub, output)
