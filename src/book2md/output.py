from pathlib import Path

from .errors import ConversionError


def prepare_output(output: Path) -> None:
    """Create the output directory, or accept one only if it is empty.

    Converters never write into a directory that already holds files, so a
    library caller cannot overwrite existing data by passing a used path. The
    CLI creates the directory itself and passes it in empty.
    """
    try:
        output.mkdir()
    except FileExistsError:
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise ConversionError(f"The output path already exists and is not empty: {output}") from None
