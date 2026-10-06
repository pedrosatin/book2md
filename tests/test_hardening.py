import contextlib
import io
import os
import random
import shutil
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

from book2md import cli
from book2md.epub import XHTMLToMarkdown, convert_epub
from book2md.errors import ConversionError, sanitize
from book2md.markdown import safe_url
from book2md.pdf import check_image_budget, convert_pdf
from book2md.process import run_converter

HEADER = ("page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio\n"
          "-" * 40 + "\n")


def listing(count, width=10, height=10):
    rows = "".join(
        f"{n:>4} {n:>4} image {width:>7} {height:>6} rgb 3 8 image no 7 0 72 72 100B 10%\n"
        for n in range(count)
    )
    return HEADER + rows


def make_pdf(path, pages, size=64):
    """Pure-Python PDF with selectable text and one RGB image repeated on every page."""
    rnd = random.Random(1)
    pixels = zlib.compress(bytes(rnd.randrange(256) for _ in range(size * size * 3)))
    objects = {}
    kids = " ".join(f"{10 + i} 0 R" for i in range(pages))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects[4] = (f"<< /Type /XObject /Subtype /Image /Width {size} /Height {size} /ColorSpace /DeviceRGB "
                  f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(pixels)} >>\nstream\n").encode() \
        + pixels + b"\nendstream"
    content = b"BT /F1 12 Tf 20 150 Td (Hello book) Tj ET q 50 0 0 50 20 20 cm /Im1 Do Q"
    objects[5] = f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
    for i in range(pages):
        objects[10 + i] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 5 0 R "
                           b"/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 4 0 R >> >> >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    start = len(out)
    top = max(objects) + 1
    out += f"xref\n0 {top}\n".encode() + b"0000000000 65535 f \n"
    for number in range(1, top):
        out += (f"{offsets[number]:010d} 00000 n \n" if number in offsets else "0000000000 65535 f \n").encode()
    out += f"trailer\n<< /Size {top} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    Path(path).write_bytes(bytes(out))


class ImageBudgetTests(unittest.TestCase):
    def test_counts_occurrences_under_limit(self):
        self.assertEqual(check_image_budget(listing(5)), 5)

    def test_rejects_too_many_images(self):
        with patch("book2md.pdf.MAX_IMAGES", 10), self.assertRaises(ConversionError) as raised:
            check_image_budget(listing(11))
        self.assertIn("more than 10", str(raised.exception))

    def test_rejects_large_estimated_expansion(self):
        with patch("book2md.pdf.MAX_ESTIMATED_IMAGE_BYTES", 1000), self.assertRaises(ConversionError):
            check_image_budget(listing(10, width=10, height=10))  # 300 bytes each

    def test_ignores_malformed_rows(self):
        self.assertEqual(check_image_budget(HEADER + "garbage\nx y z\n"), 0)


class DirectoryWatchTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX process groups")
    def test_kills_converter_that_writes_too_much(self):
        script = ("import sys, time\n"
                  "for i in range(1000):\n"
                  "    open(f'{sys.argv[1]}/f{i}', 'wb').write(b'x' * 20000)\n"
                  "    time.sleep(0.05)\n")
        with tempfile.TemporaryDirectory() as directory:
            with patch("book2md.process.POLL_INTERVAL", 0.05), self.assertRaises(ConversionError) as raised:
                run_converter([sys.executable, "-c", script, directory],
                              watch_dir=Path(directory), max_dir_bytes=100000)
            self.assertIn("stopped", str(raised.exception))
            self.assertLess(sum(p.stat().st_size for p in Path(directory).iterdir()), 1000000)

    def test_checks_directory_after_fast_converter_exits(self):
        script = "import sys; [open(f'{sys.argv[1]}/f{i}', 'wb').write(b'x' * 5000) for i in range(10)]"
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ConversionError):
            run_converter([sys.executable, "-c", script, directory],
                          watch_dir=Path(directory), max_dir_bytes=20000)

    def test_converter_under_cap_is_fine(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_converter([sys.executable, "-c", "print(1)"],
                                   watch_dir=Path(directory), max_dir_bytes=20000)
            self.assertEqual(result.returncode, 0)


@unittest.skipUnless(shutil.which("pdfimages") and shutil.which("pdftotext"), "Poppler not installed")
class PDFIntegrationTests(unittest.TestCase):
    def test_repeated_image_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "repeat.pdf"
            make_pdf(pdf, 40)
            output = Path(directory) / "out"
            convert_pdf(pdf, output)
            images = list((output / "images").iterdir())
            self.assertEqual(len(images), 1)
            readme = (output / "README.md").read_text()
            self.assertIn("Hello book", readme)
            self.assertEqual(readme.count("![]("), 1)

    def test_image_count_limit_blocks_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "repeat.pdf"
            make_pdf(pdf, 40)
            output = Path(directory) / "out"
            with patch("book2md.pdf.MAX_IMAGES", 10), self.assertRaises(ConversionError):
                convert_pdf(pdf, output)
            self.assertFalse((output / "images").exists())

    def test_output_size_limit_kills_pdfimages(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "repeat.pdf"
            make_pdf(pdf, 40)  # 40 PNG copies of about 12 KB
            output = Path(directory) / "out"
            with patch("book2md.pdf.MAX_IMAGE_DIR_BYTES", 50000), self.assertRaises(ConversionError):
                convert_pdf(pdf, output)


class MarkdownSafetyTests(unittest.TestCase):
    def convert(self, body, images=None):
        parser = XHTMLToMarkdown("a.xhtml", {"a.xhtml": "01-a.md", "b.xhtml": "02-b.md"}, images or {})
        parser.feed(f"<html><body>{body}</body></html>")
        return parser.markdown()

    def test_unsafe_link_schemes_keep_text_only(self):
        for href in ("javascript:alert(1)", "  JaVa\tScript:alert(1)", "data:text/html,x",
                     "vbscript:x", "file:///etc/passwd", "//evil.example/x"):
            with self.subTest(href=href):
                text = self.convert(f'<p><a href="{href}">click</a></p>')
                self.assertEqual(text.strip(), "click")

    def test_safe_links_survive(self):
        text = self.convert('<a href="https://x.example/a_(b)">w</a> <a href="mailto:a@b.c">m</a> '
                            '<a href="b.xhtml#s">n</a> <a href="#top">t</a>')
        self.assertIn("[w](https://x.example/a_%28b%29)", text)
        self.assertIn("[m](mailto:a@b.c)", text)
        self.assertIn("[n](02-b.md#s)", text)
        self.assertIn("[t](a.xhtml#top)".replace("a.xhtml", "01-a.md"), text)

    def test_remote_and_data_images_become_alt_text(self):
        text = self.convert('<img src="https://tracker.example/p.gif" alt="logo"/>'
                            '<img src="data:image/png;base64,AAAA" alt="inline"/><img src="x.png"/>')
        self.assertNotIn("tracker", text)
        self.assertNotIn("data:", text)
        self.assertNotIn("![", text)
        self.assertIn("logo", text)
        self.assertIn("inline", text)

    def test_local_image_is_kept(self):
        text = self.convert('<img src="p.png" alt="P"/>', {"p.png": "images/p.png"})
        self.assertIn("![P](images/p.png)", text)

    def test_html_in_text_and_entities_is_escaped(self):
        text = self.convert("<p>&lt;img src=x onerror=alert(1)&gt; and <script>bad()</script>"
                            "[x](javascript:alert(1)) &lt;javascript:alert(1)&gt;</p>")
        self.assertNotIn("<img", text)
        self.assertNotIn("<javascript", text)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", text)
        self.assertIn("\\[x\\]", text)
        self.assertNotIn("bad()", text)

    def test_code_blocks_keep_angle_brackets_and_cannot_break_out(self):
        text = self.convert("<pre>a &lt; b\n```\n&lt;x&gt;</pre><p><code>1 &lt; 2 `x`</code></p>")
        self.assertIn("a < b", text)
        self.assertIn("<x>", text)
        self.assertEqual(text.count("```"), 2)
        self.assertIn("`1 < 2 'x'`", text)

    def test_safe_url_helper(self):
        self.assertIsNone(safe_url("javascript:x"))
        self.assertEqual(safe_url("chapter.md"), "chapter.md")


def write_epub(path, extra=()):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml",
                         '<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>')
        archive.writestr("content.opf",
                         '<package xmlns="http://www.idpf.org/2007/opf"><metadata '
                         'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T &lt;b&gt;</dc:title></metadata>'
                         '<manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/></manifest>'
                         '<spine><itemref idref="one"/></spine></package>')
        archive.writestr("one.xhtml", "<html><body><h1>One</h1></body></html>")
        for name, data in extra:
            archive.writestr(name, data)


class CLIFailureTests(unittest.TestCase):
    def run_cli(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(list(argv))
        return code, err.getvalue()

    def test_file_conflict_in_images_is_a_clean_error_without_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            epub = Path(directory) / "b.epub"
            write_epub(epub, [("OEBPS/images/a", b"1"), ("OEBPS/images/a/b", b"2")])
            output = Path(directory) / "out"
            code, err = self.run_cli(str(epub), "-o", str(output))
            self.assertEqual(code, 1)
            self.assertIn("conflicting", err)
            self.assertNotIn("Traceback", err)
            self.assertFalse(output.exists())

    def test_bad_crc_is_a_clean_error_without_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            epub = Path(directory) / "b.epub"
            write_epub(epub, [("OEBPS/images/p.png", b"A" * 100)])
            raw = bytearray(epub.read_bytes())
            offset = raw.index(b"A" * 100)
            raw[offset] = ord("B")
            epub.write_bytes(bytes(raw))
            output = Path(directory) / "out"
            code, err = self.run_cli(str(epub), "-o", str(output))
            self.assertEqual(code, 1)
            self.assertIn("corrupt", err)
            self.assertFalse(output.exists())

    def test_existing_output_is_refused_and_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            epub = Path(directory) / "b.epub"
            write_epub(epub)
            output = Path(directory) / "out"
            output.mkdir()
            (output / "keep").write_text("x")
            code, err = self.run_cli(str(epub), "-o", str(output))
            self.assertEqual(code, 2)
            self.assertIn("already exists", err)
            self.assertTrue((output / "keep").exists())

    def test_conversion_error_removes_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            epub = Path(directory) / "b.epub"
            write_epub(epub, [("OEBPS/images/../../evil", b"x")])
            output = Path(directory) / "out"
            code, err = self.run_cli(str(epub), "-o", str(output))
            self.assertEqual(code, 1)
            self.assertFalse(output.exists())

    def test_successful_conversion_escapes_title(self):
        with tempfile.TemporaryDirectory() as directory:
            epub = Path(directory) / "b.epub"
            write_epub(epub)
            output = Path(directory) / "out"
            code, _ = self.run_cli(str(epub), "-o", str(output))
            self.assertEqual(code, 0)
            self.assertIn("# T &lt;b&gt;", (output / "README.md").read_text())

    def test_error_messages_strip_terminal_escapes(self):
        with tempfile.TemporaryDirectory() as directory:
            epub = Path(directory) / "b.epub"
            write_epub(epub, [("OEBPS/images/\x1b]0;pwned\x07evil/../../x", b"x")])
            output = Path(directory) / "out"
            code, err = self.run_cli(str(epub), "-o", str(output))
            self.assertEqual(code, 1)
            self.assertNotIn("\x1b", err)
            self.assertNotIn("\x07", err)

    def test_sanitize_and_conversion_error(self):
        self.assertEqual(sanitize("a\x1b[31mred\x07\nb\x9bc"), "a [31mred b c")
        self.assertNotIn("\x1b", str(ConversionError("x\x1b[2Jy")))
        self.assertLessEqual(len(sanitize("x" * 5000)), 503)


if __name__ == "__main__":
    unittest.main()
