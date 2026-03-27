#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# =========================
# CONFIG
# =========================

INPUT_FILE = "aws_well_architected.json"
OUTPUT_CLEAN_FILE = "aws_well_architected_clean.json"
OUTPUT_CHUNKS_FILE = "aws_well_architected_chunks.json"

MIN_SECTION_CHARS = 120
MAX_CHUNK_WORDS = 220
MIN_CHUNK_WORDS = 60
OVERLAP_WORDS = 35

DROP_TITLE_PATTERNS = [
    r"^document revisions$",
]

DROP_LINE_PATTERNS = [
    r"^javascript is disabled or is unavailable in your browser\.$",
    r"^to use the amazon web services documentation, javascript must be enabled\.$",
    r"^please refer to your browser'?s help pages for instructions\.$",
    r"^did this page help you\?$",
    r"^thanks for letting us know we'?re doing a good job!$",
    r"^if you'?ve got a moment, please tell us what we did right.*$",
    r"^thanks for letting us know this page needs work\.$",
    r"^we'?re sorry we let you down\.$",
    r"^if you'?ve got a moment, please tell us how we can make the documentation better\.$",
    r"^provide feedback$",
    r"^topics$",
    r"^contents$",
    r"^on this page$",
    r"^pdf$",
    r"^rss feed$",
]

BEST_PRACTICE_RE = re.compile(r"\b([A-Z]{2,5}\d{2}-BP\d{2})\b")
PUBLICATION_DATE_RE = re.compile(r"^publication date:", re.IGNORECASE)


# =========================
# BASIC UTILS
# =========================

def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fix_broken_encoding(text: str) -> str:
    if not text:
        return ""
    replacements = {
        "â": "'",
        "â": '"',
        "â": '"',
        "â": "-",
        "â": "-",
        "â¢": "-",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def clean_line(line: str) -> str:
    line = line.strip()
    line = fix_broken_encoding(line)
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    for pattern in DROP_LINE_PATTERNS:
        if re.match(pattern, line, flags=re.IGNORECASE):
            return True
    return False


def should_drop_doc(title: str) -> bool:
    title = (title or "").strip()
    for pattern in DROP_TITLE_PATTERNS:
        if re.match(pattern, title, flags=re.IGNORECASE):
            return True
    return False


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def extract_best_practice_id(*values: str) -> Optional[str]:
    for value in values:
        if not value:
            continue
        m = BEST_PRACTICE_RE.search(value)
        if m:
            return m.group(1)
    return None


# =========================
# TEXT CLEANING
# =========================

def remove_consecutive_duplicate_lines(lines: List[str]) -> List[str]:
    cleaned = []
    prev_norm = None

    for raw in lines:
        line = clean_line(raw)
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        norm = line.lower()

        # bỏ duplicate liên tiếp
        if norm == prev_norm:
            continue

        # bỏ trường hợp:
        # - Some text
        # Some text
        if line.startswith("- "):
            bullet_norm = line[2:].strip().lower()
            prev_norm = norm
            cleaned.append(line)
            # nếu dòng sau lặp lại sẽ bị loại ở vòng sau
            continue

        if cleaned:
            last = cleaned[-1].strip()
            if last.startswith("- ") and last[2:].strip().lower() == norm:
                continue

        cleaned.append(line)
        prev_norm = norm

    # gọn blank lines
    compact = []
    for line in cleaned:
        if line == "":
            if compact and compact[-1] != "":
                compact.append("")
        else:
            compact.append(line)

    while compact and compact[0] == "":
        compact.pop(0)
    while compact and compact[-1] == "":
        compact.pop()

    return compact


def clean_content_text(content: str) -> str:
    content = normalize_whitespace(fix_broken_encoding(content))
    raw_lines = content.split("\n")

    lines = []
    for raw in raw_lines:
        line = clean_line(raw)

        if is_noise_line(line):
            continue

        # bỏ publication date để giảm nhiễu
        if PUBLICATION_DATE_RE.match(line):
            continue

        lines.append(line)

    lines = remove_consecutive_duplicate_lines(lines)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =========================
# SECTION SPLITTING
# =========================

def split_into_sections(content: str) -> List[Dict[str, str]]:
    """
    Input dạng:
      ## Title
      content...
      ## Another
      content...
    """
    content = normalize_whitespace(content)
    if not content:
        return []

    lines = content.split("\n")
    sections = []

    current_title = None
    current_lines = []

    def flush():
        nonlocal current_title, current_lines
        body = "\n".join(current_lines).strip()
        if current_title and body and len(body) >= MIN_SECTION_CHARS:
            sections.append({
                "section_title": current_title.strip(),
                "content": body
            })
        current_title = None
        current_lines = []

    for line in lines:
        if re.match(r"^##\s+", line):
            flush()
            current_title = re.sub(r"^##\s+", "", line).strip()
        else:
            current_lines.append(line)

    flush()

    # fallback: nếu không parse được heading thì giữ cả page thành 1 section
    if not sections and len(content) >= MIN_SECTION_CHARS:
        sections.append({
            "section_title": "Overview",
            "content": content
        })

    return sections


def classify_chunk_type(section_title: str, page_title: str) -> str:
    s = (section_title or "").lower()

    if "implementation guidance" in s:
        return "implementation_guidance"
    if "implementation steps" in s:
        return "implementation_steps"
    if "improvement plan" in s:
        return "improvement_plan"
    if "anti-pattern" in s or "antipattern" in s:
        return "anti_pattern"
    if "resources" in s or "related resources" in s:
        return "resources"
    if "overview" in s or section_title.strip().lower() == page_title.strip().lower():
        return "overview"
    return "section"


# =========================
# CHUNKING
# =========================

def split_paragraphs(text: str) -> List[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def tokenize_words(text: str) -> List[str]:
    return text.split()


def word_count(text: str) -> int:
    return len(tokenize_words(text))


def chunk_section_text(text: str, max_words: int, min_words: int, overlap_words: int) -> List[str]:
    paragraphs = split_paragraphs(text)

    # nếu không có paragraph rõ ràng, fallback theo câu
    if len(paragraphs) <= 1:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        paragraphs = [s.strip() for s in sentences if s.strip()]

    chunks = []
    current_parts = []
    current_words = 0

    def flush():
        nonlocal current_parts, current_words
        if not current_parts:
            return

        chunk = "\n\n".join(current_parts).strip()
        if chunk:
            chunks.append(chunk)

        if overlap_words > 0 and current_parts:
            all_words = tokenize_words(chunk)
            overlap = all_words[-overlap_words:] if len(all_words) > overlap_words else all_words
            overlap_text = " ".join(overlap).strip()

            current_parts = [overlap_text] if overlap_text else []
            current_words = len(tokenize_words(overlap_text))
        else:
            current_parts = []
            current_words = 0

    for para in paragraphs:
        para_words = word_count(para)

        # paragraph quá dài -> cắt sliding window trực tiếp
        if para_words > max_words:
            if current_parts and current_words >= min_words:
                flush()
            elif current_parts:
                current_parts.append(para)
                flush()
                continue

            words = tokenize_words(para)
            step = max_words - overlap_words if max_words > overlap_words else max_words

            start = 0
            while start < len(words):
                end = min(start + max_words, len(words))
                piece = " ".join(words[start:end]).strip()
                if piece:
                    chunks.append(piece)
                if end >= len(words):
                    break
                start += step
            current_parts = []
            current_words = 0
            continue

        if current_words + para_words <= max_words:
            current_parts.append(para)
            current_words += para_words
        else:
            if current_words >= min_words:
                flush()
                current_parts.append(para)
                current_words += para_words
            else:
                current_parts.append(para)
                current_words += para_words
                flush()

    if current_parts:
        chunk = "\n\n".join(current_parts).strip()
        if chunk:
            chunks.append(chunk)

    # lọc chunk quá ngắn
    final_chunks = []
    for chunk in chunks:
        wc = word_count(chunk)
        if wc >= 20:
            final_chunks.append(chunk)

    return final_chunks


# =========================
# PAGE CLEANING
# =========================

def build_clean_doc(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = (doc.get("title") or "").strip()
    if should_drop_doc(title):
        return None

    content = clean_content_text(doc.get("content") or "")
    if not content:
        return None

    headings = []
    for h in doc.get("headings") or []:
        hh = clean_line(h)
        if hh and not is_noise_line(hh):
            if not headings or headings[-1].lower() != hh.lower():
                headings.append(hh)

    clean_doc = {
        "doc_id": doc.get("doc_id"),
        "url": doc.get("url"),
        "title": title,
        "pillar": doc.get("pillar") or "framework",
        "content": content,
        "headings": headings,
        "word_count": word_count(content),
        "metadata": {
            **(doc.get("metadata") or {}),
            "source": "aws_docs",
            "framework": "well_architected",
            "cleaned": True,
        }
    }

    return clean_doc


# =========================
# CHUNK RECORD BUILDING
# =========================

def build_chunk_records(clean_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    page_title = clean_doc["title"]
    pillar = clean_doc["pillar"]
    url = clean_doc["url"]
    page_doc_id = clean_doc["doc_id"]
    content = clean_doc["content"]

    best_practice_id_page = extract_best_practice_id(page_title, content[:400])

    sections = split_into_sections(content)
    records = []

    for sec_idx, section in enumerate(sections, start=1):
        section_title = section["section_title"].strip()
        section_content = section["content"].strip()

        # loại section kém giá trị
        if len(section_content) < MIN_SECTION_CHARS:
            continue

        best_practice_id = extract_best_practice_id(section_title, page_title, section_content[:300])
        chunk_type = classify_chunk_type(section_title, page_title)

        pieces = chunk_section_text(
            text=section_content,
            max_words=MAX_CHUNK_WORDS,
            min_words=MIN_CHUNK_WORDS,
            overlap_words=OVERLAP_WORDS,
        )

        for part_idx, piece in enumerate(pieces, start=1):
            piece_wc = word_count(piece)
            if piece_wc < 20:
                continue

            chunk_id = (
                f"{page_doc_id}__"
                f"{slugify(section_title or 'section')}__"
                f"{part_idx:02d}"
            )

            records.append({
                "chunk_id": chunk_id,
                "doc_id": page_doc_id,
                "source": "aws_well_architected",
                "pillar": pillar,
                "url": url,
                "page_title": page_title,
                "section_title": section_title,
                "best_practice_id": best_practice_id or best_practice_id_page,
                "chunk_type": chunk_type,
                "chunk_index": part_idx,
                "section_index": sec_idx,
                "content": piece,
                "word_count": piece_wc,
                "metadata": {
                    "framework": "well_architected",
                    "source_type": "aws_docs",
                    "page_doc_id": page_doc_id,
                    "cleaned": True,
                    "section_chunked": True,
                }
            })

    return records


# =========================
# RUN
# =========================

def main() -> None:
    base_dir = Path(__file__).resolve().parent
    input_path = base_dir / INPUT_FILE
    clean_path = base_dir / OUTPUT_CLEAN_FILE
    chunks_path = base_dir / OUTPUT_CHUNKS_FILE

    if not input_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file input: {input_path}\n"
            f"Hãy đặt file '{INPUT_FILE}' cùng folder với script này."
        )

    with open(input_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print("=== CLEAN AND CHUNK AWS WELL-ARCHITECTED ===")
    print(f"[INFO] Input docs: {len(docs)}")

    clean_docs = []
    all_chunks = []

    for i, doc in enumerate(docs, start=1):
        clean_doc = build_clean_doc(doc)
        if not clean_doc:
            print(f"[SKIP] {i}/{len(docs)} title={doc.get('title')!r}")
            continue

        chunks = build_chunk_records(clean_doc)

        if not chunks:
            print(f"[WARN] {i}/{len(docs)} no chunks -> {clean_doc['title']}")
            continue

        clean_docs.append(clean_doc)
        all_chunks.extend(chunks)

        print(
            f"[OK] {i}/{len(docs)} "
            f"title={clean_doc['title'][:70]} | "
            f"clean_words={clean_doc['word_count']} | "
            f"chunks={len(chunks)}"
        )

    with open(clean_path, "w", encoding="utf-8") as f:
        json.dump(clean_docs, f, ensure_ascii=False, indent=2)

    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print("\n=== DONE ===")
    print(f"[INFO] Clean docs  : {len(clean_docs)}")
    print(f"[INFO] Total chunks: {len(all_chunks)}")
    print(f"[SAVE] {clean_path.name}")
    print(f"[SAVE] {chunks_path.name}")


if __name__ == "__main__":
    main()