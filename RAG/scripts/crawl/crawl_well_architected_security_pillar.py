#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import time
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

# =========================
# CONFIG (KHÔNG CẦN SỬA)
# =========================

START_URLS = [
    "https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/performance-efficiency-pillar/welcome.html",
    "https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html",
]

OUTPUT_FILE = "aws_well_architected.json"
MAX_PAGES = 120
SLEEP = 0.2

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# =========================
# UTILS
# =========================

def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text_block(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_noise_lines(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        l = line.strip()

        if not l:
            continue

        if l.lower() in [
            "topics",
            "contents",
            "did this page help you?",
            "feedback",
            "on this page"
        ]:
            continue

        lines.append(l)

    return "\n".join(lines)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def canonical(url: str) -> str:
    url, _ = urldefrag(url)
    return url.split("?")[0]


def detect_pillar(url: str) -> str:
    if "security-pillar" in url:
        return "security"
    if "reliability-pillar" in url:
        return "reliability"
    if "operational-excellence" in url:
        return "operational_excellence"
    if "performance-efficiency" in url:
        return "performance_efficiency"
    if "cost-optimization" in url:
        return "cost_optimization"
    return "framework"


# =========================
# CORE
# =========================

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if "text/html" not in r.headers.get("Content-Type", ""):
            return None
        return r.text
    except:
        return None


def extract_content(soup):
    main = soup.select_one("main") or soup.select_one("article") or soup.body

    # remove noise
    for tag in main.select("nav, header, footer, script, style"):
        tag.decompose()

    blocks = []
    headings = []

    for tag in main.find_all(["h1", "h2", "h3", "p", "li"]):
        text = clean_text(tag.get_text())

        if not text:
            continue

        if tag.name in ["h1", "h2", "h3"]:
            headings.append(text)
            blocks.append(f"\n## {text}\n")
        elif tag.name == "li":
            blocks.append(f"- {text}")
        else:
            blocks.append(text)

    content = "\n".join(blocks)
    content = normalize_text_block(content)
    content = remove_noise_lines(content)

    return content, headings


def extract_links(base_url, soup):
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("#"):
            full = canonical(urljoin(base_url, href))
            if "wellarchitected/latest" in full:
                links.append(full)

    return list(set(links))


def crawl():
    visited = set()
    queue = list(START_URLS)
    docs = []

    while queue and len(visited) < MAX_PAGES:
        url = queue.pop(0)

        if url in visited:
            continue

        visited.add(url)

        html = fetch(url)
        if not html:
            print(f"[FAIL] {url}")
            continue

        soup = BeautifulSoup(html, "lxml")

        title = clean_text(
            (soup.find("h1") or soup.find("title")).get_text()
        )

        content, headings = extract_content(soup)

        if len(content) < 200:
            print(f"[SKIP] {url}")
            continue

        doc = {
            "doc_id": slugify(title + "_" + url.split("/")[-1]),
            "url": url,
            "title": title,
            "pillar": detect_pillar(url),
            "content": content,
            "headings": headings,
            "word_count": len(content.split()),
            "metadata": {
                "source": "aws_docs",
                "framework": "well_architected"
            }
        }

        docs.append(doc)

        print(f"[OK] {url} -> {doc['word_count']} words")

        # crawl tiếp
        for link in extract_links(url, soup):
            if link not in visited:
                queue.append(link)

        time.sleep(SLEEP)

    return docs


# =========================
# RUN
# =========================

if __name__ == "__main__":
    print("=== START CRAWL AWS WELL-ARCHITECTED ===")

    docs = crawl()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2, ensure_ascii=False)

    print(f"\n=== DONE ===")
    print(f"Total docs: {len(docs)}")
    print(f"Saved to: {OUTPUT_FILE}")