import asyncio
import re
import requests
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# --- CONFIGURATION & LOGGING ---
logging.basicConfig(
    filename="scrape.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"))
logging.getLogger("").addHandler(console)
log = logging.getLogger("scraper")

# These headers are used for the INITIAL request and the playlist metadata
CUSTOM_HEADERS = {
    "Origin": "https://embedsports.top",
    "Referer": "https://embedsports.top/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

FALLBACK_LOGOS = {
    "american football": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/nfl.png?raw=true",
    "football": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/football.png?raw=true",
    "fight": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/mma.png?raw=true",
    "basketball": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/nba.png?raw=true",
    "motor sports": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/f1.png?raw=true",
    "darts": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/darts2.png?raw=true",
    "tennis": "http://drewlive24.duckdns.org:9000/Logos/Tennis-2.png",
    "rugby": "http://drewlive24.duckdns.org:9000/Logos/Rugby.png",
    "cricket": "http://drewlive24.duckdns.org:9000/Logos/Cricket.png",
    "golf": "http://drewlive24.duckdns.org:9000/Logos/Golf.png",
    "other": "http://drewlive24.duckdns.org:9000/Logos/DrewLiveSports.png"
}

TV_IDS = {
    "baseball": "MLB.Baseball.Dummy.us",
    "fight": "PPV.EVENTS.Dummy.us",
    "american football": "Football.Dummy.us",
    "afl": "AUS.Rules.Football.Dummy.us",
    "football": "Soccer.Dummy.us",
    "basketball": "Basketball.Dummy.us",
    "hockey": "NHL.Hockey.Dummy.us",
    "tennis": "Tennis.Dummy.us",
    "darts": "Darts.Dummy.us",
    "motor sports": "Racing.Dummy.us",
    "rugby": "Rugby.Dummy.us",
    "cricket": "Cricket.Dummy.us",
    "other": "Sports.Dummy.us"
}

total_matches = 0
total_embeds = 0
total_streams = 0
total_failures = 0

# --- UTILS ---
def strip_non_ascii(text: str) -> str:
    if not text: return ""
    return re.sub(r"[^\x00-\x7F]+", "", text)

def get_all_matches():
    endpoints = ["live"]
    all_matches = []
    for ep in endpoints:
        try:
            log.info(f"📡 Fetching {ep} matches...")
            res = requests.get(f"https://streami.su/api/matches/{ep}", timeout=10)
            res.raise_for_status()
            data = res.json()
            all_matches.extend(data)
        except Exception as e:
            log.warning(f"⚠️ Failed fetching {ep}: {e}")
    return all_matches

def get_embed_urls_from_api(source):
    try:
        s_name, s_id = source.get("source"), source.get("id")
        if not s_name or not s_id: return []
        res = requests.get(f"https://streami.su/api/stream/{s_name}/{s_id}", timeout=6)
        res.raise_for_status()
        return [d.get("embedUrl") for d in res.json() if d.get("embedUrl")]
    except Exception:
        return []

# --- SCRAPING ENGINE ---
async def extract_m3u8(page, embed_url):
    global total_failures
    found = None
    try:
        async def on_request(request):
            nonlocal found
            # Capture the first .m3u8 request that isn't a known tracking/ads domain
            if ".m3u8" in request.url and not found:
                if any(x in request.url for x in ["prd.jwpltx.com", "telemetry", "log"]):
                    return
                found = request.url
                log.info(f"  ⚡ Found: {found[:50]}...")

        page.on("request", on_request)
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=15000)

        # Trigger play via sequence to bypass overlay ads
        for _ in range(2):
            if found: break
            try:
                # Click the center of the player
                await page.mouse.click(300, 300)
                await asyncio.sleep(1)
                # Close any new tabs that opened (ads)
                pages = page.context.pages
                if len(pages) > 1:
                    for p in pages[1:]: await p.close()
            except:
                pass

        if not found:
            # Last ditch effort: regex search in page source
            html = await page.content()
            match = re.search(r'(https?://[^\s"\'<> ]+\.m3u8[^\s"\'<> ]*)', html)
            if match: found = match.group(1)

        return found
    except Exception as e:
        total_failures += 1
        return None

def build_logo_url(match):
    cat = (match.get("category") or "other").strip()
    teams = match.get("teams") or {}
    for side in ["away", "home"]:
        badge = teams.get(side, {}).get("badge")
        if badge:
            return f"https://streami.su/api/images/badge/{badge}.webp", cat
    return FALLBACK_LOGOS.get(cat.lower(), FALLBACK_LOGOS["other"]), cat

async def process_match(index, match, total, ctx):
    global total_embeds, total_streams
    title = strip_non_ascii(match.get("title", "Unknown"))
    log.info(f"🎯 [{index}/{total}] {title}")
    
    sources = match.get("sources", [])
    page = await ctx.new_page()
    try:
        for s in sources:
            embed_urls = get_embed_urls_from_api(s)
            for embed in embed_urls:
                total_embeds += 1
                url = await extract_m3u8(page, embed)
                if url:
                    total_streams += 1
                    # Extract the domain for the Referer header
                    domain = re.search(r'https?://[^/]+', embed).group(0)
                    return match, url, domain
    finally:
        await page.close()
    return match, None, None

async def generate_playlist():
    global total_matches
    matches = get_all_matches()
    total_matches = len(matches)
    content = ["#EXTM3U"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a real user agent to prevent 403s on the embed page
        ctx = await browser.new_context(user_agent=CUSTOM_HEADERS["User-Agent"])
        
        for i, m in enumerate(matches, 1):
            match_obj, stream_url, embed_domain = await process_match(i, m, total_matches, ctx)
            
            if stream_url:
                logo, raw_cat = build_logo_url(match_obj)
                base_cat = raw_cat.strip().lower()
                tv_id = TV_IDS.get(base_cat, TV_IDS["other"])
                title = strip_non_ascii(match_obj.get("title", "Untitled"))

                # KEY FIX: Adding KODIPROP and Referer options to the M3U
                content.append(f'#EXTINF:-1 tvg-id="{tv_id}" tvg-logo="{logo}" group-title="{base_cat.title()}",{title}')
                # These headers tell the player (VLC, IPTV Smarters, Kodi) how to authorize the request
                content.append(f'#EXTVLCOPT:http-user-agent={CUSTOM_HEADERS["User-Agent"]}')
                content.append(f'#EXTVLCOPT:http-referrer={embed_domain}/')
                content.append(f'#EXTVLCOPT:http-origin={embed_domain}')
                # For Kodi/specific players
                content.append(f'#EXTVLCOPT:http-header=Origin: {embed_domain}')
                content.append(stream_url)

        await browser.close()
    return "\n".join(content)

if __name__ == "__main__":
    start = datetime.now()
    log.info("🚀 Starting Scrape...")
    playlist = asyncio.run(generate_playlist())
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write(playlist)
    log.info(f"🏁 Done! Scraped {total_streams} streams in {(datetime.now()-start).total_seconds():.2f}s")
