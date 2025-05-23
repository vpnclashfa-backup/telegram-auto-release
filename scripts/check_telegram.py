import requests
from bs4 import BeautifulSoup
import re
import sys
import os
from urllib.parse import urljoin
from packaging.version import parse, InvalidVersion

# --- توابع کمکی (بدون تغییر) ---

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

# --- تابع بررسی ویندوز (تایید شده) ---

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

        initial_href = soup.find('a', href="//telegram.org/dl/desktop/win64")
        if initial_href: initial_href = initial_href.get('href')

        if not initial_href:
            print("[LOG] Win_Strategy_1: Not found. Trying Win_Strategy_2...")
            all_btns = soup.find_all('a', class_='td_download_btn')
            for btn in all_btns:
                href = btn.get('href', '')
                if 'win64' in href and 'portable' not in href:
                    initial_href = href
                    print(f"[LOG] Win_Strategy_2 Found: {initial_href}")
                    break
            if not initial_href: print("[LOG] Win_Strategy_2: Not found.")
        else:
             print(f"[LOG] Win_Strategy_1 Found: {initial_href}")


        if initial_href:
            initial_url = "https:" + initial_href
            print(f"[LOG] Found Initial Windows URL: {initial_url}")
            print("[LOG] Following Windows redirects...")

            try:
                redirect_response = requests.head(initial_url, allow_redirects=True, timeout=45, headers={'User-Agent': 'Mozilla/5.0'})
                redirect_response.raise_for_status()
                final_url = redirect_response.url
                print(f"[LOG] Final Windows URL: {final_url}")

                version_match = re.search(r'[.-](\d+\.\d+\.\d+)\.exe', final_url, re.IGNORECASE)

                if version_match:
                    current_version = version_match.group(1)
                    print(f"[SUCCESS] Found Windows version: {current_version}")
                    last_known = get_last_known_version("desktop")
                    if compare_versions(current_version, last_known):
                        print("[INFO] New Windows version found! Setting outputs.")
                        set_github_output("new_version_available", "true")
                        set_github_output("version", current_version)
                        set_github_output("download_url", final_url)
                    else:
                        print("[INFO] Windows version is not newer.")
                else:
                    print(f"[ERROR] Could not extract Windows version from final URL: {final_url}")

            except requests.exceptions.RequestException as e:
                print(f"[FATAL_ERROR] Error following Windows redirects: {e}")

        else:
            print("[ERROR] Could not find initial Windows download link.")

    except requests.exceptions.RequestException as e:
        print(f"[FATAL_ERROR] Error fetching Windows page: {e}")
    except Exception as e:
        print(f"[FATAL_ERROR] An unexpected error occurred during Windows check: {e}")

    print("[INFO] Finished check for Telegram Desktop (Windows).")


# --- تابع بررسی اندروید (بازنویسی شده) ---

def check_android():
    """نسخه اندروید را با دنبال کردن ریدایرکت بررسی می‌کند."""
    print("\n" + "="*50)
    print("[INFO] Starting check for Telegram Android - New Method...")
    print("="*50)
    base_url = "https://telegram.org/"
    # این آدرس صفحه‌ای است که کدش را فرستادید (یا نزدیک به آن)
    android_page_url = urljoin(base_url, "/android") 
    set_github_output("new_version_available", "false") # پیش‌فرض

    try:
        print(f"[LOG] Fetching Android page URL: {android_page_url}")
        response = requests.get(android_page_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"[LOG] Response Status Code: {response.status_code}")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        print("[LOG] Android HTML content fetched and parsed successfully.")

        initial_href = None
        # جستجوی لینک با href="/dl/android/apk"
        apk_link_tag = soup.find('a', href="/dl/android/apk")

        if apk_link_tag:
            initial_href = apk_link_tag.get('href')
            print(f"[LOG] Found initial APK link href: {initial_href}")
        else:
            print("[ERROR] Could not find the '/dl/android/apk' link on the page.")
            print("[INFO] Finished check for Telegram Android (Link not found).")
            return # نمی‌توانیم ادامه دهیم

        # --- دنبال کردن ریدایرکت ---
        initial_url = urljoin(base_url, initial_href) # urljoin برای ساخت URL امن
        print(f"[LOG] Found Initial Android URL: {initial_url}")
        print("[LOG] Following Android redirects...")

        try:
            redirect_response = requests.head(initial_url, allow_redirects=True, timeout=45, headers={'User-Agent': 'Mozilla/5.0'})
            redirect_response.raise_for_status()
            final_url = redirect_response.url
            print(f"[LOG] Final Android URL: {final_url}")

            # === استخراج نسخه از URL نهایی ===
            # الگوهای ممکن: Telegram-X.Y.Z.apk, X.Y.Z/Telegram.apk ...
            version_match = re.search(r'[/-](\d+\.\d+(?:\.\d+)?(?:\.\d+)?)[./]', final_url, re.IGNORECASE)
            if not version_match:
                 version_match = re.search(r'[.-](\d+\.\d+(?:\.\d+)?(?:\.\d+)?)\.apk', final_url, re.IGNORECASE)

            if version_match:
                current_version = version_match.group(1)
                print(f"[SUCCESS] Found Android version from final URL: {current_version}")
                last_known = get_last_known_version("android")

                if compare_versions(current_version, last_known):
                    print("[INFO] New Android version found! Setting outputs.")
                    set_github_output("new_version_available", "true")
                    set_github_output("version", current_version)
                    set_github_output("download_url", final_url)
                else:
                    print("[INFO] Android version is not newer.")
            else:
                print(f"[ERROR] Could not extract Android version from final URL: {final_url}. Pattern might need update.")

        except requests.exceptions.RequestException as e:
            print(f"[FATAL_ERROR] Error following Android redirects: {e}")

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
            # Ensure outputs are not set for unknown platforms
            set_github_output("new_version_available", "false")
    else:
        print("[INIT] No platform specified. Checking BOTH platforms.")
        check_desktop_windows()
        check_android()

    print("[INIT] Script finished.")