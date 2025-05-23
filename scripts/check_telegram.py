import requests
from bs4 import BeautifulSoup
import re
import sys
import os
from urllib.parse import urljoin # برای ساخت URL
from packaging.version import parse, InvalidVersion # برای مقایسه نسخه

def get_output_path():
    """مسیر فایل خروجی GitHub Actions را دریافت می‌کند."""
    return os.environ.get('GITHUB_OUTPUT', 'local_output.txt')

def set_github_output(name, value):
    """یک متغیر خروجی برای GitHub Actions تنظیم می‌کند."""
    output_path = get_output_path()
    print(f"Setting output: {name}={value}") # برای دیباگ
    with open(output_path, "a") as f:
        f.write(f"{name}={value}\n")

def get_last_known_version(platform):
    """آخرین نسخه شناخته شده را از فایل می‌خواند."""
    filename = f"last_known_telegram_{platform}_version.txt"
    try:
        with open(filename, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Version file '{filename}' not found. Assuming '0.0.0'.")
        return "0.0.0" # پیش‌فرض به یک نسخه خیلی قدیمی

def compare_versions(current_version, last_known):
    """نسخه‌ها را با استفاده از کتابخانه packaging مقایسه می‌کند."""
    try:
        return parse(current_version) > parse(last_known)
    except InvalidVersion:
        print(f"Warning: Could not parse versions '{current_version}' or '{last_known}'. Comparing as strings.")
        return current_version != last_known # بازگشت به مقایسه رشته‌ای در صورت خطا

def check_desktop_windows():
    """نسخه دسکتاپ ویندوز را بررسی می‌کند."""
    base_url = "https://desktop.telegram.org/"
    try:
        print(f"Fetching URL: {base_url}")
        response = requests.get(base_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # === استراتژی‌ها برای پیدا کردن لینک و نسخه (همچنان شکننده) ===
        # تلاش برای پیدا کردن لینک با نسخه در href
        download_link_tag = soup.find('a', href=re.compile(r'(tsetup|tsetup-x64)[.-]v?(\d+\.\d+\.\d+)\.exe', re.IGNORECASE))

        # اگر پیدا نشد، تلاش برای پیدا کردن دکمه دانلود ویندوز
        if not download_link_tag:
            win_section = soup.find(lambda tag: tag.name == 'a' and ('windows' in tag.text.lower() or 'windows' in tag.get('href', '').lower()) and 'exe' in tag.get('href', '').lower())
            if win_section:
                 download_link_tag = win_section
            else: # آخرین تلاش: پیدا کردن هر لینکی که شبیه لینک دانلود ویندوز باشد
                download_link_tag = soup.find('a', href=re.compile(r'tsetup-x64.*\.exe', re.IGNORECASE))


        if download_link_tag and download_link_tag.get('href'):
            href = download_link_tag['href']
            download_url = urljoin(base_url, href) # استفاده از urljoin

            # تلاش برای استخراج نسخه از URL یا متن
            version_match = re.search(r'(\d+\.\d+\.\d+)', download_url) or \
                            re.search(r'(\d+\.\d+\.\d+)', download_link_tag.text) or \
                            re.search(r'Version\s*(\d+\.\d+\.\d+)', download_link_tag.parent.get_text())

            if version_match:
                current_version = version_match.group(1)
                print(f"Found Windows version: {current_version}, URL: {download_url}")
                last_known = get_last_known_version("desktop")
                print(f"Last known Windows version: {last_known}")

                if compare_versions(current_version, last_known):
                    set_github_output("new_version_available", "true")
                    set_github_output("version", current_version)
                    set_github_output("download_url", download_url)
                    print(f"New Windows version {current_version} found.")
                    return
                else:
                    print("No new Windows version found.")
            else:
                print("Could not extract Windows version number.")
        else:
            print("Could not find a suitable download link for Telegram Desktop (Windows x64). Website structure might have changed.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching Telegram Desktop page: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Windows check: {e}")

    set_github_output("new_version_available", "false")

def check_android():
    """نسخه اندروید را بررسی می‌کند."""
    base_url = "https://telegram.org/"
    android_url = urljoin(base_url, "/android")
    apk_url_pattern = r"/dl/android/apk" # الگوی اصلی لینک APK
    version_pattern = r'(\d+\.\d+(\.\d+)*)' # الگوی نسخه

    try:
        print(f"Fetching URL: {android_url}")
        response = requests.get(android_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        apk_download_url = None
        version = None

        # تلاش برای پیدا کردن لینکی که به صفحه دانلود APK می‌رود یا مستقیماً APK است
        apk_link_tag = soup.find('a', href=re.compile(apk_url_pattern, re.IGNORECASE))

        if apk_link_tag and apk_link_tag.get('href'):
            # اگر لینک پیدا شد، باید به آن صفحه برویم یا اگر مستقیم است، آن را بگیریم
            # در بسیاری از موارد، لینک اصلی در صفحه اصلی اندروید نیست،
            # بلکه در بخش توضیحات یا لینکی مثل "Download Telegram APK" است.
            # بیایید متن لینک را بررسی کنیم.
            apk_text_link = soup.find('a', string=re.compile(r'Telegram\s+for\s+Android\s+APK', re.IGNORECASE))
            if not apk_link_tag and apk_text_link:
                 apk_link_tag = apk_text_link

            # اگر هنوز پیدا نشده، به دنبال لینکی بگردیم که نسخه در آن باشد
            if not apk_link_tag:
                apk_link_tag = soup.find('a', href=re.compile(apk_url_pattern, re.IGNORECASE), string=re.compile(version_pattern))

            if apk_link_tag:
                 apk_download_url = urljoin(base_url, apk_link_tag['href'])
                 # تلاش برای استخراج نسخه از متن یا لینک
                 version_match = re.search(version_pattern, apk_link_tag.text) or \
                                 re.search(version_pattern, apk_download_url)

                 if version_match:
                     version = version_match.group(1)

        # اگر هیچ لینکی پیدا نشد، این روش شکست خورده است
        if apk_download_url and version:
            # مهم: لینک پیدا شده ممکن است مستقیم نباشد و نیاز به follow داشته باشد.
            # فعلاً فرض می‌کنیم مستقیم است یا curl -L آن را دنبال می‌کند.
            # برای اطمینان، می‌توانیم لینک را با requests دنبال کنیم تا به URL نهایی برسیم.
            # فعلا با همین URL ادامه می‌دهیم.
            print(f"Found Android version: {version}, URL: {apk_download_url}")
            last_known = get_last_known_version("android")
            print(f"Last known Android version: {last_known}")

            if compare_versions(version, last_known):
                set_github_output("new_version_available", "true")
                set_github_output("version", version)
                set_github_output("download_url", apk_download_url)
                print(f"New Android version {version} found.")
                return
            else:
                print("No new Android version found.")
        else:
            print("Could not find a suitable direct download link or version for Telegram Android APK. Website structure might have changed.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching Telegram Android page: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Android check: {e}")

    set_github_output("new_version_available", "false")


if __name__ == "__main__":
    # اگر فایل خروجی محلی وجود دارد، آن را پاک می‌کنیم تا هر اجرا جدید باشد
    if os.path.exists('local_output.txt'):
        os.remove('local_output.txt')

    if len(sys.argv) > 1:
        platform_to_check = sys.argv[1]
        if platform_to_check == "windows":
            check_desktop_windows()
        elif platform_to_check == "android":
            check_android()
        else:
            print(f"Unknown platform: {platform_to_check}")
            set_github_output("new_version_available", "false")
    else:
        print("No platform specified (windows or android). Checking both.")
        check_desktop_windows()
        check_android() # یا می‌توانید خطا بدهید یا هر دو را چک کنید