import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from .errors import ConversionError


class XHTMLToMarkdown(HTMLParser):
    block_tags = {"p", "div", "section", "article", "figure", "figcaption", "dl", "dt", "dd"}
    skip_tags = {"head", "style", "script", "title", "svg"}

    def __init__(self, source_path: str, file_map: dict[str, str], image_map: dict[str, str]):
        super().__init__(convert_charrefs=True)
        self.source_path = source_path
        self.file_map = file_map
        self.image_map = image_map
        self.output: list[str] = []
        self.skip_depth = 0
        self.pre_depth = 0
        self.list_depth = 0
        self.pending_link = ""

    def write(self, text: str) -> None:
        self.output.append(text)

    def blank(self) -> None:
        if not self.output or not self.output[-1].endswith("\n\n"):
            self.write("\n\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.blank()
            self.write("#" * int(tag[1]) + " ")
        elif tag in self.block_tags:
            self.blank()
        elif tag == "br":
            self.write("\n")
        elif tag in {"strong", "b"}:
            self.write("**")
        elif tag in {"em", "i"}:
            self.write("*")
        elif tag == "code" and not self.pre_depth:
            self.write("`")
        elif tag == "pre":
            self.blank()
            self.write("```\n")
            self.pre_depth += 1
        elif tag in {"ul", "ol"}:
            self.blank()
            self.list_depth += 1
        elif tag == "li":
            self.blank()
            self.write("  " * max(0, self.list_depth - 1) + "- ")
        elif tag == "blockquote":
            self.blank()
            self.write("> ")
        elif tag == "a":
            href = attributes.get("href")
            if href:
                self.write("[")
                self.pending_link = f"]({self.rewrite_link(href)})"
        elif tag == "img":
            source = attributes.get("src")
            if source:
                target = posixpath.normpath(
                    posixpath.join(posixpath.dirname(self.source_path), source)
                )
                alt = attributes.get("alt", "") or ""
                self.write(f"![{alt}]({self.image_map.get(target, source)})")
        elif tag == "hr":
            self.blank()
            self.write("---\n\n")

    def rewrite_link(self, href: str) -> str:
        if href.startswith(("http://", "https://", "mailto:")):
            return href
        target, separator, fragment = href.partition("#")
        resolved = (
            self.source_path
            if not target
            else posixpath.normpath(posixpath.join(posixpath.dirname(self.source_path), target))
        )
        rewritten = self.file_map.get(resolved, target)
        return f"{rewritten}{separator}{fragment}" if separator else rewritten

    def handle_endtag(self, tag: str) -> None:
        if tag in self.skip_tags:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} | self.block_tags | {"li", "blockquote"}:
            self.blank()
        elif tag in {"strong", "b"}:
            self.write("**")
        elif tag in {"em", "i"}:
            self.write("*")
        elif tag == "code" and not self.pre_depth:
            self.write("`")
        elif tag == "pre":
            self.write("\n```\n\n")
            self.pre_depth = max(0, self.pre_depth - 1)
        elif tag in {"ul", "ol"}:
            self.list_depth = max(0, self.list_depth - 1)
            self.blank()
        elif tag == "a":
            self.write(self.pending_link)
            self.pending_link = ""

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        self.write(data if self.pre_depth else re.sub(r"\s+", " ", data))

    def markdown(self) -> str:
        text = "".join(self.output)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def convert_epub(source: Path, output: Path) -> None:
    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as error:
        raise ConversionError(f"{source} is not a valid EPUB archive.") from error

    with archive:
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next(
                element.attrib["full-path"]
                for element in container.iter()
                if element.tag.endswith("rootfile")
            )
            package = ET.fromstring(archive.read(rootfile))
        except (KeyError, ET.ParseError, StopIteration) as error:
            raise ConversionError("The EPUB package metadata is missing or malformed.") from error

        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
        }
        title = package.findtext("opf:metadata/dc:title", namespaces=ns) or source.stem
        creator = package.findtext("opf:metadata/dc:creator", namespaces=ns)
        manifest = {
            item.attrib["id"]: item.attrib
            for item in package.findall("opf:manifest/opf:item", ns)
        }
        opf_dir = posixpath.dirname(rootfile)
        documents = []
        for itemref in package.findall("opf:spine/opf:itemref", ns):
            item = manifest.get(itemref.attrib["idref"])
            if item and item.get("media-type") in {"application/xhtml+xml", "text/html"}:
                documents.append(posixpath.normpath(posixpath.join(opf_dir, item["href"])))
        if not documents:
            raise ConversionError("The EPUB reading order does not contain XHTML documents.")

        file_map = {
            document: f"{index:02d}-{re.sub(r'[^A-Za-z0-9._-]+', '-', Path(document).stem).strip('-')}.md"
            for index, document in enumerate(documents, 1)
        }
        output.mkdir()
        image_map = {}
        for name in archive.namelist():
            if name.startswith("OEBPS/images/") and not name.endswith("/"):
                relative = Path(name).relative_to("OEBPS/images")
                destination = output / "images" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
                image_map[name] = destination.relative_to(output).as_posix()

        sections = []
        for document in documents:
            parser = XHTMLToMarkdown(document, file_map, image_map)
            parser.feed(archive.read(document).decode("utf-8", errors="replace"))
            content = parser.markdown()
            destination = output / file_map[document]
            destination.write_text(content, encoding="utf-8")
            heading = next(
                (line[2:].strip() for line in content.splitlines() if line.startswith("# ")),
                destination.stem,
            )
            sections.append((heading, destination.name))

    readme = [f"# {title}"]
    if creator:
        readme.extend(["", f"Author: {creator}"])
    readme.extend(["", "## Sections", ""])
    readme.extend(f"- [{heading}]({filename})" for heading, filename in sections)
    (output / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

