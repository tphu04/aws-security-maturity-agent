# exporters.py — Rebuilt (Sprint 3)
# - write_file: unchanged
# - render_html: kept for backward compat (markdown → HTML)
# - export_pdf: weasyprint first, wkhtmltopdf fallback, temp cleanup

import os
import tempfile
import textwrap

from pdca.observability.logger import get_logger

logger = get_logger(__name__)


def write_file(path: str, content: str) -> str:
    """Write content to file, creating directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def render_html(markdown_text: str) -> str:
    """Markdown → HTML conversion. Kept for backward compat."""
    import markdown2
    return markdown2.markdown(
        markdown_text,
        extras=[
            "tables",
            "fenced-code-blocks",
            "break-on-newline",
            "strike",
            "cuddled-lists",
        ],
    )


def html_to_markdown(html: str) -> str:
    """Lightweight HTML → Markdown for report rendering.

    Walks the rendered report DOM and emits Markdown that retains structural
    cues — `# /## /###` headings, lists, tables, code, blockquotes — so the
    state-adapter section splitter can carve sections and a user downloading
    `final_report.md` gets a real Markdown document (not raw HTML).

    Intentionally minimal: handles only the tags the report templates emit.
    Inline styles, classes, and custom attributes are dropped.
    """
    from bs4 import BeautifulSoup, NavigableString, Tag

    soup = BeautifulSoup(html, "html.parser")
    # Strip non-content nodes that would otherwise leak markup into the .md.
    for tag in soup(["style", "script", "head", "meta", "link"]):
        tag.decompose()
    root = soup.body or soup

    def _txt(node) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ""
        name = (node.name or "").lower()
        inner = "".join(_txt(c) for c in node.children)
        if name in ("strong", "b"):
            s = inner.strip()
            return f"**{s}**" if s else ""
        if name in ("em", "i"):
            s = inner.strip()
            return f"_{s}_" if s else ""
        if name == "code":
            return f"`{inner}`"
        if name == "br":
            return "\n"
        if name == "a":
            href = node.get("href") or ""
            label = inner.strip() or href
            return f"[{label}]({href})" if href else label
        if name == "img":
            src = node.get("src") or ""
            alt = node.get("alt") or ""
            return f"![{alt}]({src})"
        return inner

    def _table(tbl: Tag) -> str:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [_txt(td).strip().replace("\n", " ") for td in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        # If first row contains <th>, treat as header; else fabricate one.
        first_tr = tbl.find("tr")
        has_header = bool(first_tr and first_tr.find("th"))
        header = rows[0] if has_header else [f"col{i+1}" for i in range(len(rows[0]))]
        body = rows[1:] if has_header else rows
        cols = len(header)
        body = [(r + [""] * cols)[:cols] for r in body]
        out = "| " + " | ".join(header) + " |\n"
        out += "|" + "|".join(["---"] * cols) + "|\n"
        for r in body:
            out += "| " + " | ".join(r) + " |\n"
        return out

    blocks: list[str] = []

    def _walk(node):
        if isinstance(node, NavigableString):
            txt = str(node).strip()
            if txt:
                blocks.append(txt)
            return
        if not isinstance(node, Tag):
            return
        name = (node.name or "").lower()
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            blocks.append(f"{'#' * level} {_txt(node).strip()}")
            return
        if name == "p":
            text = _txt(node).strip()
            if text:
                blocks.append(text)
            return
        if name in ("ul", "ol"):
            ordered = name == "ol"
            lines = []
            for i, li in enumerate(node.find_all("li", recursive=False), 1):
                prefix = f"{i}." if ordered else "-"
                lines.append(f"{prefix} {_txt(li).strip()}")
            if lines:
                blocks.append("\n".join(lines))
            return
        if name == "blockquote":
            text = _txt(node).strip()
            if text:
                blocks.append("\n".join(f"> {ln}" for ln in text.splitlines()))
            return
        if name == "pre":
            code = _txt(node).rstrip()
            if code:
                blocks.append(f"```\n{code}\n```")
            return
        if name == "table":
            md = _table(node).strip()
            if md:
                blocks.append(md)
            return
        if name == "hr":
            blocks.append("---")
            return
        # Container — recurse.
        for child in node.children:
            _walk(child)

    _walk(root)

    text = "\n\n".join(b for b in blocks if b)
    # Collapse 3+ blank lines and trim.
    import re as _re
    text = _re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text


def export_pdf(html: str, path: str) -> str | None:
    """
    HTML → PDF. Fallback chain:
    1. weasyprint (pure Python, preferred)
    2. wkhtmltopdf (fallback)
    3. matplotlib text PDF fallback
    """
    # Try weasyprint first
    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(path)
        logger.info("PDF exported", extra={"backend": "weasyprint", "path": path})
        return path
    except ImportError:
        pass
    except Exception as e:
        logger.warning("weasyprint export failed", extra={"error": str(e)})

    # Fallback: wkhtmltopdf
    pdf_path = _export_pdf_wkhtmltopdf(html, path)
    if pdf_path:
        return pdf_path

    return _export_pdf_text_fallback(html, path)


def _export_pdf_wkhtmltopdf(html: str, path: str) -> str | None:
    """wkhtmltopdf fallback with proper temp file cleanup."""
    try:
        import pdfkit
    except ImportError:
        logger.info("No PDF library installed — PDF skipped")
        return None

    # Write to temp file (auto-cleanup via finally)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.html', delete=False, encoding='utf-8'
        ) as f:
            f.write(html)
            tmp_path = f.name

        # Find wkhtmltopdf binary
        possible = [
            r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
            r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
            "/usr/local/bin/wkhtmltopdf",
            "/usr/bin/wkhtmltopdf",
        ]
        wk = next((p for p in possible if os.path.exists(p)), None)
        if not wk:
            logger.info("wkhtmltopdf not found — PDF skipped")
            return None

        config = pdfkit.configuration(wkhtmltopdf=wk)
        pdfkit.from_file(
            tmp_path, path,
            configuration=config,
            options={
                "enable-local-file-access": None,
                "load-error-handling": "ignore",
            },
        )
        logger.info("PDF exported", extra={"backend": "wkhtmltopdf", "path": path})
        return path
    except Exception as e:
        logger.warning("PDF export error", extra={"error": str(e)})
        return None
    finally:
        # Always cleanup temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _export_pdf_text_fallback(html: str, path: str) -> str | None:
    """Last-resort PDF export using only the Python stdlib.

    This keeps the web app's PDF preview/download path available even on
    machines without WeasyPrint or the wkhtmltopdf binary. It is intentionally
    plain-text, while the primary exporters preserve the designed HTML layout.
    """
    try:
        import html as _html
        import re as _re
        text = _re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", html)
        text = _re.sub(r"(?i)</\s*(p|div|section|article|h[1-6]|li|tr)\s*>", "\n", text)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _html.unescape(text)
        text = _re.sub(r"[ \t]{2,}", " ", text)
        lines: list[str] = []
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                lines.append("")
                continue
            lines.extend(textwrap.wrap(raw, width=96) or [""])

        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_plain_pdf(lines or ["Report generated with no text content."], path)
        logger.info("PDF exported", extra={"backend": "plain_text", "path": path})
        return path
    except Exception as e:
        logger.warning("text PDF fallback failed", extra={"error": str(e)})
        return None


def _pdf_text_literal(value: str) -> bytes:
    safe = (
        value.encode("latin-1", "replace")
        .replace(b"\\", b"\\\\")
        .replace(b"(", b"\\(")
        .replace(b")", b"\\)")
    )
    return b"(" + safe + b")"


def _write_plain_pdf(lines: list[str], path: str) -> None:
    """Write a minimal multi-page PDF with standard Helvetica text."""
    page_chunks = [lines[i:i + 48] for i in range(0, len(lines), 48)] or [[""]]
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    catalog_id = add(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add(b"")  # filled after page objects are known
    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []

    for chunk in page_chunks:
        commands = [b"BT /F1 9 Tf 50 790 Td 12 TL"]
        for line in chunk:
            commands.append(_pdf_text_literal(line) + b" Tj T*")
        commands.append(b"ET")
        stream = b"\n".join(commands)
        content_id = add(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\n"
            b"stream\n" + stream + b"\nendstream"
        )
        page_id = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 " + str(font_id).encode("ascii") + b" 0 R >> >> "
            b"/Contents " + str(content_id).encode("ascii") + b" 0 R >>"
        )
        page_ids.append(page_id)

    kids = b" ".join(str(i).encode("ascii") + b" 0 R" for i in page_ids)
    objects[pages_id - 1] = (
        b"<< /Type /Pages /Kids [" + kids + b"] /Count "
        + str(len(page_ids)).encode("ascii") + b" >>"
    )

    del catalog_id  # documents object numbering; object 1 is the catalog
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{idx} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_at = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        b"trailer\n<< /Size " + str(len(objects) + 1).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_at).encode("ascii") + b"\n%%EOF\n"
    )
    with open(path, "wb") as f:
        f.write(output)
