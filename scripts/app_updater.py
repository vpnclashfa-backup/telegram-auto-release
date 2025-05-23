import requests
from bs4 import BeautifulSoup
import re
import json
import os
from packaging.version import parse, InvalidVersion
from urllib.parse import urljoin, urlparse, unquote
import logging

# --- پیکربندی اولیه ---
URL_FILE = "urls_to_check.txt"
TRACKING_FILE = "versions_tracker.json"
OUTPUT_JSON_FILE = "updates_found.json"
GITHUB_OUTPUT_FILE = os.environ.get('GITHUB_OUTPUT', 'local_github_output.txt')

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# --- توابع کمکی (بدون تغییر) ---

def load_tracker():
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logging.info(f"فایل ردیابی {TRACKING_FILE} با موفقیت بارگذاری شد.")
                return data
        except json.JSONDecodeError:
            logging.warning(f"{TRACKING_FILE} خراب است. با ردیاب خالی شروع می شود.")
            return {}
    logging.info(f"فایل ردیابی {TRACKING_FILE} یافت نشد. با ردیاب خالی شروع می شود.")
    return {}

def compare_versions(current_v_str, last_v_str):
    logging.info(f"مقایسه نسخه ها: فعلی='{current_v_str}', قبلی='{last_v_str}'")
    try:
        if not current_v_str: logging.warning("نسخه فعلی نامعتبر است (خالی)."); return False
        if not last_v_str or last_v_str == "0.0.0": logging.info("نسخه قبلی یافت نشد یا 0.0.0 بود، نسخه فعلی جدید است."); return True
        normalize_for_parse = lambda v: re.split(r'[^0-9.]', v, 1)[0].strip('.')
        current_norm = normalize_for_parse(current_v_str)
        last_norm = normalize_for_parse(last_v_str)
        if not current_norm: logging.warning(f"نسخه فعلی '{current_v_str}' پس از نرمال سازی نامعتبر شد."); return False
        if not last_norm: logging.warning(f"نسخه قبلی '{last_v_str}' پس از نرمال سازی نامعتبر شد."); return True
        parsed_current = parse(current_norm)
        parsed_last = parse(last_norm)
        is_newer = parsed_current > parsed_last
        logging.info(f"نتیجه مقایسه (تجزیه شده): فعلی='{parsed_current}', قبلی='{parsed_last}', جدیدتر: {is_newer}")
        return is_newer
    except InvalidVersion as e:
        logging.warning(f"خطای InvalidVersion هنگام مقایسه: {e}. مقایسه به صورت رشته ای انجام می شود.")
        return current_v_str != last_v_str
    except Exception as e:
        logging.error(f"خطای پیش بینی نشده هنگام مقایسه نسخه ها: {e}. مقایسه به صورت رشته ای انجام می شود.")
        return current_v_str != last_v_str

def sanitize_text(text, for_filename=False):
    if not text: return ""
    text = text.strip().lower()
    text = re.sub(r'\((farsroid\.com|.*?)\)', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'[\(\)]', '', text)
    if for_filename:
        text = re.sub(r'[<>:"/\\|?*]', '_', text)
        text = re.sub(r'\s+', '_', text)
    else:
        text = re.sub(r'\s+', '_', text)
    return text

def extract_app_name_from_page(soup, page_url):
    h1_tag = soup.find('h1', class_=re.compile(r'title', re.IGNORECASE))
    if h1_tag:
        title_text = h1_tag.text.strip()
        match = re.match(r'^(?:دانلود\s+)?(.+?)(?:\s+\d+\.\d+.*|\s+–\s+.*|<span class="math-inline">\)', title\_text, re\.IGNORECASE\)
if match and match\.group\(1\)\: return match\.group\(1\)\.strip\(\)
title\_tag \= soup\.find\('title'\)
if title\_tag\:
title\_text \= title\_tag\.text\.strip\(\)
match \= re\.match\(r'^\(?\:دانلود\\s\+\)?\(\.\+?\)\(?\:\\s\+\\d\+\\\.\\d\+\.\*\|\\s\+برنامه\.\*\|\\s\+–\\s\+\.\*\|</span>)', title_text, re.IGNORECASE)
        if match and match.group(1):
            app_name = match.group(1).strip()
            app_name = re.sub(r'\s+(?:اندروید|آیفون|ios|android)$', '', app_name, flags=re.IGNORECASE).strip()
            if app_name: return app_name
    parsed_url = urlparse(page_url)
    path_parts = [part for part in parsed_url.path.split('/') if part]
    if path_parts:
        guessed_name = path_parts[-1].replace('-', ' ').replace('_', ' ')
        return guessed_name.title()
    return "UnknownApp"

# --- منطق خراش دادن خاص سایت فارسروید (اصلاح شده) ---
def scrape_farsroid_page(page_url, soup, tracker_data):
    """اطلاعات دانلود را از یک صفحه فارسروید خراش می دهد."""
    updates_found_on_page = []
    page_app_name = extract_app_name_from_page(soup, page_url)
    logging.info(f"پردازش صفحه فارسروید: {page_url} (نام برنامه: {page_app_name})")

    download_box = soup.find('section', class_='downloadbox')
    if not download_box:
        logging.warning(f"باکس دانلود در {page_url} پیدا نشد.")
        return updates_found_on_page
    logging.info("باکس دانلود پیدا شد.")

    download_links_ul = download_box.find('ul', class_='download-links')
    if not download_links_ul:
        logging.warning(f"لیست لینک های دانلود (ul) در {page_url} پیدا نشد.")
        return updates_found_on_page
    logging.info("لیست لینک های دانلود (ul) پیدا شد.")

    # **تغییر اصلی اینجا:** به جای جستجوی عمومی، مستقیماً li ها را پیدا می کنیم
    found_lis = download_links_ul.find_all('li', class_='download-link')
    logging.info(f"تعداد {len(found_lis)} آیتم li.download-link پیدا شد.")

    if not found_lis:
        logging.warning("هیچ آیتم li.download-link پیدا نشد. شاید ساختار عوض شده؟")
        return updates_found_on_page

    for i, li in enumerate(found_lis):
        logging.info(f"--- پردازش li شماره {i+1} ---")
        # **تغییر اصلی اینجا:** داخل هر li به دنبال a.download-btn می گردیم
        link_tag = li.find('a', class_='download-btn')
        if not link_tag:
            logging.warning(f"  تگ a.download-btn در li شماره {i+1} پیدا نشد. رد شدن...")
            continue

        download_url = urljoin(page_url, link_tag.get('href')) # استفاده از urljoin
        link_text_span = link_tag.find('span', class_='txt')
        link_text = link_text_span.text.strip() if link_text_span else "متن لینک یافت نشد"

        if not download_url or not link_text:
            logging.warning(f"  URL یا متن لینک در li شماره {i+1} ناقص است. رد شدن...")
            continue

        logging.info(f"  URL: {download_url}")
        logging.info(f"  متن: {link_text}")

        version_match = re.search(r'(\d+\.\d+(?:\.\d+){0,2}(?:[.-][a-zA-Z0-9]+)*)', download_url)
        current_version = version_match.group(1) if version_match else None

        if not current_version:
            logging.warning(f"  نسخه از URL '{download_url}' استخراج نشد. رد شدن...")
            continue
        logging.info(f"  نسخه: {current_version}")

        variant = "Universal"
        filename_in_url = unquote(urlparse(download_url).path.split('/')[-1])
        if re.search(r'Armeabi-v7a', filename_in_url + link_text, re.IGNORECASE): variant = "Armeabi-v7a"
        elif re.search(r'Arm64-v8a', filename_in_url + link_text, re.IGNORECASE): variant = "Arm64-v8a"
        elif re.search(r'x86_64', filename_in_url + link_text, re.IGNORECASE): variant = "x86_64"
        elif re.search(r'x86', filename_in_url + link_text, re.IGNORECASE): variant = "x86"
        elif re.search(r'Universal', filename_in_url + link_text, re.IGNORECASE): variant = "Universal"
        logging.info(f"  نوع: {variant}")

        tracking_id = f"{sanitize_text(page_app_name)}_{sanitize_text(variant)}".lower()
        last_known_version = tracker_data.get(tracking_id, "0.0.0")

        if compare_versions(current_version, last_known_version):
            logging.info(f"    => آپدیت جدید برای {tracking_id}: {current_version}")
            app_name_for_file = sanitize_text(page_app_name, for_filename=True)
            variant_for_file = sanitize_text(variant, for_filename=True)
            suggested_filename = f"{app_name_for_file}_v{current_version}_{variant_for_file}.apk"
            updates_found_on_page.append({
                "app_name": page_app_name,
                "version": current_version,
                "variant": variant,
                "download_url": download_url,
                "page_url": page_url,
                "tracking_id": tracking_id,
                "suggested_filename": suggested_filename,
                "current_version_for_tracking": current_version
            })
        else:
            logging.info(f"    => {tracking_id} به‌روز است.")

    return updates_found_on_page

# --- منطق اصلی (بدون تغییر) ---
def main():
    if not os.path.exists(URL_FILE):
        logging.error(f"فایل URL ها یافت نشد: {URL_FILE}")
        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f: json.dump([], f)
        if 'GITHUB_OUTPUT' in os.environ:
            with open(GITHUB_OUTPUT_FILE, 'a') as gh_output: gh_output.write(f"updates_count=0\n")
        sys.exit(1)

    with open(URL_FILE, 'r', encoding='utf-8') as f:
        urls_to_process = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not urls_to_process:
        logging.info("فایل URL ها خالی است.")
        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f: json.dump([], f)
        if 'GITHUB_OUTPUT' in os.environ:
            with open(GITHUB_OUTPUT_FILE, 'a') as gh_output: gh_output.write(f"updates_count=0\n")
        return

    tracker_data = load_tracker()
    all_updates_found = []

    for page_url in urls_to_process:
        logging.info(f"\n--- شروع بررسی URL: {page_url} ---")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)