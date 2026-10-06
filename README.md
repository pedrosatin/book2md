# book2md

Turn a DRM-free ebook into local Markdown files.

Criado por [@pedrosatin](https://github.com/pedrosatin)

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

## Contributing

Contributions and bug reports are welcome at https://github.com/pedrosatin/book2md/issues.

## License

MIT

## Conversion limits

EPUB archives are limited to 10,000 unique entries, 256 MiB of declared uncompressed data,
64 MiB per entry and a compression ratio of 200. Decompression streams enforce the entry
limit, and metadata rejects DTD/entity declarations and files larger than 2 MiB.
PDF and MOBI converters have a 120-second deadline. On POSIX, their process groups are
terminated on timeout; individual output files are limited to 64 MiB and address space
to 1 GiB. Captured output is written to temporary files. These limits do not replace
a filesystem quota for the total files produced by external converters.

PDF image extraction runs `pdfimages -list` first and refuses PDFs with more than 5,000
image occurrences or more than 4 GiB of estimated raw image data. `pdfimages` writes one
file per occurrence, so extraction is stopped if the `images/` directory grows past
256 MiB, and byte-identical images are kept only once.

## Markdown safety

Book content is treated as untrusted. In the Markdown output:

- Links keep only `http`, `https`, `mailto`, fragments and relative paths. A link with any
  other scheme (`javascript:`, `data:`, `file:`) or a protocol-relative URL is removed and
  its text is kept.
- Remote, `data:` and otherwise unresolved images are removed. Their alt text stays as
  plain text. Only images extracted from the EPUB into `images/` are embedded.
- Raw HTML from the book is not preserved. `<`, `>`, `[` and `]` in text are escaped, so
  text such as `[x](javascript:...)` stays text. Code blocks and inline code keep their
  content as written.

## Errors

If a conversion fails, `book2md` removes the output directory it created and prints one
message. Corrupt archives and conflicting entry names (for example `images/a` and
`images/a/b`) are reported this way, without a traceback. Control and escape characters
in error messages, such as file names taken from the book, are replaced with spaces.

Run offline tests with `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
