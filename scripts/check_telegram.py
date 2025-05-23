import requests
from bs4 import BeautifulSoup
import re
import sys
import os
from urllib.parse import urljoin
from packaging.version import parse, InvalidVersion

# --- توابع کمکی ---

def get_output_path():
    """مسیر فایل خروجی GitHub Actions را دریافت می‌کند."""
    return os.environ.get('GITHUB_OUTPUT', 'local_output.txt')

def set_github_output(name, value):
    """یک متغیر خروجی برای GitHub Actions تنظیم می‌کند."""
    output_path = get_output_path()
    print(f"[LOG] Setting GitHub Output: {name}={value}")
    with open(output_path, "a") as f:
        f.write(f"{name}={value}\n")

def get_last_known_version(platform):
    """آخرین نسخه شناخته شده را از فایل می‌خواند."""
    filename = f"last_known_telegram_{platform}_version.txt"
    print(f"[LOG] Attempting to read last known version from: {filename}")
    try:
        with open(filename, "r") as f:
            version = f.read().strip()
            if version:
                print(f"[LOG] Found last known version: {version}")
                return version
            else:
                print(f"[LOG] Version file '{filename}' is empty. Assuming '0.0.0'.")
                return "0.0.0"
    except FileNotFoundError:
        print(f"[LOG] Version file '{filename}' not found. Assuming '0.0.0'.")
        return "0.0.0"

def compare_versions(current_version, last_known):
    """نسخه‌ها را با استفاده از کتابخانه packaging مقایسه می‌کند."""
    print(f"[LOG] Comparing versions: Current='{current_version}', LastKnown='{last_known}'")
    try:
        is_newer = parse(current_version) > parse(last_known)
        print(f"[LOG] Comparison result (using packaging): {is_newer}")
        return is_newer
    except InvalidVersion:
        print(f"[WARN] Could not parse versions using 'packaging'. Comparing as strings.")
        is_newer = current_version != last_known
        print(f"[LOG] Comparison result (using strings): {is_newer}")
        return is_newer

# --- توابع اصلی بررسی ---

def check_desktop_windows():
    """نسخه دسکتاپ ویندوز را بررسی می‌کند."""
    print("\n" + "="*50)
    print("[INFO] Starting check for Telegram Desktop (Windows)...")
    print("="*50)
    base_url = "https://desktop.telegram.org/"
    set_github_output("new_version_available", "false") # پیش‌فرض: نسخه جدیدی نیست

    try:
        print(f"[LOG] Fetching URL: {base_url}")
        response = requests.get(base_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"[LOG] Response Status Code: {response.status_code}")
        response.raise_for_status() # اگر خطا بود، متوقف می‌شود
        soup = BeautifulSoup(response.text, 'html.parser')
        print("[LOG] HTML content fetched and parsed successfully.")

        download_link_tag = None
        
        # === استراتژی ۱: پیدا کردن لینک با نسخه در href ===
        print("[LOG] Strategy 1: Searching for link with version in href...")
        pattern1 = re.compile(r'(tsetup|tsetup-x64)[.-]v?(\d+\.\d+\.\d+)\.exe', re.IGNORECASE)
        download_link_tag = soup.find('a', href=pattern1)
        if download_link_tag:
            print(f"[LOG] Strategy 1 Found: {download_link_tag.get('href')}")
        else:
            print("[LOG] Strategy 1: Not found.")

        # === استراتژی ۲: پیدا کردن دکمه دانلود ویندوز ===
        if not download_link_tag:
            print("[LOG] Strategy 2: Searching for 'windows' + 'exe' link...")
            download_link_tag = soup.find(lambda tag: tag.name == 'a' and ('windows' in tag.text.lower() or 'windows' in tag.get('href', '').lower()) and 'exe' in tag.get('href', '').lower())
            if download_link_tag:
                print(f"[LOG] Strategy 2 Found: {download_link_tag.get('href')}")
            else:
                print("[LOG] Strategy 2: Not found.")

        # === استراتژی ۳: پیدا کردن هر لینکی که شبیه دانلود ویندوز باشد ===
        if not download_link_tag:
            print("[LOG] Strategy 3: Searching for 'tsetup-x64.*.exe' link...")
            download_link_tag = soup.find('a', href=re.compile(r'tsetup-x64.*\.exe', re.IGNORECASE))
            if download_link_tag:
                print(f"[LOG] Strategy 3 Found: {download_link_tag.get('href')}")
            else:
                print("[LOG] Strategy 3: Not found.")

        # --- پردازش لینک پیدا شده ---
        if download_link_tag and download_link_tag.get('href'):
            href = download_link_tag['href']
            print(f"[LOG] Found a potential link tag. Href: '{href}'")
            download_url = urljoin(base_url, href)
            print(f"[LOG] Constructed Download URL: {download_url}")

            # === استخراج نسخه ===
            print("[LOG] Attempting to extract version number...")
            version_match = re.search(r'(\d+\.\d+\.\d+)', download_url) or \
                            re.search(r'(\d+\.\d+\.\d+)', download_link_tag.text)
            
            if not version_match and download_link_tag.parent:
                parent_text = download_link_tag.parent.get_text()
                print(f"[LOG] Trying parent text for version: '{parent_text[:100]}...'")
                version_match = re.search(r'Version\s*(\d+\.\d+\.\d+)', parent_text)

            if version_match:
                current_version = version_match.group(1)
                print(f"[SUCCESS] Found Windows version: {current_version}")

                last_known = get_last_known_version("desktop")

                if compare_versions(current_version, last_known):
                    print("[INFO] New Windows version found! Setting outputs.")
                    set_github_output("new_version_available", "true")
                    set_github_output("version", current_version)
                    set_github_output("download_url", download_url)
                else:
                    print("[INFO] Found version is not newer than the last known version.")
            else:
                print("[ERROR] Could not extract Windows version number from any source.")
        else:
            print("[ERROR] Could not find any suitable download link for Telegram Desktop (Windows x64).")
            # print(f"[DEBUG] Soup (first 1000 chars):\n{soup.prettify()[:1000]}") # برای دیباگ شدید (از کامنت خارج کنید)

    except requests.exceptions.RequestException as e:
        print(f"[FATAL_ERROR] Error fetching Telegram Desktop page: {e}")
    except Exception as e:
        print(f"[FATAL_ERROR] An unexpected error occurred during Windows check: {e}")

    print("[INFO] Finished check for Telegram Desktop (Windows).")


def check_android():
    """نسخه اندروید را بررسی می‌کند."""
    print("\n" + "="*50)
    print("[INFO] Starting check for Telegram Android...")
    print("="*50)
    base_url = "https://telegram.org/"
    android_url = urljoin(base_url, "/android")
    apk_url_pattern = r"/dl/android/apk"
    version_pattern = r'(\d+\.\d+(\.\d+)*)'
    set_github_output("new_version_available", "false") # پیش‌فرض: نسخه جدیدی نیست

    try:
        print(f"[LOG] Fetching URL: {android_url}")
        response = requests.get(android_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"[LOG] Response Status Code: {response.status_code}")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        print("[LOG] HTML content fetched and parsed successfully.")

        apk_link_tag = None
        version = None
        apk_download_url = None

        print("[LOG] Searching for Android APK link...")
        # تلاش برای پیدا کردن لینکی با الگوی APK
        apk_link_tag = soup.find('a', href=re.compile(apk_url_pattern, re.IGNORECASE))
        if apk_link_tag:
            print(f"[LOG] Found link with pattern: {apk_link_tag.get('href')}")
        else:
            print("[LOG] Link with pattern not found. Trying text search...")
            # تلاش برای پیدا کردن لینکی با متن مشخص
            apk_link_tag = soup.find('a', string=re.compile(r'Telegram\s+for\s+Android\s+APK', re.IGNORECASE))
            if apk_link_tag:
                 print(f"[LOG] Found link with text: {apk_link_tag.get('href')}")
            else:
                 print("[LOG] Link with text not found.")


        if apk_link_tag and apk_link_tag.get('href'):
            href = apk_link_tag['href']
            print(f"[LOG] Found a potential Android link tag. Href: '{href}'")
            apk_download_url = urljoin(base_url, href)
            print(f"[LOG] Constructed Download URL: {apk_download_url}")

            # تلاش برای استخراج نسخه از متن یا لینک
            print("[LOG] Attempting to extract version number...")
            version_match = re.search(version_pattern, apk_link_tag.text) or \
                            re.search(version_pattern, apk_download_url)
            
            if not version_match and apk_link_tag.parent:
                parent_text = apk_link_tag.parent.get_text()
                print(f"[LOG] Trying parent text for version: '{parent_text[:100]}...'")
                version_match = re.search(version_pattern, parent_text)

            if version_match:
                version = version_match.group(1)
                print(f"[SUCCESS] Found Android version: {version}")

        # --- پردازش نسخه پیدا شده ---
        if apk_download_url and version:
            last_known = get_last_known_version("android")
            if compare_versions(version, last_known):
                print("[INFO] New Android version found! Setting outputs.")
                set_github_output("new_version_available", "true")
                set_github_output("version", version)
                set_github_output("download_url", apk_download_url)
            else:
                print("[INFO] Found version is not newer than the last known version.")
        else:
            if not apk_download_url:
                print("[ERROR] Could not find any suitable direct download link for Telegram Android APK.")
            if not version:
                print("[ERROR] Could not extract Android version number.")
            # print(f"[DEBUG] Soup (first 1000 chars):\n{soup.prettify()[:1000]}") # برای دیباگ شدید (از کامنت خارج کنید)

    except requests.exceptions.RequestException as e:
        print(f"[FATAL_ERROR] Error fetching Telegram Android page: {e}")
    except Exception as e:
        print(f"[FATAL_ERROR] An unexpected error occurred during Android check: {e}")

    print("[INFO] Finished check for Telegram Android.")

# --- اجرای اسکریپت ---

if __name__ == "__main__":
    print("[INIT] Starting Telegram version check script...")
    output_file = get_output_path()
    if os.path.exists(output_file) and output_file == 'local_output.txt':
        print("[INIT] Removing old local output file.")
        os.remove(output_file)

    if len(sys.argv) > 1:
        platform_to_check = sys.argv[1]
        print(f"[INIT] Platform specified: {platform_to_check}")
        if platform_to_check == "windows":
            check_desktop_windows()
        elif platform_to_check == "android":
            check_android()
        else:
            print(f"[FATAL_ERROR] Unknown platform: {platform_to_check}")
            set_github_output("new_version_available", "false") # اطمینان از false بودن در صورت خطای پلتفرم
    else:
        print("[INIT] No platform specified. Checking BOTH platforms.")
        check_desktop_windows()
        check_android()

    print("[INIT] Script finished.")