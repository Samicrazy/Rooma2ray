import os
import re
import base64
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

# ==========================================
# تنظیمات کانال‌ها و نام اختصاصی کانفیگ‌ها
CHANNELS = [
    "freeVPNjd"
]
CUSTOM_REMARK = "@Rooma_Net"
# ==========================================

PROTOCOLS = ("vless://", "trojan://")

# هدر مرورگر برای باز کردن تلگرام
TG_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# هدر اختصاصی کلاینت v2rayNG برای دریافت کانفیگ خام از سرورهای حساس سابسکریپشن
SUB_HEADERS = {
    'User-Agent': 'v2rayNG/1.8.19'
}

IGNORED_DOMAINS = (
    "t.me/", "telegram.org", "telegra.ph", "youtube.com", "youtu.be",
    "instagram.com", "twitter.com", "x.com", "google.com", "play.google.com",
    "apple.com", "github.com/2dust", "github.com/MatsuriDayo", "github.com/hiddify"
)
IGNORED_EXTENSIONS = (".apk", ".exe", ".dmg", ".zip", ".rar", ".jpg", ".jpeg", ".png", ".gif", ".mp4")

def is_valid_sub_url(url):
    """بررسی معتبر بودن لینک سابسکریپشن و حذف لینک‌های ثبت‌نام سایت‌ها"""
    url_lower = url.lower()
    if any(domain in url_lower for domain in IGNORED_DOMAINS):
        return False
    if url_lower.endswith(IGNORED_EXTENSIONS):
        return False
    # نادیده گرفتن صفحات ثبت‌نام و تبلیغاتی پنل‌ها
    if "/#/register" in url_lower or "/#/login" in url_lower or url_lower.endswith("/aff"):
        return False
    return True

def decode_base64(data):
    """رمزگشایی محتوای Base64"""
    try:
        data = data.strip()
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.b64decode(data).decode('utf-8', errors='ignore')
    except Exception:
        return ""

def clean_and_extract_configs(text):
    """استخراج کانفیگ‌های VLESS و Trojan از متن"""
    configs = set()
    for line in text.splitlines():
        line = line.strip()
        for proto in PROTOCOLS:
            if proto in line:
                matches = re.findall(rf'{proto}[^\s<>"]+', line)
                for m in matches:
                    configs.add(m.strip())
    return configs

def fetch_configs_from_sub(url):
    """دانلود لینک سابسکریپشن با یوزر ایجنت v2rayNG و فیلتر کردن VLESS و Trojan"""
    configs = set()
    try:
        # اگر لینک پارامتر clash داشت، آن را حذف می‌کنیم تا کانفیگ استاندارد V2Ray بدهد
        clean_url = re.sub(r'[?&]clash=[^&]+', '', url)
        
        res = requests.get(clean_url, headers=SUB_HEADERS, timeout=12, allow_redirects=True)
        if res.status_code == 200:
            content = res.text.strip()
            if not any(p in content for p in ("vless://", "vmess://", "trojan://", "ss://", "hy2://")):
                decoded = decode_base64(content)
                if decoded:
                    content = decoded
            configs.update(clean_and_extract_configs(content))
    except Exception as e:
        print(f"[-] Error fetching sub {url}: {e}")
    return configs

def scrape_channel(channel):
    """اسکرپ کردن نسخه وب کانال تلگرام"""
    url = f"https://t.me/s/{channel}"
    found_configs = set()
    sub_links = set()
    
    try:
        res = requests.get(url, headers=TG_HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        message_wraps = soup.find_all('div', class_='tgme_widget_message_wrap')
        
        for wrap in message_wraps:
            for a_tag in wrap.find_all('a', href=True):
                href = a_tag['href'].strip()
                if href.startswith(('http://', 'https://')) and is_valid_sub_url(href):
                    sub_links.add(href)

            msg_text_div = wrap.find('div', class_='tgme_widget_message_text')
            if msg_text_div:
                text = msg_text_div.get_text("\n")
                found_configs.update(clean_and_extract_configs(text))
                
                raw_urls = re.findall(r'https?://[^\s<>"]+', text)
                for u in raw_urls:
                    u = u.rstrip(').,;!]')
                    if is_valid_sub_url(u):
                        sub_links.add(u)
                        
    except Exception as e:
        print(f"[-] Error scraping channel {channel}: {e}")
        
    print(f"[*] Found {len(found_configs)} direct configs and {len(sub_links)} potential sub links in @{channel}")

    for sub in sub_links:
        print(f"[*] Checking subscription link: {sub}")
        extracted = fetch_configs_from_sub(sub)
        if extracted:
            print(f"    [+] Extracted {len(extracted)} VLESS/Trojan configs from sub!")
            found_configs.update(extracted)
            
    return found_configs

def deduplicate_and_rename(configs, custom_name):
    """حذف کانفیگ‌های تکراری و تغییر نام به @Rooma_Net"""
    unique_bases = []
    seen_keys = set()

    for cfg in configs:
        base_part = cfg.split('#')[0].strip()
        if base_part and base_part not in seen_keys:
            seen_keys.add(base_part)
            unique_bases.append(base_part)

    renamed_list = []
    for index, base_part in enumerate(unique_bases, start=1):
        new_remark = f"{custom_name} {index}"
        encoded_remark = quote(new_remark)
        renamed_list.append(f"{base_part}#{encoded_remark}")

    return renamed_list

def upload_to_cpanel(raw_text, b64_text):
    """ارسال مستقیم کانفیگ‌ها به فایل update.php در هاست سی‌پنل"""
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    webhook_token = os.environ.get("WEBHOOK_TOKEN", "").strip()
    
    if not webhook_url or not webhook_token:
        raise ValueError("[-] WEBHOOK_URL or WEBHOOK_TOKEN is not set in GitHub Secrets!")
        
    headers = {
        "X-Webhook-Token": webhook_token,
        "Content-Type": "application/json",
        "User-Agent": TG_HEADERS['User-Agent']
    }
    payload = {
        "token": webhook_token,  # ارسال توکن در بدنه JSON برای دور زدن محدودیت هدر سی‌پنل
        "raw": raw_text,
        "b64": b64_text
    }
    
    print(f"[*] Uploading to cPanel...")
    res = requests.post(webhook_url, json=payload, headers=headers, timeout=25)
    print(f"[*] Server Response ({res.status_code}): {res.text}")
    res.raise_for_status()

def main():
    all_configs = set()
    for ch in CHANNELS:
        print(f"[*] Scraping channel: @{ch}...")
        all_configs.update(scrape_channel(ch))
        
    final_configs = deduplicate_and_rename(all_configs, CUSTOM_REMARK)
    print(f"[+] Total unique VLESS/Trojan configs ready to upload: {len(final_configs)}")
    
    if not final_configs:
        print("[-] No configs found! Skipping upload to keep previous configs safe.")
        return
        
    raw_content = "\n".join(final_configs)
    b64_content = base64.b64encode(raw_content.encode("utf-8")).decode("utf-8")
    
    upload_to_cpanel(raw_content, b64_content)

if __name__ == "__main__":
    main()
