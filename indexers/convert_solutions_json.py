"""
Convert Freshdesk Solutions.json → FAQ CSV (data/faqs/solutions_faq.csv).

Structure recognised:
  Category  →  {order}_{GROUP}_{Thai topic}_{ENV}
  Folder    →  01_DEFAULT                     (generic, applies to all companies)
            →  XX_COMPANY_{topic}_{Company}   (company-specific override)

Groups decoded:
  NON_LOGIN       — user cannot log in (registration / phone-change / login problems)
  LOGIN           — user is logged in  (phone-change while authenticated)
  FEATURE_SOD     — Salary-on-Demand withdrawal features
  FEATURE_FLEXBEN — Flexible Benefits
  FEATURE_DIRECT_DEBIT — Bank account linking

CSV output columns (matches existing FAQ CSV schema):
  Context, Question, Answer, source_type, company_id, incident, tags, followup_questions

Tags include:
  default          — article is the generic / fallback version
  company_specific — article belongs to a specific company

Usage:
    python indexers/convert_solutions_json.py --file ~/Downloads/Solutions.json
    python indexers/convert_solutions_json.py --file ~/Downloads/Solutions.json --out data/faqs/solutions_faq.csv

After running:
    python indexers/merge_data.py
    python indexers/index_faq_csv.py --file data/merged/<company>_th.csv --company <company>
"""

import argparse
import base64
import csv
import json
import re
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


# ── Company slug aliases (maps variant → canonical) ──────────────────────────
# Freshdesk folder names are sometimes inconsistent; merge variants into one slug.
_COMPANY_ALIASES: dict[str, str] = {
    "bonnthavorn":                                  "boonthavorn",
    "centralretail":                                "central_retail",
    "crg_group":                                    "crg",
    "ifs":                                          "ifs_group",
    "n_a_p_security_guard":                         "nap_guard",
    "n_a_p_service_and_trading":                    "nap_service_and_trading",
    "mud_hound":                                    "mud_and_hound_group",
    "the_fresh_food_getfresh_group":                "the_fresh_food_getfresh_fresh_food_hospitality",
    "thairung_partners_group":                      "thairung_group",
    "rocks_pc_meraki_rocks_khao_soi_group":         "rocks_pc_meraki_rocks_khao_soi",
    "homa_hertz_insee":                             "insee_group",
}


# ── Category group → (source_type, user_state label) ─────────────────────────
_GROUP_MAP: dict[str, tuple[str, str]] = {
    "NON_LOGIN":           ("non_login",           "ก่อนเข้าสู่ระบบ"),
    "LOGIN":               ("login",               "หลังเข้าสู่ระบบ"),
    "FEATURE_SOD":         ("feature_sod",         ""),
    "FEATURE_FLEXBEN":     ("feature_flexben",     ""),
    "FEATURE_DIRECT_DEBIT":("feature_direct_debit",""),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_category(raw_name: str) -> tuple[str, str, str]:
    """
    '12_FEATURE_SOD_เงื่อนไขอื่นๆ_PROD'
    → source_type='feature_sod', topic='เงื่อนไขอื่นๆ', state_label=''

    '07_NON_LOGIN_วิธีการเปลี่ยนเบอร์โทรศัพท์_PROD'
    → source_type='non_login', topic='วิธีการเปลี่ยนเบอร์โทรศัพท์', state_label='ก่อนเข้าสู่ระบบ'
    """
    name = re.sub(r"^\d+_", "", raw_name)           # strip leading order
    name = re.sub(r"_(PROD|DEV|UAT)$", "", name)    # strip env suffix

    source_type = "faq"
    state_label = ""

    for key, (stype, slabel) in _GROUP_MAP.items():
        if name.startswith(key + "_"):
            source_type = stype
            state_label = slabel
            name = name[len(key) + 1:]
            break

    topic = name.strip("_").strip()
    return source_type, topic, state_label


def _parse_folder(folder_name: str) -> tuple[bool, str]:
    """
    '01_DEFAULT'                                   → is_default=True,  company_id='salary_hero'
    '01_COMPANY_ยอดเงินไม่อัปเดต_Default ( No T&A Company )' → is_default=True, company_id='no_ta'
    '02_COMPANY_เงื่อนไขอื่นๆ_Boonthavorn'        → is_default=False, company_id='boonthavorn'
    '03_COMPANY_วิธีการเปลี่ยนเบอร์โทรศัพท์_PCS_Foodhouse' → is_default=False, company_id='pcs_foodhouse'
    """
    name = re.sub(r"^\d+_", "", folder_name)  # strip order prefix

    # Plain DEFAULT folder
    if name.upper() == "DEFAULT" or name.upper() == "DRAFTS":
        return True, "salary_hero"

    # COMPANY_topic_CompanyName pattern
    m = re.match(r"COMPANY_[^_]+?_(.+)$", name, re.IGNORECASE)
    if m:
        raw_company = m.group(1).strip()
        # Special "Default (No T&A Company)" → treat as generic fallback
        if re.search(r"default|no.?t.?a", raw_company, re.IGNORECASE):
            return True, "no_ta"
        slug = _slugify(raw_company)
        return False, _COMPANY_ALIASES.get(slug, slug)

    # Fallback: treat as generic
    return True, "salary_hero"


def _slugify(name: str) -> str:
    """
    Convert a company display name to a short lowercase slug.
    Handles both English and Thai names.

    'PCS Foodhouse'      → 'pcs_foodhouse'
    'Greyhound Cafe'     → 'greyhound_cafe'
    'R89'                → 'r89'
    'พนักงานรักษาความปลอดภัย' → 'พนักงานรักษาความปลอดภัย'  (kept as-is, Thai)
    """
    # Only use ASCII path if there are real alphanumeric ASCII characters
    ascii_only = re.sub(r"[^\x00-\x7F]", "", name).strip()
    if ascii_only and re.search(r"[a-zA-Z0-9]", ascii_only):
        slug = ascii_only.lower()
        slug = re.sub(r"[^a-z0-9]+", "_", slug)
        return slug.strip("_")

    # Thai or mixed — keep Thai characters, lowercase ASCII parts
    slug = name.strip().lower()
    slug = re.sub(r"[\s/\\,.()\[\]&+]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


def _clean_html(html: str) -> str:
    """Strip HTML tags, decode entities, normalise whitespace."""
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>|</div>|</li>|</tr>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = (text
            .replace("&nbsp;", " ")
            .replace("&amp;",  "&")
            .replace("&lt;",   "<")
            .replace("&gt;",   ">")
            .replace("&quot;", '"'))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_context(topic: str, state_label: str) -> str:
    """Combine topic + user-state label into the Context field."""
    if state_label:
        return f"{topic} ({state_label})"
    return topic


# ── Vision extraction ─────────────────────────────────────────────────────────

_STUB_MARKERS = ("ได้ตามด้านล่าง", "ตามด้านล่าง")

def _extract_image_urls(html: str) -> list[str]:
    return re.findall(r'src=["\']?(https://s3[^"\'> ]+)', html)


def _is_stub(text: str, html: str) -> bool:
    """True when the cleaned text is boilerplate and the raw HTML has images."""
    short = len(text.strip()) < 150
    has_stub = any(m in text for m in _STUB_MARKERS)
    has_img = bool(_extract_image_urls(html))
    return short and has_stub and has_img


def _vision_extract(image_url: str, title: str) -> str | None:
    """Download image and ask Claude to extract conditions as plain Thai text."""
    try:
        import anthropic, os
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_bytes = resp.read()
            content_type = resp.headers.get("Content-Type", "image/png").split(";")[0].strip()

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": content_type,
                            "data": base64.standard_b64encode(img_bytes).decode("utf-8"),
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"นี่คือภาพข้อมูลเกี่ยวกับ '{title}'\n"
                            "สกัดข้อมูลทุกเงื่อนไข กฎ ค่าธรรมเนียม วันที่ และขั้นตอนออกมาเป็นข้อความไทยธรรมดา\n"
                            "ไม่ใช้ # หัวข้อ markdown ไม่ใช้ ** ตัวหนา ให้ใช้ขึ้นบรรทัดใหม่แทน\n"
                            "ครบถ้วน ชัดเจน ห้ามข้ามข้อมูลใด"
                        ),
                    },
                ],
            }],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        print(f"    [vision] failed for {image_url[:60]}: {exc}", file=sys.stderr)
        return None


# ── Main conversion ───────────────────────────────────────────────────────────

def convert(
    input_path: str,
    output_path: str,
    fallback_answer: str = "กรุณาติดต่อแอดมินเพื่อขอข้อมูลเพิ่มเติมค่ะ",
    use_vision: bool = False,
) -> int:
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    rows: list[dict] = []

    for cat_entry in data:
        cat = cat_entry["category"]
        if not cat.get("all_folders"):
            continue

        source_type, topic, state_label = _parse_category(cat.get("name", ""))
        context = _build_context(topic, state_label)

        for folder in cat["all_folders"]:
            is_default, company_id = _parse_folder(folder.get("name", ""))
            articles = folder.get("articles", [])

            # Sibling titles → followup_questions
            sibling_titles = [
                a["title"].strip()
                for a in articles
                if a.get("title", "").strip()
            ]

            for art in articles:
                title      = (art.get("title") or "").strip()
                raw_html   = art.get("description") or ""
                answer     = _clean_html(raw_html)

                if not title:
                    continue

                if use_vision and _is_stub(answer, raw_html):
                    img_urls = _extract_image_urls(raw_html)
                    for url in img_urls:
                        print(f"    [vision] extracting: {title[:40]} ({company_id})", file=sys.stderr)
                        extracted = _vision_extract(url, title)
                        if extracted:
                            answer = extracted
                            break

                if not answer:
                    answer = fallback_answer

                # Article-level tags + is_default marker
                art_tags = [t.get("name", "") for t in art.get("tags", []) if t.get("name")]
                art_tags.append("default" if is_default else "company_specific")
                tags_str = ";".join(art_tags)

                # Follow-up questions = sibling articles (excluding self)
                followups = ";".join(t for t in sibling_titles if t != title)

                image_urls = ";".join(_extract_image_urls(raw_html))

                rows.append({
                    "Context":            context,
                    "Question":           title,
                    "Answer":             answer,
                    "source_type":        source_type,
                    "company_id":         company_id,
                    "incident":           "",
                    "tags":               tags_str,
                    "followup_questions": followups,
                    "image_urls":         image_urls,
                })

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Context", "Question", "Answer", "source_type",
                  "company_id", "incident", "tags", "followup_questions", "image_urls"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Freshdesk Solutions.json → FAQ CSV")
    parser.add_argument("--file", required=True, help="Path to Solutions.json")
    parser.add_argument("--out",  default="data/faqs/solutions_faq.csv",
                        help="Output CSV path (default: data/faqs/solutions_faq.csv)")
    parser.add_argument("--use-vision", action="store_true",
                        help="Use Claude vision API to extract text from image-only articles")
    args = parser.parse_args()

    n = convert(args.file, args.out, use_vision=args.use_vision)
    print(f"✓ {n} articles → {args.out}")

    # Summary
    import csv as _csv
    with open(args.out, encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))

    from collections import Counter
    by_type    = Counter(r["source_type"] for r in rows)
    by_company = Counter(r["company_id"]  for r in rows)
    defaults   = sum(1 for r in rows if "default" in r["tags"].split(";"))
    specific   = sum(1 for r in rows if "company_specific" in r["tags"].split(";"))

    print(f"\nSource types:   {dict(by_type)}")
    print(f"Default rows:   {defaults}")
    print(f"Company-specific rows: {specific}")
    print(f"Unique companies: {len(by_company)} — {sorted(by_company)[:8]} ...")
    print(f"\nNext steps:")
    print(f"  python indexers/merge_data.py")
    print(f"  python indexers/index_faq_csv.py --file data/merged/salary_hero_th.csv --company salary_hero")


if __name__ == "__main__":
    main()
