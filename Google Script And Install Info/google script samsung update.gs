import requests
import gzip
import json
import os
import logging
import time
import re
from io import BytesIO

# --- Configuration ---
OUTPUT_DIR = "playlists"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
REQUEST_TIMEOUT = 30 

REGION_MAP = {
    'us': 'United States', 'gb': 'United Kingdom', 'ca': 'Canada',
    'de': 'Germany', 'es': 'Spain', 'fr': 'France', 'it': 'Italy', 
    'br': 'Brazil', 'mx': 'Mexico', 'ar': 'Argentina', 'au': 'Australia'
}

# Mapping keywords to categories. 
KEYWORD_CATEGORIES = {
    'Movies': ['movie', 'cinema', 'film', 'hallmark', 'thriller'],
    'News': ['news', 'reuters', 'bloomberg', 'weather', 'local', 'bbc', 'cnn', 'msnbc'],
    'Sports': ['sport', 'nfl', 'mlb', 'fubo', 'racing', 'fight', 'golf', 'soccer'],
    'Kids': ['kids', 'cartoon', 'nick', 'baby', 'disney'],
    'Music': ['music', 'mtv', 'vevo', 'concert', 'vh1'],
    'Comedy': ['comedy', 'funny', 'laugh', 'sitcom'],
    'Crime': ['crime', 'mystery', 'detective', 'forensic', 'law']
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_smart_category(channel_name):
    """Checks name against keywords. If no match, labels as 'Unsorted'."""
    name_lower = channel_name.lower()
    for category, keywords in KEYWORD_CATEGORIES.items():
        if any(kw in name_lower for kw in keywords):
            return category
    return "Unsorted"

def cleanup_output_dir():
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            file_path = os.path.join(OUTPUT_DIR, filename)
            try:
                if os.path.isfile(file_path): os.unlink(file_path)
            except Exception as e: logger.error(f"Error cleaning {file_path}: {e}")
    else:
        os.makedirs(OUTPUT_DIR)

def fetch_url(url, is_json=True, is_gzipped=False, headers=None):
    headers = headers or {'User-Agent': USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content = response.content
        if is_gzipped:
            with gzip.GzipFile(fileobj=BytesIO(content), mode='rb') as f:
                content = f.read()
        return json.loads(content.decode('utf-8')) if is_json else content.decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None

def format_extinf(c_id, tvg_id, chno, name, logo, group, display_name):
    group_str = group if group else "Unsorted"
    clean_name = name.replace('"', "'")
    return f'#EXTINF:-1 channel-id="{c_id}" tvg-id="{tvg_id}" tvg-chno="{chno or ""}" tvg-name="{clean_name}" tvg-logo="{logo}" group-title="{group_str}",{clean_name}\n'

# --- Service Generators ---

def generate_pluto_m3u():
    data = fetch_url('https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/PlutoTV/.channels.json.gz', is_gzipped=True)
    if not data: return
    for region in list(data['regions'].keys()) + ['all']:
        output = [f'#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/{region}.xml.gz"\n']
        channels = []
        if region == 'all':
            for r_code, r_data in data['regions'].items():
                for c_id, c_info in r_data.get('channels', {}).items():
                    grp = f"{REGION_MAP.get(r_code, r_code.upper())}: {c_info.get('group', 'Unsorted')}"
                    channels.append({**c_info, 'id': f"{c_id}-{r_code}", 'orig_id': c_id, 'group': grp})
        else:
            region_data = data['regions'].get(region, {}).get('channels', {})
            for c_id, c_info in region_data.items():
                channels.append({**c_info, 'id': c_id, 'orig_id': c_id, 'group': c_info.get('group', 'Unsorted')})
        
        for ch in sorted(channels, key=lambda x: x['name']):
            output.append(format_extinf(ch['id'], ch['orig_id'], ch.get('chno'), ch['name'], ch['logo'], ch['group'], ch['name']))
            output.append(f"https://jmp2.uk/plu-{ch['orig_id']}.m3u8\n")
        with open(os.path.join(OUTPUT_DIR, f"plutotv_{region}.m3u"), 'w', encoding='utf-8') as f: f.write("".join(output))

def generate_plex_m3u():
    data = fetch_url('https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/Plex/.channels.json.gz', is_gzipped=True)
    if not data: return
    found_regions = set()
    for ch in data['channels'].values(): found_regions.update(ch.get('regions', []))
    for region in list(found_regions) + ['all']:
        output = [f'#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/Plex/{region}.xml.gz"\n']
        for c_id, ch in data['channels'].items():
            if region == 'all' or region in ch.get('regions', []):
                group = get_smart_category(ch['name'])
                output.append(format_extinf(c_id, c_id, ch.get('chno'), ch['name'], ch['logo'], group, ch['name']))
                output.append(f"https://jmp2.uk/plex-{c_id}.m3u8\n")
        with open(os.path.join(OUTPUT_DIR, f"plex_{region}.m3u"), 'w', encoding='utf-8') as f: f.write("".join(output))

def generate_samsungtvplus_m3u():
    data = fetch_url('https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/SamsungTVPlus/.channels.json.gz', is_gzipped=True)
    if not data: return
    for region in list(data['regions'].keys()) + ['all']:
        output = [f'#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/SamsungTVPlus/{region}.xml.gz"\n']
        channels = []
        if region == 'all':
            for r_code, r_info in data['regions'].items():
                for c_id, c_info in r_info.get('channels', {}).items():
                    grp = f"{REGION_MAP.get(r_code, r_code.upper())}: {c_info.get('group', 'Unsorted')}"
                    channels.append({**c_info, 'id': f"{c_id}-{r_code}", 'orig_id': c_id, 'group': grp})
        else:
            region_info = data['regions'].get(region, {}).get('channels', {})
            for c_id, c_info in region_info.items():
                channels.append({**c_info, 'id': c_id, 'orig_id': c_id, 'group': c_info.get('group', 'Unsorted')})
        
        for ch in sorted(channels, key=lambda x: x['name']):
            slug = ch.get('slug', 'stvp-{id}').replace('{id}', ch['orig_id'])
            output.append(format_extinf(ch['id'], ch['orig_id'], ch.get('chno'), ch['name'], ch['logo'], ch['group'], ch['name']))
            output.append(f"https://jmp2.uk/{slug}\n")
        with open(os.path.join(OUTPUT_DIR, f"samsungtvplus_{region}.m3u"), 'w', encoding='utf-8') as f: f.write("".join(output))

def generate_stirr_m3u():
    data = fetch_url('https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/Stirr/.channels.json.gz', is_gzipped=True)
    if not data: return
    output = ['#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/Stirr/all.xml.gz"\n']
    for c_id, ch in data['channels'].items():
        group = ", ".join(ch.get('groups', [])) if ch.get('groups') else "Unsorted"
        output.append(format_extinf(c_id, c_id, ch.get('chno'), ch['name'], ch['logo'], group, ch['name']))
        output.append(f"https://jmp2.uk/str-{c_id}.m3u8\n")
    with open(os.path.join(OUTPUT_DIR, "stirr_all.m3u"), 'w', encoding='utf-8') as f: f.write("".join(output))

def generate_roku_m3u():
    data = fetch_url('https://i.mjh.nz/Roku/.channels.json') 
    if not data: return
    output = ['#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/Roku/all.xml.gz"\n']
    for c_id, ch in data['channels'].items():
        group = ch.get('groups', ['Unsorted'])[0]
        output.append(format_extinf(c_id, c_id, ch.get('chno'), ch['name'], ch['logo'], group, ch['name']))
        output.append(f"https://jmp2.uk/rok-{c_id}.m3u8\n")
    with open(os.path.join(OUTPUT_DIR, "roku_all.m3u"), 'w', encoding='utf-8') as f: f.write("".join(output))

def generate_tubi_m3u():
    content = fetch_url('https://raw.githubusercontent.com/BuddyChewChew/tubi-scraper/refs/heads/main/tubi_playlist.m3u', is_json=False)
    if not content: return
    
    lines = content.strip().split('\n')
    output = ['#EXTM3U url-tvg="https://raw.githubusercontent.com/BuddyChewChew/tubi-scraper/refs/heads/main/tubi_epg.xml"\n']
    
    current_extinf = ""
    for line in lines:
        if line.startswith('#EXTINF'):
            name_match = re.search(r',(.+)$', line)
            channel_name = name_match.group(1) if name_match else "Tubi Channel"
            group = get_smart_category(channel_name)
            
            # Update group-title to match our smart category
            if 'group-title="' in line:
                line = re.sub(r'group-title="[^"]*"', f'group-title="{group}"', line)
            else:
                line = line.replace(', ', f' group-title="{group}", ')
            current_extinf = line
        elif line.startswith('http'):
            output.append(current_extinf + "\n" + line + "\n")
            
    with open(os.path.join(OUTPUT_DIR, "tubi_all.m3u"), 'w', encoding='utf-8') as f:
        f.write("".join(output))

if __name__ == "__main__":
    cleanup_output_dir()
    generate_pluto_m3u()
    generate_plex_m3u()
    generate_samsungtvplus_m3u()
    generate_stirr_m3u()
    generate_roku_m3u()
    generate_tubi_m3u()
    logger.info("Playlists updated: Unmatched channels moved to 'Unsorted'.")
