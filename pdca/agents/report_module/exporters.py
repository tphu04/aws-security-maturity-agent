# exporters.py — Rebuilt (Sprint 3)
# - write_file: unchanged
# - render_html: kept for backward compat (markdown → HTML)
# - export_pdf: weasyprint first, wkhtmltopdf fallback, temp cleanup

import os
import tempfile

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
    3. None (skip PDF)
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
    return _export_pdf_wkhtmltopdf(html, path)


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
