import hashlib
import shutil
from pathlib import Path

from .errors import ConversionError
from .markdown import escape_text, fence_block
from .output import prepare_output
from .process import run_converter

MAX_IMAGES = 5000
MAX_ESTIMATED_IMAGE_BYTES = 4 * 1024 ** 3
MAX_IMAGE_DIR_BYTES = 256 * 1024 ** 2


def require_command(name: str) -> str:
    command = shutil.which(name)
    if not command:
        raise ConversionError(
            f"PDF conversion requires '{name}' from Poppler. Install Poppler and try again."
        )
    return command


def check_image_budget(listing: str) -> int:
    """Refuse PDFs whose image occurrences would amplify into too much output.

    pdfimages writes one file per occurrence, so a small PDF that repeats one
    image on many pages can expand hundreds of times. Parses `pdfimages -list`
    (two header lines, then one row per occurrence).
    """
    count = 0
    estimated = 0
    for line in listing.splitlines()[2:]:
        fields = line.split()
        if len(fields) < 8 or not fields[0].isdigit():
            continue
        try:
            width, height, components, bits = (int(value) for value in (*fields[3:5], *fields[6:8]))
        except ValueError:
            continue
        count += 1
        estimated += max(1, width * height * components * bits // 8)
        if count > MAX_IMAGES:
            raise ConversionError(
                f"The PDF has more than {MAX_IMAGES} embedded image occurrences; refusing to extract them."
            )
        if estimated > MAX_ESTIMATED_IMAGE_BYTES:
            raise ConversionError("The PDF images would expand to too much data; refusing to extract them.")
    return count


def deduplicate(directory: Path) -> None:
    """Remove byte-identical image files, keeping the first of each."""
    seen: set[str] = set()
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            path.unlink()
        else:
            seen.add(digest)


def convert_pdf(source: Path, output: Path) -> None:
    pdftotext = require_command("pdftotext")
    pdfimages = require_command("pdfimages")
    text_result = run_converter([pdftotext, "-layout", str(source), "-"])
    if text_result.returncode:
        raise ConversionError(text_result.stderr.strip() or "pdftotext could not read the PDF.")
    if not text_result.stdout.strip():
        raise ConversionError(
            "No selectable text was found. OCR for scanned PDFs is not supported."
        )

    listing = run_converter([pdfimages, "-list", str(source)])
    if listing.returncode:
        raise ConversionError(listing.stderr.strip() or "pdfimages could not list images.")
    check_image_budget(listing.stdout)

    prepare_output(output)
    assets = output / "images"
    assets.mkdir()
    image_result = run_converter(
        [pdfimages, "-all", str(source), str(assets / "page")],
        watch_dir=assets, max_dir_bytes=MAX_IMAGE_DIR_BYTES,
    )
    if image_result.returncode:
        raise ConversionError(image_result.stderr.strip() or "pdfimages could not extract images.")
    deduplicate(assets)

    image_files = sorted(path.relative_to(output).as_posix() for path in assets.iterdir())
    # The -layout text keeps indentation that Markdown would read as code blocks,
    # where escapes show up literally. A fence keeps the text as extracted and
    # stops it from forming links or HTML.
    lines = [f"# {escape_text(source.stem)}", "", fence_block(text_result.stdout.strip())]
    if image_files:
        lines.extend(["", "## Extracted images", ""])
        lines.extend(f"![]({image})" for image in image_files)
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
