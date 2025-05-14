import requests
from bs4 import BeautifulSoup
import re
import sys
import os

def get_output_path():
    return os.environ.get('GITHUB_OUTPUT', 'local_output.txt')

def set_github_output(name, value):
    output_path = get_output_path()
    # print(f"Setting output: {name}={value} to {output_path}") # For local debugging
    with open(output_path, "a") as f:
        f.write(f"{name}={value}\n")

def get_last_known_version(platform):
    filename = f"last_known_telegram_{platform}_version.txt"
    try:
        with open(filename, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0" # Default to a very old version

def check_desktop_windows():
    url = "https://desktop.telegram.org/"
    try:
        print(f"Fetching URL: {url}")
        response = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # === Strategy 1: Find a direct download link with version in href ===
        # Example: <a href=".../tsetup.x64.4.8.1.exe">
        download_link_tag = soup.find('a', href=re.compile(r'tsetup\.x64\.(\d+\.\d+\.\d+)\.exe', re.IGNORECASE))
        if not download_link_tag:
            # === Strategy 2: Find a prominent download button/link for Windows and extract version from text or nearby elements ===
            # This is highly dependent on website structure
            # Example: Looking for "Download Telegram for Windows x64" then trying to find version nearby
            win_section = soup.find('div', class_=re.compile(r'td_download_box.*win|td_download_btn.*win', re.IGNORECASE)) # Common class patterns
            if win_section:
                 download_link_tag = win_section.find('a', href=re.compile(r'win64|exe', re.IGNORECASE))
                 if not download_link_tag: # Fallback if no specific link found in section
                     download_link_tag = soup.find('a', href=re.compile(r'tsetup-x64.*\.exe', re.IGNORECASE))


        if download_link_tag and download_link_tag.get('href'):
            href = download_link_tag['href']
            # Construct full URL if relative
            if href.startswith('/'):
                download_url = "https://desktop.telegram.org" + href
            elif not href.startswith('http'):
                 download_url = "https://desktop.telegram.org/" + href # Assuming relative to base
            else:
                download_url = href

            # Try to extract version from URL
            version_match = re.search(r'(\d+\.\d+\.\d+)', download_url)
            if not version_match and download_link_tag.text: # Try from link text
                version_match = re.search(r'(\d+\.\d+\.\d+)', download_link_tag.text)
            if not version_match : # Try from nearby text if main link tag doesn't have it.
                 parent = download_link_tag.parent
                 if parent:
                    version_match = re.search(r'Version (\d+\.\d+\.\d+)', parent.get_text())


            if version_match:
                current_version = version_match.group(1)
                print(f"Found Windows version: {current_version}, URL: {download_url}")

                last_known = get_last_known_version("desktop")
                print(f"Last known Windows version: {last_known}")

                # Simple version comparison (can be improved with packaging.version)
                if current_version != last_known: # A more robust check would parse versions
                    set_github_output("new_version_available", "true")
                    set_github_output("version", current_version)
                    set_github_output("download_url", download_url)
                    print(f"New Windows version {current_version} found.")
                    return
                else:
                    print("No new Windows version found.")
            else:
                print("Could not extract Windows version number from link or text.")
        else:
            print("Could not find a suitable download link for Telegram Desktop (Windows x64). Website structure might have changed.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching Telegram Desktop page: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Windows check: {e}")

    set_github_output("new_version_available", "false")


def check_android():
    # Telegram's official site usually links to Google Play.
    # A common, often updated direct source for APKs is the official Telegram channel,
    # or their dedicated APK download page if available and stable.
    # Let's try to find a direct APK download page or rely on a pattern often seen.
    # Alternative: https://telegram.org/dl/android/apk (sometimes this is a direct link)

    # Strategy 1: Telegram's APK download page (if it exists and is consistent)
    # url = "https://telegram.org/android/apk" # This URL might not always be up-to-date or may redirect
    # Strategy 2: Telegram's general Android page and look for APK links
    url = "https://telegram.org/android"
    direct_apk_url_pattern = r"https?://telegram.org/dl/android/apk[^\s'\"]*|https?://t.me/TAndroidAPK[^\s'\"]*" # General patterns
    version_pattern_in_url = r'(\d+\.\d+(\.\d+)*(-\d+)*)' # More flexible version matching

    try:
        print(f"Fetching URL: {url}")
        response = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        apk_download_url = None
        version = None

        # Try to find a link matching the direct APK URL pattern
        apk_link_tag = soup.find('a', href=re.compile(direct_apk_url_pattern, re.IGNORECASE))

        if apk_link_tag and apk_link_tag.get('href'):
            apk_download_url = apk_link_tag['href']
            # Try to extract version from the URL itself
            version_match = re.search(version_pattern_in_url, apk_download_url)
            if version_match:
                version = version_match.group(1)
            elif apk_link_tag.text: # Try from link text
                version_match = re.search(version_pattern_in_url, apk_link_tag.text)
                if version_match:
                    version = version_match.group(1)
            # If version not in URL or link text, try nearby elements (more fragile)
            if not version:
                parent_text = apk_link_tag.parent.get_text(separator=' ', strip=True) if apk_link_tag.parent else ""
                version_match = re.search(r'Version\s*(\d+\.\d+(\.\d+)*)', parent_text, re.IGNORECASE)
                if version_match:
                    version = version_match.group(1)


        # Fallback: If no direct link, sometimes the version is mentioned near a Play Store link.
        # This is less ideal as we need a direct APK link.
        # For now, we focus on direct APK links.
        # If direct download is not found, a more complex strategy would be needed,
        # possibly checking official Telegram channels or reputable APK sites (with caution).

        if apk_download_url and version:
            print(f"Found Android version: {version}, URL: {apk_download_url}")
            last_known = get_last_known_version("android")
            print(f"Last known Android version: {last_known}")

            if version != last_known: # A more robust check would parse versions
                set_github_output("new_version_available", "true")
                set_github_output("version", version)
                set_github_output("download_url", apk_download_url)
                print(f"New Android version {version} found.")
                return
            else:
                print("No new Android version found.")
        else:
            if not apk_download_url:
                print("Could not find a suitable direct download link for Telegram Android APK.")
            if not version:
                print("Could not extract Android version number.")
            print("Website structure for Android APK might have changed or direct link not easily identifiable.")


    except requests.exceptions.RequestException as e:
        print(f"Error fetching Telegram Android page: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Android check: {e}")

    set_github_output("new_version_available", "false")


if __name__ == "__main__":
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
        print("No platform specified (windows or android).")
        set_github_output("new_version_available", "false")
