import requests
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

json_urls = [
    "https://magnetic.website/MAD_TITAN_SPORTS/TOOLS/METAL/luc-247.json",
    "https://magnetic.website/MAD_TITAN_SPORTS/TOOLS/METAL/ky-247.json",
    "https://magnetic.website/MAD_TITAN_SPORTS/TOOLS/METAL/sps-247.json",
    "https://magnetic.website/MAD_TITAN_SPORTS/TOOLS/METAL/zpenn-247.json
]

STATIC_TVG_ID = "24.7.Dummy.us"
STATIC_LOGO_URL = "https://github.com/BuddyChewChew/ppv/blob/main/assets/24-7.png?raw=true"
MAX_WORKERS = 50
CHECK_TIMEOUT = 5

def check_stream(channel_info, session):
    url = channel_info.get("stream_url")
    if not url:
        return None
    try:
        response = session.head(url, timeout=CHECK_TIMEOUT, allow_redirects=True)
        if response.status_code == 200:
            return channel_info
    except requests.exceptions.RequestException:
        pass
    return None

all_channels = []
for url in json_urls:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        if not items:
            print(f"Warning: No 'items' found in {url}")
            continue

        for item in items:
            channel_name = item.get("channel") or re.sub(r'\[.*?\]', '', item.get("title", "")).strip()
            stream_url = item.get("stream") or item.get("link", "")
            category = item.get("category", "General")

            if stream_url and channel_name:
                all_channels.append({
                    "name": channel_name,
                    "stream_url": stream_url,
                    "group": f"{category}"
                })
                
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {url}.")

valid_channels = []
total_to_check = len(all_channels)

with requests.Session() as session:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_channel = {executor.submit(check_stream, channel, session): channel for channel in all_channels}
        
        for i, future in enumerate(as_completed(future_to_channel)):
            result = future.result()
            if result:
                valid_channels.append(result)
            
            progress = (i + 1) / total_to_check * 100
            sys.stdout.write(f"\rChecking streams... {int(progress)}% complete")
            sys.stdout.flush()

m3u8_content = "#EXTM3U\n"
for channel in valid_channels:
    m3u8_content += f'#EXTINF:-1 tvg-id="{STATIC_TVG_ID}" tvg-logo="{STATIC_LOGO_URL}" group-title="{channel["group"]}",{channel["name"]}\n'
    m3u8_content += f'{channel["stream_url"]}\n'

try:
    with open("24-7.m3u8", "w", encoding="utf-8") as file:
        file.write(m3u8_content)
    print(f"\n\nSuccess! Wrote {len(valid_channels)} valid streams to '24-7.m3u8'.")
except Exception as e:
    print(f"\nError writing to file: {e}")
