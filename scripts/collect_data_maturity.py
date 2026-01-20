import requests
from bs4 import BeautifulSoup
import json
import os
import time

PHASES = ["1.-quickwins", "2.-foundational", "3.-efficient", "4.-optimized"]
# PHASES = ["1.-quickwins"]

BASE_URL = "https://maturitymodel.security.aws.dev/en/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

def get_section_text(soup, header_text):
    """Lấy toàn bộ nội dung dưới một tiêu đề cụ thể cho đến khi gặp tiêu đề tiếp theo"""
    for header in soup.find_all(['h2', 'h3', 'h4']):
        if header_text.lower() in header.get_text().lower():
            content = []
            for sibling in header.find_next_siblings():
                if sibling.name in ['h1', 'h2', 'h3', 'h4']: # Gặp tiêu đề mới thì dừng
                    break
                content.append(sibling.get_text(separator=" ").strip())
            return "\n".join(content)
    return ""

def scrape_full_detail():
    all_data = []
    for phase_folder in PHASES:
        phase_url = f"{BASE_URL}{phase_folder}/"
        print(f"🚀 Đang quét Phase: {phase_folder}...")
        try:
            res = requests.get(phase_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.content, "html.parser")
            # Lấy tất cả các link action
            links = soup.find_all("a", href=True)
            action_links = []
            for l in links:
                href = l["href"]
                if f"/{phase_folder}/" in href and len(href.split("/")) > 3:
                    if not href.startswith("http"):
                        href = "https://maturitymodel.security.aws.dev" + href
                    action_links.append(href)
            
            action_links = list(set(action_links))

            for link in action_links:
                try:
                    res = requests.get(link, headers=HEADERS, timeout=15)
                    detail_soup = BeautifulSoup(res.content, "html.parser")
                    
                    title = detail_soup.find("h1").get_text(strip=True)
                    
                    # 1. Tóm tắt ban đầu (nằm trước h2 đầu tiên)
                    intro = []
                    first_h2 = detail_soup.find(['h2', 'h3'])
                    main_div = detail_soup.find("div", {"id": "body-inner"}) or detail_soup.find("main")
                    if main_div:
                        for child in main_div.children:
                            if child == first_h2: break
                            if child.name == 'p': intro.append(child.get_text(strip=True))

                    # 2. Bóc tách từng phần theo yêu cầu của Phát
                    risk = get_section_text(detail_soup, "Risk Mitigation")
                    how_to_check = get_section_text(detail_soup, "How to check")
                    guidance = get_section_text(detail_soup, "Guidance for assessments")
                    
                    # 3. Lấy Code Snippets (JSON/SCP)
                    code_blocks = [code.get_text() for code in detail_soup.find_all("pre")]

                    all_data.append({
                        "phase": phase_folder.replace(".-", " "),
                        "title": title,
                        "summary": " ".join(intro),
                        "risk_explanation": risk,
                        "recommendation": get_section_text(detail_soup, "Additional Best Practices") or " ".join(intro),
                        "how_to_check": how_to_check,
                        "guidance": guidance,
                        "code_examples": code_blocks,
                        "url": link
                    })
                    print(f"   ✅ Đã bóc tách chi tiết: {title}")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"   ❌ Lỗi tại {link}: {e}")
        except Exception as e:
            print(f"❌ Lỗi Phase {phase_folder}: {e}")

    os.makedirs("data/raw", exist_ok=True)
    with open("data/raw/maturity_model_v3_detailed.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"\n✨ XONG! Đã lưu dữ liệu chi tiết tại data/raw/maturity_model_v3_detailed.json")

if __name__ == "__main__":
    scrape_full_detail()