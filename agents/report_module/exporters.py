# exporters.py — Rebuilt (Sprint 3)
# - write_file: unchanged
# - render_html: kept for backward compat (markdown → HTML)
# - export_pdf: weasyprint first, wkhtmltopdf fallback, temp cleanup

import os
import tempfile


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
        print(f"[exporters] PDF exported (weasyprint): {path}")
        return path
    except ImportError:
        pass
    except Exception as e:
        print(f"[exporters] weasyprint failed: {e}")

    # Fallback: wkhtmltopdf
    return _export_pdf_wkhtmltopdf(html, path)


def _export_pdf_wkhtmltopdf(html: str, path: str) -> str | None:
    """wkhtmltopdf fallback with proper temp file cleanup."""
    try:
        import pdfkit
    except ImportError:
        print("[exporters] No PDF library installed — PDF skipped.")
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
            print("[exporters] wkhtmltopdf not found — PDF skipped.")
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
        print(f"[exporters] PDF exported (wkhtmltopdf): {path}")
        return path
    except Exception as e:
        print(f"[exporters] PDF export error: {e}")
        return None
    finally:
        # Always cleanup temp file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
