#!/usr/bin/env python3
"""
Reformat raw AWS Well-Architected Security Pillar JSONL into a cleaner raw format
that is easier to normalize later.

Input:
    aws_well_architected_security.jsonl

Output:
    aws_well_architected_security_raw_clean.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any
from urllib.parse import urlparse


def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_common_noise_lines(lines: list[str]) -> list[str]:
    noise_patterns = [
        r"^Did this page help you\??$",
        r"^Thanks for letting us know.*$",
        r"^Javascript is disabled or is unavailable in your browser\.$",
        r"^To use the Amazon Web Services Documentation, Javascript must be enabled\.$",
        r"^Document Conventions$",
        r"^Contributors$",
        r"^Document revisions$",
        r"^Resources$",
        r"^Related resources$",
    ]

    compiled = [re.compile(pat, re.IGNORECASE) for pat in noise_patterns]

    cleaned: list[str] = []
    for line in lines:
        line = normalize_whitespace(line)
        if not line:
            continue

        if any(p.match(line) for p in compiled):
            continue

        cleaned.append(line)

    return cleaned


def dedupe_consecutive(lines: list[str]) -> list[str]:
    output: list[str] = []
    prev = None
    for line in lines:
        if line != prev:
            output.append(line)
        prev = line
    return output


def split_paragraphs_from_content(content: str) -> list[str]:
    """
    The crawler stored content as newline-separated blocks.
    Here we preserve those blocks as paragraph-like units.
    """
    if not content:
        return []

    lines = [normalize_whitespace(x) for x in content.split("\n")]
    lines = strip_common_noise_lines(lines)
    lines = dedupe_consecutive(lines)

    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush():
        nonlocal buffer
        if buffer:
            paragraph = normalize_whitespace(" ".join(buffer))
            if paragraph:
                paragraphs.append(paragraph)
            buffer = []

    for line in lines:
        # Heuristic: short heading-like lines start a new paragraph block
        is_heading_like = (
            len(line) <= 100
            and not line.endswith(".")
            and not line.endswith(":")
            and line[:1].isupper()
        )

        if is_heading_like:
            flush()
            paragraphs.append(line)
        else:
            buffer.append(line)

    flush()

    # Remove trivial duplicates again at paragraph level
    final_paragraphs = dedupe_consecutive(paragraphs)
    return final_paragraphs


def clean_page_title(page_title: str) -> str:
    if not page_title:
        return ""
    title = normalize_whitespace(page_title)

    # AWS docs often use "X - Security Pillar"
    title = re.sub(r"\s*-\s*Security Pillar\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*-\s*AWS Well-Architected Framework\s*$", "", title, flags=re.IGNORECASE)
    return title.strip()


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    if filename.endswith(".html"):
        filename = filename[:-5]
    return filename or "unknown"


def path_from_url(url: str) -> str:
    return urlparse(url).path


def build_raw_id(slug: str) -> str:
    return f"wa_raw:{slug}"


def bool_hint_from_text(text: str, patterns: list[str]) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in patterns)


def reformat_record(obj: dict[str, Any]) -> dict[str, Any]:
    url = obj.get("url", "").strip()
    page_title = obj.get("page_title", "").strip()
    h1 = obj.get("h1", "").strip()
    section_path = obj.get("section_path", []) or []
    content = obj.get("content", "")

    slug = slug_from_url(url)
    path = path_from_url(url)

    content_raw = normalize_whitespace(content)
    content_paragraphs = split_paragraphs_from_content(content_raw)
    content_clean = "\n\n".join(content_paragraphs)

    combined_hint_text = " ".join(
        [
            clean_page_title(page_title),
            h1,
            " ".join(section_path),
            content_clean,
        ]
    )

    record = {
        "raw_id": build_raw_id(slug),
        "url": url,
        "path": path,
        "slug": slug,
        "page_title": normalize_whitespace(page_title),
        "page_title_clean": clean_page_title(page_title),
        "h1": normalize_whitespace(h1),
        "section_path": [normalize_whitespace(x) for x in section_path if normalize_whitespace(x)],
        "pillar": obj.get("pillar", "security"),
        "source_name": obj.get("source_name", "aws_well_architected_security_pillar"),
        "source_type": obj.get("source_type", "official_doc"),
        "source_uri": obj.get("source_uri", url),
        "language": obj.get("language", "en"),
        "crawl_version": obj.get("crawl_version", ""),
        "content_raw": content_raw,
        "content_clean": content_clean,
        "content_paragraphs": content_paragraphs,
        "char_count": len(content_clean),
        "paragraph_count": len(content_paragraphs),
        "has_implementation_guidance": bool_hint_from_text(
            combined_hint_text,
            [
                "implementation guidance",
                "implementation steps",
                "how to implement",
            ],
        ),
        "has_recommendations_hint": bool_hint_from_text(
            combined_hint_text,
            [
                "best practice",
                "recommendation",
                "recommended",
                "consider",
                "should",
            ],
        ),
        "has_detection_hint": bool_hint_from_text(
            combined_hint_text,
            [
                "detect",
                "detection",
                "logging",
                "monitoring",
                "traceability",
                "alert",
            ],
        ),
        "has_identity_hint": bool_hint_from_text(
            combined_hint_text,
            [
                "identity",
                "iam",
                "permission",
                "least privilege",
                "federation",
                "role",
                "credential",
                "access management",
            ],
        ),
        "has_data_protection_hint": bool_hint_from_text(
            combined_hint_text,
            [
                "encrypt",
                "encryption",
                "kms",
                "key management",
                "data protection",
                "protect data",
                "data at rest",
                "data in transit",
            ],
        ),
        "has_incident_response_hint": bool_hint_from_text(
            combined_hint_text,
            [
                "incident response",
                "playbook",
                "forensic",
                "game day",
                "containment",
                "post-incident",
            ],
        ),
    }

    return record


def read_jsonl(path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {i}: {e}") from e
    return records


def write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    out_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(out_dir, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reformat raw Well-Architected Security Pillar JSONL."
    )
    parser.add_argument(
        "--input",
        default="aws_well_architected_security.jsonl",
        help="Input raw JSONL file.",
    )
    parser.add_argument(
        "--output",
        default="aws_well_architected_security_raw_clean.jsonl",
        help="Output cleaned raw JSONL file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = (
        args.input
        if os.path.isabs(args.input)
        else os.path.join(script_dir, args.input)
    )
    output_path = (
        args.output
        if os.path.isabs(args.output)
        else os.path.join(script_dir, args.output)
    )

    rows = read_jsonl(input_path)
    cleaned = [reformat_record(row) for row in rows]
    write_jsonl(output_path, cleaned)

    print(f"[DONE] input={len(rows)} records -> output={len(cleaned)} records")
    print(f"[OUT] {output_path}")


if __name__ == "__main__":
    main()