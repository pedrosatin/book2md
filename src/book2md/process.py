import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from .errors import ConversionError

CONVERTER_TIMEOUT = 120
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


class _DirectoryLimit(Exception):
    pass


def _limits() -> None:
    import resource
    for kind, cap in ((resource.RLIMIT_FSIZE, MAX_OUTPUT_BYTES),
                      (resource.RLIMIT_AS, 1024 * 1024 * 1024)):
        inherited = resource.getrlimit(kind)
        limit = min([cap, *(value for value in inherited if value != resource.RLIM_INFINITY)])
        resource.setrlimit(kind, (limit, limit))


POLL_INTERVAL = 0.2


def directory_bytes(directory: Path) -> int:
    total = 0
    for entry in os.scandir(directory):
        try:
            total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            pass
    return total


def run_converter(command: list[str], watch_dir: Path | None = None,
                  max_dir_bytes: int | None = None) -> subprocess.CompletedProcess:
    """Bound converter time, captured output and individual files on POSIX.

    With watch_dir and max_dir_bytes, the converter is killed once the files in
    that directory exceed the cap, bounding the total it can write.
    """
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                       start_new_session=os.name == "posix",
                                       preexec_fn=_limits if os.name == "posix" else None)
        except (OSError, subprocess.SubprocessError):
            raise ConversionError("The converter could not start with the configured resource limits.") from None
        try:
            deadline = time.monotonic() + CONVERTER_TIMEOUT
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, CONVERTER_TIMEOUT)
                try:
                    process.wait(timeout=min(POLL_INTERVAL, remaining))
                    break
                except subprocess.TimeoutExpired:
                    if watch_dir is not None and directory_bytes(watch_dir) > max_dir_bytes:
                        raise _DirectoryLimit from None
            if watch_dir is not None and directory_bytes(watch_dir) > max_dir_bytes:
                raise _DirectoryLimit
        except BaseException as error:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
            if isinstance(error, _DirectoryLimit):
                raise ConversionError(
                    f"The converter wrote more than {max_dir_bytes // (1024 * 1024)} MiB of files; stopped."
                ) from None
            if isinstance(error, subprocess.TimeoutExpired):
                raise ConversionError("The converter exceeded the 120-second time limit.") from error
            raise
        for stream in (stdout, stderr):
            if stream.tell() >= MAX_OUTPUT_BYTES:
                raise ConversionError("The converter exceeded the output size limit.")
            stream.seek(0)
        return subprocess.CompletedProcess(command, process.returncode,
                                           stdout.read(MAX_OUTPUT_BYTES).decode("utf-8", "replace"),
                                           stderr.read(MAX_OUTPUT_BYTES).decode("utf-8", "replace"))
