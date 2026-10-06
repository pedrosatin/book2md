import io
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

    def test_rejects_xml_entities(self):
        with self.archive([("metadata", b'<!DOCTYPE x [<!ENTITY a "payload">]><x>&a;</x>')]) as archive:
            with self.assertRaises(ConversionError):
                read_metadata(archive, "metadata")


class ConverterLimitsTests(unittest.TestCase):
    def test_successful_converter_keeps_output(self):
        result = run_converter([sys.executable, "-c", 'print("converted")'])
        self.assertEqual(result.stdout.strip(), "converted")
        self.assertEqual(result.returncode, 0)

    def test_converter_timeout_becomes_conversion_error(self):
        with patch("book2md.process.CONVERTER_TIMEOUT", 0.05), self.assertRaises(ConversionError):
            run_converter([sys.executable, "-c", "import time; time.sleep(30)"])


if __name__ == "__main__":
    unittest.main()
