import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from .epub import convert_epub
from .errors import ConversionError, sanitize
from .mobi import convert_mobi
from .pdf import convert_pdf


CONVERTERS = {
    ".epub": convert_epub,
    ".mobi": convert_mobi,
    ".pdf": convert_pdf,
}


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="book2md",
        description="Convert DRM-free EPUB, MOBI, and text-based PDF books to Markdown.",
    )
    parser.add_argument("input", type=Path, help="Path to an EPUB, MOBI, or PDF file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination directory. Defaults to INPUT-markdown.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.input.expanduser().resolve()
    if not source.is_file():
        print(f"book2md: input file not found: {sanitize(source)}", file=sys.stderr)
        return 2
    converter = CONVERTERS.get(source.suffix.lower())
    if not converter:
        supported = ", ".join(extension[1:].upper() for extension in CONVERTERS)
        print(f"book2md: unsupported format '{sanitize(source.suffix)}'. Supported: {supported}.", file=sys.stderr)
        return 2

    output = (args.output or source.with_suffix("")).expanduser()
    if args.output is None:
        output = Path(f"{output}-markdown")
    output = output.resolve()
    if output.exists():
        print(f"book2md: output path already exists: {output}", file=sys.stderr)
        return 2

    try:
        output.mkdir()
    except FileExistsError:
        print(f"book2md: output path already exists: {sanitize(output)}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"book2md: cannot create the output directory: {sanitize(error)}", file=sys.stderr)
        return 1

    try:
        converter(source, output)
    except BaseException as error:
        # Never leave a partial conversion behind; the directory was created above.
        shutil.rmtree(output, ignore_errors=True)
        if isinstance(error, ConversionError):
            message = str(error)
        elif isinstance(error, zipfile.BadZipFile):
            message = f"The EPUB archive is corrupt: {sanitize(error)}"
        elif isinstance(error, FileExistsError):
            message = f"The book contains conflicting file or directory names: {sanitize(error)}"
        elif isinstance(error, (OSError, ValueError)):
            message = f"The conversion failed: {sanitize(error)}"
        else:
            raise
        print(f"book2md: {message}", file=sys.stderr)
        return 1
    print(f"Converted {source.name} to {output}")
    return 0

