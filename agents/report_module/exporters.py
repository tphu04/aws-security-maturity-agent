# ------------------------------------------------------------
# exporters.py — FIXED VERSION
# ------------------------------------------------------------

import os
import pdfkit
import markdown2


# ------------------------------------------------------------
# WRITE FILE
# ------------------------------------------------------------
def write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ------------------------------------------------------------
# MARKDOWN → HTML (Markdown2)
# ------------------------------------------------------------
def render_html(markdown_text: str):
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


# ------------------------------------------------------------
# HTML → PDF (wkhtmltopdf)
# ------------------------------------------------------------
def export_pdf(html: str, path: str):
    """
    FIX:
    - Remove unsupported fonts
    - Ensure local file access enabled
    - Ensure wkhtmltopdf found
    """

    html_wrapper = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 25px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }}
            th, td {{
                border: 1px solid #ccc;
                padding: 6px 8px;
                font-size: 13px;
            }}
            th {{
                background: #eee;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        {html}
    </body>
    </html>
    """

    tmp_html_path = "data/temp_report.html"
    with open(tmp_html_path, "w", encoding="utf-8") as f:
        f.write(html_wrapper)

    # wkhtmltopdf search
    possible_paths = [
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"/usr/local/bin/wkhtmltopdf",
        r"/usr/bin/wkhtmltopdf",
    ]

    wk_path = next((p for p in possible_paths if os.path.exists(p)), None)
    if wk_path is None:
        print("❌ wkhtmltopdf not found — PDF skipped.")
        return None

    config = pdfkit.configuration(wkhtmltopdf=wk_path)

    options = {
        "enable-local-file-access": None,
        "load-error-handling": "ignore",
        "disable-external-links": None,
    }

    try:
        pdfkit.from_file(tmp_html_path, path, configuration=config, options=options)
        print(f" PDF exported: {path}")
        return path
    except Exception as e:
        print("❌ PDF EXPORT ERROR:", e)
        return None
