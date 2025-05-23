import requests
from bs4 import BeautifulSoup
import re
import json
import os
from packaging.version import parse, InvalidVersion
from urllib.parse import urlparse, unquote
import logging

# --- پیکربندی اولیه ---
URL_FILE = "urls_to_check.txt"  # فایلی که شامل URL ها برای بررسی است
TRACKING_FILE = "versions_tracker.json"  # فایلی برای ردیابی نسخه های دانلود شده
OUTPUT_JSON_FILE = "updates_found.json"  # خروجی برای GitHub Actions

# تنظیمات لاگ گیری
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# --- توابع کمکی ---

def load_tracker():
    """فایل ردیابی نسخه ها را بارگذاری می کند."""
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.warning(f"{TRACKING_FILE} خراب است یا فرمت JSON ندارد. با یک ردیاب خالی شروع می شود.")
            return {}
    return {}

def compare_versions(current_v_str, last_v_str):
    """نسخه فعلی را با آخرین نسخه شناخته شده مقایسه می کند."""
    logging.info(f"مقایسه نسخه ها: فعلی='{current_v_str}', قبلی='{last_v_str}'")
    try:
        if not current_v_str:
            logging.warning("نسخه فعلی نامعتبر است (خالی).")
            return False # نسخه فعلی نامعتبر

        # اگر نسخه قبلی وجود نداشته باشد، نسخه فعلی جدید محسوب می شود
        if not last_v_str or last_v_str == "0.0.0":
            logging.info("نسخه قبلی یافت نشد یا 0.0.0 بود، نسخه فعلی جدید است.")
            return True

        # نرمال سازی اولیه برای حذف بخش های غیر عددی احتمالی قبل از تجزیه اصلی
        # این بخش برای نسخه هایی مثل 1.2.3-beta یا 1.2.3a کاربرد دارد
        normalize_for_parse = lambda v: re.split(r'[^0-9.]', v, 1)[0]

        parsed_current = parse(normalize_for_parse(current_v_str))
        parsed_last = parse(normalize_for_parse(last_v_str))

        is_newer = parsed_current > parsed_last
        logging.info(f"نتیجه مقایسه (تجزیه شده): فعلی='{parsed_current}', قبلی='{parsed_last}', جدیدتر: {is_newer}")
        return is_newer
    except InvalidVersion as e:
        logging.warning(f"خطای InvalidVersion هنگام مقایسه: {e}. مقایسه به صورت رشته ای انجام می شود.")
        # بازگشت به مقایسه رشته ای در صورت عدم موفقیت تجزیه (کمتر قابل اعتماد)
        return current_v_str != last_v_str
    except Exception as e:
        logging.error(f"خطای پیش بینی نشده هنگام مقایسه نسخه ها: {e}. مقایسه به صورت رشته ای انجام می شود.")
        return current_v_str != last_v_str


def sanitize_text(text, for_filename=False):
    """متن را برای استفاده در شناسه های ردیابی یا نام فایل پاکسازی می کند."""
    text = text.strip().lower()
    # حذف (FarsRoid.com) و موارد مشابه
    text = re.sub(r'\((farsroid\.com|.*?)\)', '', text, flags=re.IGNORECASE)
    text = text.strip()
    if for_filename:
        # برای نام فایل، کاراکترهای غیرمجاز بیشتری را جایگزین می کنیم
        text = re.sub(r'[<>:"/\\|?*]', '_', text)
        text = re.sub(r'\s+', '_', text) # جایگزینی فاصله ها با آندرلاین
    else:
        # برای شناسه، فقط فاصله ها را با آندرلاین جایگزین می کنیم
        text = re.sub(r'\s+', '_', text)
    return text


def extract_app_name_from_page(soup, page_url):
    """تلاش برای استخراج نام برنامه از عنوان صفحه یا تگ H1."""
    # اولویت با تگ <title>
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.text.strip()
        # مثال فارسروید: "دانلود Advanced Download Manager Pro 14.0.38 برنامه مدیریت دانلود پیشرفته اندروید"
        # تلاش برای حذف "دانلود"، نسخه و توضیحات اضافی
        # این regex ممکن است نیاز به بهبود داشته باشد
        match = re.match(r'^(?:دانلود\s+)?(.+?)(?:\s+\d+\.\d+.*|\s+برنامه.*|\s+–\s+.*|$)', title_text, re.IGNORECASE)
        if match and match.group(1):
            app_name = match.group(1).strip()
            # حذف کلمات کلیدی اضافی مانند "اندروید" یا "آیفون" اگر در انتها باشند
            app_name = re.sub(r'\s+(?:اندروید|آیفون|ios|android)$', '', app_name, flags=re.IGNORECASE).strip()
            if app_name: return app_name

    # اگر از عنوان پیدا نشد، تگ H1 اصلی صفحه را امتحان کنید
    # این بخش نیاز به دقت بیشتری دارد چون H1 های زیادی ممکن است در صفحه باشند
    # سعی می کنیم H1 مربوط به عنوان اصلی پست را پیدا کنیم
    article_title_h1 = soup.find('h1', class_=re.compile(r'title|post-title|entry-title', re.IGNORECASE))
    if article_title_h1:
        return article_title_h1.text.strip()

    # به عنوان آخرین راه حل، از URL یک نام حدس بزنید
    parsed_url = urlparse(page_url)
    path_parts = [part for part in parsed_url.path.split('/') if part]
    if path_parts:
        guessed_name = path_parts[-1].replace('-', ' ').replace('_', ' ')
        # حذف پسوندهای رایج مانند .html, .php
        guessed_name = re.sub(r'\.(html|php|asp|aspx)$', '', guessed_name, flags=re.IGNORECASE)
        return guessed_name.title() # اولین حرف بزرگ

    return "UnknownApp"

# --- منطق خراش دادن خاص سایت فارسروید ---
def scrape_farsroid_page(page_url, soup, tracker_data):
    """اطلاعات دانلود را از یک صفحه فارسروید خراش می دهد."""
    updates_found_on_page = []
    # استخراج نام برنامه از صفحه (به روش کلی تر)
    page_app_name = extract_app_name_from_page(soup, page_url)
    logging.info(f"پردازش صفحه فارسروید: {page_url} (نام برنامه شناسایی شده: {page_app_name})")

    download_box = soup.find('section', class_='downloadbox')
    if not download_box:
        logging.warning(f"باکس دانلود در {page_url} پیدا نشد.")
        return updates_found_on_page

    download_links_ul = download_box.find('ul', class_='download-links')
    if not download_links_ul:
        logging.warning(f"لیست لینک های دانلود (ul) در {page_url} پیدا نشد.")
        return updates_found_on_page

    for li in download_links_ul.find_all('li', class_='download-link'):
        link_tag = li.find('a', class_='download-btn')
        if not link_tag:
            continue

        download_url = link_tag.get('href')
        link_text_span = link_tag.find('span', class_='txt')
        link_text = link_text_span.text.strip() if link_text_span else ""

        if not download_url or not link_text:
            logging.warning(f"لینک دانلود یا متن لینک در {page_url} ناقص است. رد شدن...")
            continue

        # استخراج نسخه از URL دانلود یا متن لینک (مشخصه فارسروید)
        # مثال URL: https://www.dl.farsroid.com/ap/ADM-Pro-14.0.38(FarsRoid.com).apk
        # مثال متن: دانلود فایل نصبی حرفه ای یونیورسال با لینک مستقیم - 29 مگابایت
        version_match_url = re.search(r'(\d+\.\d+(?:\.\d+){0,2}(?:[.-][a-zA-Z0-9]+)*)', download_url)
        version_match_text = re.search(r'(\d+\.\d+(?:\.\d+){0,2}(?:[.-][a-zA-Z0-9]+)*)', link_text) # گاهی نسخه در متن هم هست

        current_version = None
        if version_match_url:
            current_version = version_match_url.group(1)
        elif version_match_text: # اگر در URL نبود، متن را امتحان کن
            current_version = version_match_text.group(1)

        if not current_version:
            logging.warning(f"نسخه از URL '{download_url}' یا متن '{link_text}' استخراج نشد.")
            continue

        # استخراج نوع (Variant) از متن لینک یا URL
        variant = "Universal" # پیش فرض
        filename_in_url = unquote(urlparse(download_url).path.split('/')[-1])

        # الگوهای رایج برای نوع در فارسروید
        if re.search(r'Armeabi-v7a', filename_in_url + link_text, re.IGNORECASE):
            variant = "Armeabi-v7a"
        elif re.search(r'Arm64-v8a', filename_in_url + link_text, re.IGNORECASE):
            variant = "Arm64-v8a"
        elif re.search(r'x86_64', filename_in_url + link_text, re.IGNORECASE):
            variant = "x86_64"
        elif re.search(r'x86', filename_in_url + link_text, re.IGNORECASE): # باید بعد از x86_64 بیاید
            variant = "x86"
        elif re.search(r'Universal', filename_in_url + link_text, re.IGNORECASE):
             variant = "Universal"


        # نام برنامه: از نام استخراج شده از صفحه استفاده می کنیم
        # می توانیم آن را با بخشی از نام فایل ترکیب کنیم اگر لازم باشد
        app_name_for_file = sanitize_text(page_app_name, for_filename=True)
        variant_for_file = sanitize_text(variant, for_filename=True)

        # شناسه ردیابی منحصر به فرد
        tracking_id = f"{sanitize_text(page_app_name)}_{sanitize_text(variant)}".lower()
        last_known_version = tracker_data.get(tracking_id, "0.0.0")

        logging.info(f"  جزئیات یافت شده: برنامه='{page_app_name}', نسخه='{current_version}', نوع='{variant}', URL='{download_url}'")
        logging.info(f"    شناسه ردیابی='{tracking_id}', نسخه قبلی='{last_known_version}'")

        if compare_versions(current_version, last_known_version):
            logging.info(f"    => آپدیت جدید برای {tracking_id}: {current_version} (قبلی: {last_known_version})")
            
            # تولید نام فایل پیشنهادی برای دانلود
            # مثال: Advanced_Download_Manager_Pro_v14.0.38_Universal.apk
            suggested_filename = f"{app_name_for_file}_v{current_version}_{variant_for_file}.apk" # فرض بر APK بودن

            updates_found_on_page.append({
                "app_name": page_app_name,
                "version": current_version,
                "variant": variant,
                "download_url": download_url,
                "page_url": page_url, # برای ارجاع
                "tracking_id": tracking_id,
                "suggested_filename": suggested_filename,
                "current_version_for_tracking": current_version # برای به‌روزرسانی ردیاب توسط Workflow
            })
        else:
            logging.info(f"    => {tracking_id} به‌روز است (نسخه: {current_version}).")

    return updates_found_on_page

# --- منطق اصلی ---
def main():
    """نقطه ورود اصلی اسکریپت."""
    if not os.path.exists(URL_FILE):
        logging.error(f"فایل URL ها یافت نشد: {URL_FILE}")
        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f) # ایجاد خروجی JSON خالی برای نشان دادن عدم وجود آپدیت
        sys.exit(1) # خروج با خطا

    with open(URL_FILE, 'r', encoding='utf-8') as f:
        # خواندن URL ها، حذف خطوط خالی و خطوطی که با # شروع می شوند
        urls_to_process = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not urls_to_process:
        logging.info("فایل URL ها خالی است یا هیچ URL معتبری ندارد.")
        with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        return

    tracker_data = load_tracker()
    all_updates_found = [] # لیستی برای نگهداری تمام آپدیت های پیدا شده از همه URL ها

    for page_url in urls_to_process:
        logging.info(f"\n--- شروع بررسی URL: {page_url} ---")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8', # درخواست محتوای انگلیسی/فارسی
                'Referer': 'https://www.google.com/'
            }
            response = requests.get(page_url, headers=headers, timeout=45)
            response.raise_for_status() # بررسی خطاهای HTTP
            soup = BeautifulSoup(response.content, 'html.parser')

            # تشخیص نوع سایت بر اساس URL (در آینده می توان گسترش داد)
            if "farsroid.com" in page_url.lower():
                updates_on_page = scrape_farsroid_page(page_url, soup, tracker_data)
                all_updates_found.extend(updates_on_page)
            # elif "another-site.com" in page_url.lower():
            #     # updates_on_page = scrape_another_site_page(page_url, soup, tracker_data)
            #     # all_updates_found.extend(updates_on_page)
            #     logging.warning(f"خراش دهنده برای {page_url} هنوز پیاده سازی نشده است.")
            else:
                logging.warning(f"هیچ خراش دهنده مشخصی برای URL پیدا نشد: {page_url}. رد شدن...")

        except requests.exceptions.Timeout:
            logging.error(f"خطای Timeout هنگام دریافت {page_url}.")
        except requests.exceptions.RequestException as e:
            logging.error(f"خطا در دریافت {page_url}: {e}")
        except Exception as e:
            logging.error(f"خطای پیش بینی نشده هنگام پردازش {page_url}: {e}", exc_info=True)
        logging.info(f"--- پایان بررسی URL: {page_url} ---")


    # نوشتن نتایج در فایل خروجی JSON
    with open(OUTPUT_JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_updates_found, f, ensure_ascii=False, indent=2)

    if all_updates_found:
        logging.info(f"\nخلاصه: {len(all_updates_found)} آپدیت پیدا شد. جزئیات در {OUTPUT_JSON_FILE}")
    else:
        logging.info(f"\nخلاصه: هیچ آپدیت جدیدی پیدا نشد. فایل {OUTPUT_JSON_FILE} خالی است یا شامل لیست خالی [].")

if __name__ == "__main__":
    main()
