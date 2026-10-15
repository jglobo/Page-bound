from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
import html
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import img2pdf
import pikepdf

from .images import UnreadablePage, jpeg_bytes
from .model import Project

LOG = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


def safe_stem(title: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .") or "ebook"


def _prepare(project, folder, progress, cancelled):
    paths = []
    warnings = []
    for number, page in enumerate(project.pages, 1):
        if cancelled and cancelled():
            raise Cancelled()
        try:
            content, dimensions = jpeg_bytes(page, project.quality)
            path = folder / f"{number:06}.jpg"
            path.write_bytes(content)
            paths.append((path, dimensions))
        except UnreadablePage:
            LOG.exception("Unreadable page %s", page.path)
            warnings.append(f"Page {number} ({Path(page.path).name}) could not be read and was skipped.")
        if progress:
            progress("Preparing pages", number, len(project.pages))
    if not paths:
        raise ValueError("No readable pages were found.")
    return paths, warnings


def build_pdf(prepared, metadata, destination, progress=None, cancelled=None):
    if cancelled and cancelled():
        raise Cancelled()
    staged = destination.with_suffix(".pdf.partial")
    try:
        with staged.open("wb") as output:
            img2pdf.convert([str(p) for p, _ in prepared], outputstream=output)
        if cancelled and cancelled():
            raise Cancelled()
        with pikepdf.open(staged, allow_overwriting_input=True) as pdf:
            with pdf.open_metadata(set_pikepdf_as_editor=False) as info:
                info["dc:title"] = metadata.title
                info["dc:creator"] = [metadata.author]
                info["dc:language"] = [metadata.language]
                if metadata.description:
                    info["dc:description"] = metadata.description
            pdf.docinfo["/Title"] = metadata.title
            pdf.docinfo["/Author"] = metadata.author
            if metadata.publisher:
                pdf.docinfo["/Producer"] = metadata.publisher
            pdf.save(staged.with_suffix(".ready"))
        staged.with_suffix(".ready").replace(destination)
        if progress:
            progress("PDF complete", 1, 1)
    finally:
        staged.unlink(missing_ok=True)
        staged.with_suffix(".ready").unlink(missing_ok=True)


def build_epub(prepared, metadata, destination, cover_file=None, progress=None, cancelled=None):
    staged = destination.with_suffix(".epub.partial")
    uid = str(uuid.uuid4())
    esc = html.escape
    try:
        with ZipFile(staged, "w") as book:
            book.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
            book.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            manifest, spine, toc = [], [], []
            for i, (path, (width, height)) in enumerate(prepared, 1):
                if cancelled and cancelled():
                    raise Cancelled()
                image_name = f"images/page{i:06}.jpg"
                page_name = f"pages/page{i:06}.xhtml"
                book.write(path, f"OEBPS/{image_name}", compress_type=ZIP_STORED)
                xhtml = f'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Page {i}</title><meta name="viewport" content="width={width},height={height}"/><style>html,body{{margin:0;width:100%;height:100%;}} img{{display:block;width:100%;height:100%;object-fit:contain;}}</style></head><body><img src="../{image_name}" alt="Scanned page {i}"/></body></html>'''
                book.writestr(f"OEBPS/{page_name}", xhtml)
                manifest.extend([f'<item id="img{i}" href="{image_name}" media-type="image/jpeg"/>', f'<item id="page{i}" href="{page_name}" media-type="application/xhtml+xml"/>'])
                spine.append(f'<itemref idref="page{i}"/>')
                toc.append(f'<li><a href="{page_name}">Page {i}</a></li>')
                if progress:
                    progress("Building EPUB", i, len(prepared))
            cover_meta = ""
            if cover_file:
                book.write(cover_file, "OEBPS/images/cover.jpg", compress_type=ZIP_STORED)
                manifest.append('<item id="cover" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>')
            else:
                cover_meta = '<meta name="cover" content="img1"/>'
            book.writestr("OEBPS/nav.xhtml", f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol>{"".join(toc)}</ol></nav></body></html>')
            manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
            fields = [f'<dc:title>{esc(metadata.title)}</dc:title>', f'<dc:creator>{esc(metadata.author)}</dc:creator>', f'<dc:language>{esc(metadata.language)}</dc:language>', f'<dc:identifier id="uid">urn:uuid:{uid}</dc:identifier>']
            for tag, value in (("publisher", metadata.publisher), ("description", metadata.description), ("date", metadata.publication_date)):
                if value:
                    fields.append(f'<dc:{tag}>{esc(value)}</dc:{tag}>')
            if metadata.isbn:
                fields.append(f'<dc:identifier>urn:isbn:{esc(metadata.isbn)}</dc:identifier>')
            modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            book.writestr("OEBPS/package.opf", f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" prefix="rendition: http://www.idpf.org/vocab/rendition/#"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">{"".join(fields)}<meta property="dcterms:modified">{modified}</meta><meta property="rendition:layout">pre-paginated</meta><meta property="rendition:spread">none</meta>{cover_meta}</metadata><manifest>{"".join(manifest)}</manifest><spine>{"".join(spine)}</spine></package>''')
        if cancelled and cancelled():
            raise Cancelled()
        staged.replace(destination)
    finally:
        staged.unlink(missing_ok=True)


def export_project(project: Project, output: Path, progress=None, cancelled=None):
    output.mkdir(parents=True, exist_ok=True)
    result, warnings = [], []
    with TemporaryDirectory(prefix="ebook-builder-") as tmp:
        temp = Path(tmp)
        prepared, warnings = _prepare(project, temp, progress, cancelled)
        cover = None
        if project.metadata.cover_path and Path(project.metadata.cover_path).is_file():
            cover_bytes, _ = jpeg_bytes(type(project.pages[0])(project.metadata.cover_path), project.quality)
            cover = temp / "cover.jpg"
            cover.write_bytes(cover_bytes)
        elif project.metadata.use_first_page_cover:
            cover = prepared[0][0]
        stem = safe_stem(project.output_name or project.metadata.title)
        base = stem
        serial = 2
        while any((output / f"{stem}.{ext}").exists() for ext in ("pdf", "epub")):
            stem = f"{base} ({serial})"
            serial += 1
        if project.pdf:
            target = output / f"{stem}.pdf"
            build_pdf(prepared, project.metadata, target, progress, cancelled)
            result.append(target)
        if project.epub:
            target = output / f"{stem}.epub"
            build_epub(prepared, project.metadata, target, cover, progress, cancelled)
            result.append(target)
    return result, warnings
