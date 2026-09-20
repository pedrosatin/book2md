import argparse
import sys
from pathlib import Path

from .epub import convert_epub
from .errors import ConversionError
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
        print(f"book2md: input file not found: {source}", file=sys.stderr)
        return 2
    converter = CONVERTERS.get(source.suffix.lower())
    if not converter:
        supported = ", ".join(extension[1:].upper() for extension in CONVERTERS)
        print(f"book2md: unsupported format '{source.suffix}'. Supported: {supported}.", file=sys.stderr)
        return 2

    output = (args.output or source.with_suffix("")).expanduser()
    if args.output is None:
        output = Path(f"{output}-markdown")
    output = output.resolve()
    if output.exists():
        print(f"book2md: output path already exists: {output}", file=sys.stderr)
        return 2

    try:
        converter(source, output)
    except ConversionError as error:
        print(f"book2md: {error}", file=sys.stderr)
        return 1
    print(f"Converted {source.name} to {output}")
    return 0

