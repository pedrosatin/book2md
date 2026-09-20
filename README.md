# book2md

Turn a DRM-free ebook into local Markdown files.

```bash
book2md ~/books/book.epub -o ~/notes/book
```

```text
Converted book.epub to /home/you/notes/book
```

EPUB output keeps the book's reading order, local images, and internal links:

```text
book/
├── README.md
├── 01-frontmatter.md
├── 02-chapter-one.md
├── 03-chapter-two.md
└── images/
```

## Dependencies

| Format | Required | Notes |
| --- | --- | --- |
| EPUB | Python 3.10+ | No extra reader required. |
| PDF | Poppler: `pdftotext` and `pdfimages` | The PDF needs selectable text. |
| MOBI | Calibre: `ebook-convert` | `book2md` converts the MOBI to EPUB first. |

`book2md` does not remove DRM. It does not run OCR on scanned PDFs.

## Setup

Clone the repository and install the command:

```bash
git clone https://github.com/pedrosatin/book2md.git ~/Work/book2md
python -m pip install ~/Work/book2md
```

Install the format readers you need:

```bash
sudo pacman -S poppler          # PDF support on Arch
sudo pacman -S calibre          # MOBI support on Arch
```

On Debian or Ubuntu:

```bash
sudo apt install poppler-utils  # PDF support
sudo apt install calibre        # MOBI support
```

Check the installation:

```bash
command -v book2md
book2md --help
```

## Usage

```text
book2md INPUT [-o OUTPUT]
```

```bash
book2md book.epub
book2md book.pdf -o notes/book
book2md book.mobi
```

Without `-o`, `book2md` creates `book-markdown/` beside the source file. It refuses to overwrite an existing output directory.

## Output by format

**EPUB.** Creates one Markdown file for each item in the EPUB reading order, plus a `README.md` index and an `images/` directory.

**PDF.** Creates a `README.md` with extracted text and embedded images. Scanned PDFs fail with a clear message because they need OCR.

**MOBI.** Uses Calibre to create an EPUB, then uses the EPUB converter. The result has the same structure as EPUB output.

## Known limitations

The EPUB converter handles prose, headings, lists, code blocks, links, and images. Complex tables and publisher-specific XHTML may need cleanup after conversion.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
