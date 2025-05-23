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

# --- تابع بررسی ویندوز (بازنویسی شده) ---

def check_desktop_windows():
    """نسخه دسکتاپ ویندوز را بر اساس HTML جدید و با دنبال کردن ریدایرکت بررسی می‌کند."""
    print("\n" + "="*50)
    print("[INFO] Starting check for Telegram Desktop (Windows) - New Method...")
    print("="*50)
    base_url = "https://desktop.telegram.org/"
    set_github_output("new_version_available", "false") # پیش‌فرض

    try:
        print(f"[LOG] Fetching URL: {base_url}")
        response = requests.get(base_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"[LOG] Response Status Code: {response.status_code}")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        print("[LOG] HTML content fetched and parsed successfully.")

        download_link_tag = None
        initial_href = None

        # === استراتژی ۱: جستجوی لینک با href دقیق ===
        print("[LOG] Strategy 1: Searching for href='//telegram.org/dl/desktop/win64'...")
        download_link_tag = soup.find('a', href="//telegram.org/dl/desktop/win64")
        if download_link_tag:
            initial_href = download_link_tag.get('href')
            print(f"[LOG] Strategy 1 Found: {initial_href}")
        else:
            print("[LOG] Strategy 1: Not found.")

        # === استراتژی ۲: جستجوی کلاس td_download_btn و فیلتر کردن href ===
        if not download_link_tag:
            print("[LOG] Strategy 2: Searching for 'td_download_btn' and filtering 'win64'...")
            all_btns = soup.find_all('a', class_='td_download_btn')
            for btn in all_btns:
                href = btn.get('href', '')
                if 'win64' in href and 'portable' not in href:
                    download_link_tag = btn
                    initial_href = href
                    print(f"[LOG] Strategy 2 Found: {initial_href}")
                    break
            if not download_link_tag:
                 print("[LOG] Strategy 2: Not found.")

        # --- پردازش لینک پیدا شده و دنبال کردن ریدایرکت ---
        if initial_href:
            initial_url = "https:" + initial_href
            print(f"[LOG] Found Initial Download URL: {initial_url}")
            print("[LOG] Following redirects to find final URL and version...")

            try:
                redirect_response = requests.head(initial_url, allow_redirects=True, timeout=45, headers={'User-Agent': 'Mozilla/5.0'})
                redirect_response.raise_for_status()
                final_url = redirect_response.url
                print(f"[LOG] Final Redirected URL: {final_url}")

                # === استخراج نسخه از URL نهایی ===
                version_match = re.search(r'[.-](\d+\.\d+\.\d+)\.exe', final_url, re.IGNORECASE)

                if version_match:
                    current_version = version_match.group(1)
                    actual_download_url = final_url
                    print(f"[SUCCESS] Found Windows version from final URL: {current_version}")

                    last_known = get_last_known_version("desktop")

                    if compare_versions(current_version, last_known):
                        print("[INFO] New Windows version found! Setting outputs.")
                        set_github_output("new_version_available", "true")
                        set_github_output("version", current_version)
                        set_github_output("download_url", actual_download_url)
                    else:
                        print("[INFO] Found version is not newer than the last known version.")
                else:
                    print(f"[ERROR] Could not extract version from final URL: {final_url}. Pattern might need update.")

            except requests.exceptions.RequestException as e:
                print(f"[FATAL_ERROR] Error following redirects or fetching final URL: {e}")

        else:
            print("[ERROR] Could not find the initial download link in the HTML.")

    except requests.exceptions.RequestException as e:
        print(f"[FATAL_ERROR] Error fetching Telegram Desktop page: {e}")
    except Exception as e:
        print(f"[FATAL_ERROR] An unexpected error occurred during Windows check: {e}")

    print("[INFO] Finished check for Telegram Desktop (Windows).")


# --- تابع بررسی اندروید (با لاگ‌گیری بهبود یافته) ---

def check_android():
    """نسخه اندروید را بررسی می‌کند."""
    print("\n" + "="*50)
    print("[INFO] Starting check for Telegram Android...")
    print("="*50)
    base_url = "https://telegram.org/"
    android_url = urljoin(base_url, "/android")
    apk_url_pattern = r"/dl/android/apk"
    version_pattern = r'(\d+\.\d+(\.\d+)*)'
    set_github_output("new_version_available", "false") # پیش‌فرض

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
        apk_link_tag = soup.find('a', href=re.compile(apk_url_pattern, re.IGNORECASE))
        if apk_link_tag:
            print(f"[LOG] Found link with pattern: {apk_link_tag.get('href')}")
        else:
            print("[LOG] Link with pattern not found. Trying text search...")
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

        if apk_download_url and version:
            # اینجا هم می‌توانیم ریدایرکت را دنبال کنیم تا URL نهایی APK را بگیریم
            # اما فعلاً با همین URL ادامه می‌دهیم چون پیدا کردن نسخه اندروید چالش اصلی نیست
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
            check_android() # توجه: این بخش ممکن است همچنان شکننده باشد
        else:
            print(f"[FATAL_ERROR] Unknown platform: {platform_to_check}")
            set_github_output("new_version_available", "false")
    else:
        print("[INIT] No platform specified. Checking BOTH platforms.")
        check_desktop_windows()
        check_android()

    print("[INIT] Script finished.")