#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سحب البيانات من بوابة أم القرى (uqn.gov.sa)

يدعم القسمين:
  - اللوائح والأنظمة : /decisions/rules-and-regulations
  - قرارات مجلس الوزراء : /decisions/council-of-ministers-decisions

يجمع لكل عنصر: الرقم، العنوان، التاريخ، والنص الكامل، ويخرجها في ملف JSON.

أمثلة:
  python scrapers/uqn_scraper.py --section rules --all -o data/uqn_rules.json
  python scrapers/uqn_scraper.py --section decisions --limit 12 -o data/uqn_decisions.json
  python scrapers/uqn_scraper.py --section rules --all --engine playwright -o data/uqn_rules.json
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse, urlencode, urlsplit, parse_qsl, urlunsplit

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None


BASE = "https://www.uqn.gov.sa"

SECTIONS = {
    "rules": "/decisions/rules-and-regulations",
    "decisions": "/decisions/council-of-ministers-decisions",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# محارف التحكم في اتجاه النص التي تظهر داخل التواريخ في الموقع
BIDI_CHARS = "​‌‍‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


# ---------------------------------------------------------------- utilities

def clean(text):
    """إزالة محارف الاتجاه وتوحيد المسافات."""
    if not text:
        return ""
    for ch in BIDI_CHARS:
        text = text.replace(ch, "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def to_ascii_digits(text):
    return (text or "").translate(ARABIC_DIGITS)


def with_page(url, page):
    """إضافة/تحديث معامل الصفحة في الرابط."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


# ------------------------------------------------------------------ parsing

def _soup(html):
    if BeautifulSoup is None:
        sys.exit("ينقص المتطلب beautifulsoup4 — نفّذ: pip install -r scrapers/requirements.txt")
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


# روابط التنقل العامة التي يجب تجاهلها عند جمع روابط العناصر
NAV_HINTS = (
    "/login", "/register", "/search", "/contact", "/about", "/privacy",
    "/terms", "/sitemap", "/rss", "/media", "/news-", "/help", "/faq",
    "javascript:", "mailto:", "tel:", "#",
)


def extract_item_links(html, list_url):
    """استخراج روابط صفحات التفاصيل من صفحة القائمة، مع الحفاظ على الترتيب."""
    soup = _soup(html)
    list_path = urlparse(list_url).path.rstrip("/")

    # نجرب أولًا الحاويات المتوقعة، ثم نتوسّع لكل الصفحة
    scopes = []
    for sel in (
        "a.article-link", ".article-item a", ".article-card a", ".card a",
        ".decision-item a", ".list-item a", "article a", ".results a",
    ):
        found = soup.select(sel)
        if found:
            scopes.append(found)
    scopes.append(soup.select("a[href]"))

    for anchors in scopes:
        links, seen = [], set()
        for a in anchors:
            href = (a.get("href") or "").strip()
            if not href or any(h in href.lower() for h in NAV_HINTS):
                continue
            absolute = urljoin(list_url, href)
            parts = urlparse(absolute)
            if parts.netloc and parts.netloc != urlparse(list_url).netloc:
                continue
            path = parts.path.rstrip("/")
            if path == list_path or not path:
                continue
            # صفحة تفاصيل = مسار أعمق من مسار القائمة، أو مسار يحمل معرّفًا رقميًا
            deeper = path.startswith(list_path + "/")
            has_id = bool(re.search(r"/\d{2,}(?:$|/|-)", path))
            if not (deeper or has_id):
                continue
            key = absolute.split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            links.append(key)
        if links:
            return links
    return []


def parse_number_and_date(text):
    """استخراج رقم النظام/القرار وتاريخ إقراره من نص مثل:
    'قرار رقم (246) وتاريخ 05/03/1448هـ'  أو  'مرسوم ملكي رقم (م/12) وتاريخ ...'"""
    text = clean(text)
    if not text:
        return None, None, None

    kind = None
    m_kind = re.match(r"\s*((?:قرار|مرسوم\s+ملكي|أمر\s+ملكي|أمر\s+سام[يٍ]?|نظام|لائحة)[^\d(رقم]*)", text)
    if m_kind:
        kind = clean(m_kind.group(1)) or None

    number = None
    m_num = re.search(r"رقم\s*\(?\s*([^\)\s]{1,20}?)\s*\)?\s*(?:و?تاريخ|$|،)", text)
    if m_num:
        number = to_ascii_digits(clean(m_num.group(1))).strip("()")

    date_hijri = None
    m_date = re.search(r"تاريخ\s*([0-9٠-٩]{1,2}\s*/\s*[0-9٠-٩]{1,2}\s*/\s*[0-9٠-٩]{4})", text)
    if m_date:
        date_hijri = re.sub(r"\s*", "", to_ascii_digits(m_date.group(1)))

    return kind, number, date_hijri


def parse_publish_dates(text):
    """تفكيك 'ت 1448-3-15 الموافق 28-08-2026' إلى هجري وميلادي."""
    text = to_ascii_digits(clean(text))
    hijri = gregorian = None
    m = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
    if m:
        hijri = m.group(1).replace("/", "-")
    m = re.search(r"الموافق\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})", text)
    if m:
        gregorian = m.group(1).replace("/", "-")
    else:
        m = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})", text)
        if m:
            gregorian = m.group(1).replace("/", "-")
    return hijri, gregorian


def _first_text(soup, selectors):
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            value = clean(el.get_text(" ", strip=True))
            if value:
                return value
    return None


def parse_detail(html, url):
    """استخراج حقول عنصر واحد (نظام / لائحة / قرار) من صفحة التفاصيل."""
    soup = _soup(html)

    title = _first_text(soup, ["h1.article-title", ".article-title", "h1"])
    publish_raw = _first_text(soup, [".date-item span", ".date-item", ".article-date", "time"])
    publish_hijri, publish_gregorian = parse_publish_dates(publish_raw or "")

    subtitle = _first_text(soup, ["p.article-subtitle", ".article-subtitle"])
    kind, number, issue_date_hijri = parse_number_and_date(subtitle or "")
    if not number:  # بعض الصفحات تضع الرقم في العنوان فقط
        kind2, number2, date2 = parse_number_and_date(title or "")
        kind = kind or kind2
        number = number or number2
        issue_date_hijri = issue_date_hijri or date2

    body = soup.select_one("article#article-content") or soup.select_one(".article-desc") \
        or soup.select_one("article") or soup.select_one(".article-body")

    paragraphs, content_html = [], None
    if body:
        content_html = str(body)
        for node in body.select("p, li, h2, h3, h4, td"):
            if node.find(["p", "li", "table"]):  # تجاهل الحاويات المتداخلة
                continue
            value = clean(node.get_text(" ", strip=True))
            if value:
                paragraphs.append(value)
        if not paragraphs:
            paragraphs = [p for p in (clean(x) for x in body.get_text("\n", strip=True).split("\n")) if p]

    # إزالة العنوان الفرعي المكرر من أول المحتوى
    if paragraphs and subtitle and paragraphs[0] == subtitle:
        paragraphs = paragraphs[1:]

    return {
        "url": url,
        "title": title,
        "type": kind,
        "number": number,
        "issue_date_hijri": issue_date_hijri,
        "publish_date_hijri": publish_hijri,
        "publish_date_gregorian": publish_gregorian,
        "publish_date_raw": publish_raw,
        "subtitle": subtitle,
        "content_paragraphs": paragraphs,
        "content_text": "\n\n".join(paragraphs),
        "content_html": content_html,
    }


# ------------------------------------------------------------------ engines

class HttpEngine:
    """محرك بسيط يعتمد requests — يصلح إذا كانت الصفحات تُبنى في الخادم."""

    name = "http"

    def __init__(self, timeout=30, retries=4):
        if requests is None:
            sys.exit("ينقص المتطلب requests — نفّذ: pip install -r scrapers/requirements.txt")
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ar,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml",
        })

    def get(self, url):
        delay = 2
        last = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, timeout=self.timeout)
                r.raise_for_status()
                r.encoding = r.encoding or "utf-8"
                return r.text
            except Exception as exc:  # شبكة أو رمز خطأ
                last = exc
                if attempt < self.retries - 1:
                    time.sleep(delay)
                    delay *= 2
        raise RuntimeError("تعذّر جلب %s: %s" % (url, last))

    def list_page(self, list_url, page):
        return self.get(list_url if page == 1 else with_page(list_url, page))

    def close(self):
        self.session.close()


class PlaywrightEngine:
    """محرك متصفح — لازم إذا كانت الصفحات تُبنى بجافاسكربت."""

    name = "playwright"

    def __init__(self, headless=True, timeout=45000):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit("ينقص المتطلب playwright — نفّذ: pip install playwright && playwright install chromium")
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=headless)
        self.page = self.browser.new_page(user_agent=USER_AGENT, locale="ar-SA")
        self.timeout = timeout

    def _settle(self, wait_for=None):
        try:
            self.page.wait_for_load_state("networkidle", timeout=self.timeout)
        except Exception:
            pass
        if wait_for:
            try:
                self.page.wait_for_selector(wait_for, timeout=8000)
            except Exception:
                pass

    def get(self, url):
        self.page.goto(url, timeout=self.timeout, wait_until="domcontentloaded")
        self._settle("h1.article-title, .article-title, .article-desc")
        return self.page.content()

    def list_page(self, list_url, page):
        target = list_url if page == 1 else with_page(list_url, page)
        self.page.goto(target, timeout=self.timeout, wait_until="domcontentloaded")
        self._settle("a[href]")
        html = self.page.content()

        # إذا لم يغيّر معامل ?page= المحتوى، نستخدم أزرار الترقيم
        if page > 1 and not extract_item_links(html, list_url):
            for selector in (
                'a[aria-label="%d"]' % page, '.pagination a:text-is("%d")' % page,
                'a:text-is("%d")' % page, '.pagination a[href*="page=%d"]' % page,
            ):
                try:
                    locator = self.page.locator(selector).first
                    if locator.count():
                        locator.click(timeout=5000)
                        self._settle("a[href]")
                        return self.page.content()
                except Exception:
                    continue
        return html

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()


# --------------------------------------------------------------------- main

def collect_links(engine, list_url, max_pages, limit, start_page, delay, verbose=True):
    links, seen = [], set()
    page = start_page
    pages_done = 0
    while pages_done < max_pages:
        html = engine.list_page(list_url, page)
        found = extract_item_links(html, list_url)
        fresh = [u for u in found if u not in seen]
        if verbose:
            print("الصفحة %d: %d رابط (%d جديد)" % (page, len(found), len(fresh)), file=sys.stderr)
        if not fresh:
            break
        for u in fresh:
            seen.add(u)
            links.append(u)
            if limit and len(links) >= limit:
                return links[:limit]
        page += 1
        pages_done += 1
        time.sleep(delay)
    return links[:limit] if limit else links


def main():
    ap = argparse.ArgumentParser(description="سحب اللوائح والأنظمة / قرارات مجلس الوزراء من أم القرى")
    ap.add_argument("--section", choices=sorted(SECTIONS), default="rules",
                    help="rules = اللوائح والأنظمة، decisions = قرارات مجلس الوزراء")
    ap.add_argument("--url", help="رابط قائمة مخصص يتجاوز --section")
    ap.add_argument("--engine", choices=("http", "playwright"), default="http")
    ap.add_argument("--all", action="store_true", help="سحب كل الصفحات حتى النهاية")
    ap.add_argument("--pages", type=int, default=2, help="عدد صفحات القائمة (يُتجاهل مع --all)")
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="حد أقصى لعدد العناصر (0 = بلا حد)")
    ap.add_argument("--delay", type=float, default=1.0, help="ثوانٍ بين الطلبات")
    ap.add_argument("--headless", dest="headless", action="store_true", default=True)
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--list-only", action="store_true", help="طباعة الروابط فقط دون سحب التفاصيل")
    ap.add_argument("--dump-html", metavar="DIR", help="حفظ HTML الخام للتشخيص")
    ap.add_argument("-o", "--out", default="data/uqn_output.json")
    args = ap.parse_args()

    list_url = args.url or (BASE + SECTIONS[args.section])
    max_pages = 10**6 if args.all else max(1, args.pages)

    engine = PlaywrightEngine(headless=args.headless) if args.engine == "playwright" else HttpEngine()

    try:
        links = collect_links(engine, list_url, max_pages, args.limit, args.start_page, args.delay)
        print("إجمالي الروابط: %d" % len(links), file=sys.stderr)

        if args.list_only:
            for u in links:
                print(u)
            return 0

        if not links:
            print("لم يُعثر على روابط. جرّب --engine playwright ثم --dump-html للتشخيص.", file=sys.stderr)
            return 1

        items = []
        for i, url in enumerate(links, 1):
            try:
                html = engine.get(url)
                if args.dump_html:
                    import os
                    os.makedirs(args.dump_html, exist_ok=True)
                    with open("%s/%03d.html" % (args.dump_html, i), "w", encoding="utf-8") as fh:
                        fh.write(html)
                record = parse_detail(html, url)
                record["order"] = i
                items.append(record)
                print("[%d/%d] %s" % (i, len(links), record.get("title") or url), file=sys.stderr)
            except Exception as exc:
                print("[%d/%d] فشل %s: %s" % (i, len(links), url, exc), file=sys.stderr)
                items.append({"url": url, "order": i, "error": str(exc)})
            time.sleep(args.delay)

        import os
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        payload = {
            "source_url": list_url,
            "section": args.section,
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "count": len(items),
            "items": items,
        }
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print("تم الحفظ في %s (%d عنصر)" % (args.out, len(items)), file=sys.stderr)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
