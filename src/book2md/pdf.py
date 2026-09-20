import shutil
import subprocess
from pathlib import Path

from .errors import ConversionError


def require_command(name: str) -> str:
    command = shutil.which(name)
    if not command:
        raise ConversionError(
            f"PDF conversion requires '{name}' from Poppler. Install Poppler and try again."
        )
    return command


def convert_pdf(source: Path, output: Path) -> None:
    pdftotext = require_command("pdftotext")
    pdfimages = require_command("pdfimages")
    text_result = subprocess.run(
        [pdftotext, "-layout", str(source), "-"],
        capture_output=True,
        text=True,
    )
    if text_result.returncode:
        raise ConversionError(text_result.stderr.strip() or "pdftotext could not read the PDF.")
    if not text_result.stdout.strip():
        raise ConversionError(
            "No selectable text was found. OCR for scanned PDFs is not supported."
        )

    output.mkdir()
    assets = output / "images"
    assets.mkdir()
    image_result = subprocess.run(
        [pdfimages, "-all", str(source), str(assets / "page")],
        capture_output=True,
        text=True,
    )
    if image_result.returncode:
        raise ConversionError(image_result.stderr.strip() or "pdfimages could not extract images.")

    image_files = sorted(path.relative_to(output).as_posix() for path in assets.iterdir())
    lines = [f"# {source.stem}", "", text_result.stdout.strip()]
    if image_files:
        lines.extend(["", "## Extracted images", ""])
        lines.extend(f"![]({image})" for image in image_files)
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

