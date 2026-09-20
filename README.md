# book2md

`book2md` turns DRM-free ebooks into local Markdown files. It handles EPUB directly, reads PDFs that contain selectable text, and converts MOBI through Calibre.

## Install

```bash
python -m pip install .
```

During development:

```bash
python -m pip install -e .
```

## Use

```bash
book2md book.epub
book2md book.pdf -o notes/book
book2md book.mobi
```

If you omit `-o`, `book2md` writes beside the source file. For example, `book.epub` becomes `book-markdown/`. It stops instead of overwriting an existing directory.

## Format support

| Format | What you need | What it writes |
| --- | --- | --- |
| EPUB | Python 3.10+ | One Markdown file per item in the book's reading order. Images and internal links stay local. |
| PDF | Poppler: `pdftotext` and `pdfimages` | A `README.md` containing the extracted text, plus any embedded images. |
| MOBI | Calibre: `ebook-convert` | Calibre converts the book to EPUB first. `book2md` then writes the EPUB output. |

PDFs need selectable text. Scanned PDFs need OCR, which this release does not do. The tool does not remove DRM.

## Development

```bash
python -m unittest discover -s tests -v
```
