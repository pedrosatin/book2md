import io
import os
import subprocess
import sys
import unittest
import zipfile
from unittest.mock import patch

from book2md.epub import read_entry, read_metadata, validate_archive
from book2md.errors import ConversionError
from book2md.process import run_converter


class ArchiveLimitsTests(unittest.TestCase):
    def archive(self, entries, compression=zipfile.ZIP_STORED):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
            for name, value in entries:
                archive.writestr(name, value)
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    def test_rejects_high_compression_ratio(self):
        with self.archive([("bomb", b"0" * 100000)], zipfile.ZIP_DEFLATED) as archive:
            with self.assertRaises(ConversionError):
                validate_archive(archive)

    def test_checks_total_and_individual_size(self):
        with self.archive([("a", b"x" * 40), ("b", b"x" * 40)]) as archive:
            with patch("book2md.epub.MAX_ARCHIVE_BYTES", 60), self.assertRaises(ConversionError):
                validate_archive(archive)
            with patch("book2md.epub.MAX_ENTRY_BYTES", 30), self.assertRaises(ConversionError):
                validate_archive(archive)

    def test_stream_limit_is_enforced_even_without_preflight(self):
        with self.archive([("text", b"x" * 200)]) as archive:
            with patch("book2md.epub.MAX_ENTRY_BYTES", 100), self.assertRaises(ConversionError):
                read_entry(archive, "text")

    def test_rejects_utf16_xml_entities(self):
        value = '<!DOCTYPE x [<!ENTITY a "payload">]><x>&a;</x>'.encode("utf-16")
        with self.archive([("metadata", value)]) as archive:
            with self.assertRaises(ConversionError):
                read_metadata(archive, "metadata")

    def test_rejects_xml_entities(self):
        with self.archive([("metadata", b'<!DOCTYPE x [<!ENTITY a "payload">]><x>&a;</x>')]) as archive:
            with self.assertRaises(ConversionError):
                read_metadata(archive, "metadata")


class ConverterLimitsTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX resource limits")
    def test_preserves_lower_inherited_limits_in_isolated_process(self):
        code = '''
import json, resource, sys, tempfile
from pathlib import Path
from book2md.process import run_converter
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 8192))
probe = run_converter([sys.executable, "-c", "import json, resource; print(json.dumps([resource.getrlimit(resource.RLIMIT_AS), resource.getrlimit(resource.RLIMIT_FSIZE)]))"])
assert probe.returncode == 0, probe.stderr
assert json.loads(probe.stdout) == [[268435456, 268435456], [4096, 4096]], probe.stdout
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "output"
    result = run_converter([sys.executable, "-c", "import sys; f = open(sys.argv[1], 'wb'); f.write(b'x' * 8192); f.close()", str(path)])
    assert result.returncode != 0
    assert path.stat().st_size <= 4096
print("inherited limits enforced")
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("inherited limits enforced", result.stdout)

    @unittest.skipUnless(os.name == "posix", "POSIX resource limits")
    def test_unlimited_inherited_limits_receive_configured_caps(self):
        import resource
        with patch("resource.getrlimit", return_value=(resource.RLIM_INFINITY, resource.RLIM_INFINITY)), \
                patch("resource.setrlimit") as set_limit:
            from book2md.process import _limits
            _limits()
        self.assertEqual(set_limit.call_args_list[0].args[1], (67108864, 67108864))
        self.assertEqual(set_limit.call_args_list[1].args[1], (1073741824, 1073741824))

    def test_start_failure_is_contextual_and_does_not_expose_command(self):
        for error in (OSError("private path"), subprocess.SubprocessError("private command")):
            with self.subTest(error=type(error).__name__), \
                    patch("book2md.process.subprocess.Popen", side_effect=error), \
                    self.assertRaises(ConversionError) as raised:
                run_converter(["private-converter", "private-input"])
            self.assertIn("could not start", str(raised.exception))
            self.assertNotIn("private", str(raised.exception))
            self.assertTrue(raised.exception.__suppress_context__)

    def test_successful_converter_keeps_output(self):
        result = run_converter([sys.executable, "-c", 'print("converted")'])
        self.assertEqual(result.stdout.strip(), "converted")
        self.assertEqual(result.returncode, 0)

    def test_converter_timeout_becomes_conversion_error(self):
        with patch("book2md.process.CONVERTER_TIMEOUT", 0.05), self.assertRaises(ConversionError):
            run_converter([sys.executable, "-c", "import time; time.sleep(30)"])


if __name__ == "__main__":
    unittest.main()
