import os
import signal
import subprocess
import tempfile

from .errors import ConversionError

CONVERTER_TIMEOUT = 120
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


def _limits() -> None:
    import resource
    for kind, cap in ((resource.RLIMIT_FSIZE, MAX_OUTPUT_BYTES),
                      (resource.RLIMIT_AS, 1024 * 1024 * 1024)):
        inherited = resource.getrlimit(kind)
        limit = min([cap, *(value for value in inherited if value != resource.RLIM_INFINITY)])
        resource.setrlimit(kind, (limit, limit))


def run_converter(command: list[str]) -> subprocess.CompletedProcess:
    """Bound converter time, captured output and individual files on POSIX."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                       start_new_session=os.name == "posix",
                                       preexec_fn=_limits if os.name == "posix" else None)
        except (OSError, subprocess.SubprocessError):
            raise ConversionError("The converter could not start with the configured resource limits.") from None
        try:
            process.wait(timeout=CONVERTER_TIMEOUT)
        except BaseException as error:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
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
