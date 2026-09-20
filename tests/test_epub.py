import tempfile
import unittest
import zipfile
from pathlib import Path

from book2md.epub import convert_epub


class EPUBConversionTests(unittest.TestCase):
    def test_converts_spine_order_and_local_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            epub = root / "book.epub"
            with zipfile.ZipFile(epub, "w") as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    """<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>""",
                )
                archive.writestr(
                    "content.opf",
                    """<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test book</dc:title></metadata><manifest><item id="one" href="text/one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="text/two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>""",
                )
                archive.writestr(
                    "text/one.xhtml",
                    '<html><body><h1>One</h1><p><a href="two.xhtml">Next</a></p></body></html>',
                )
                archive.writestr(
                    "text/two.xhtml",
                    '<html><body><h1>Two</h1><p>Done.</p></body></html>',
                )
            output = root / "output"
            convert_epub(epub, output)
            self.assertIn("[Next](02-two.md)", (output / "01-one.md").read_text())
            self.assertIn("# Test book", (output / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()

