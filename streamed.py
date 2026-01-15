import asyncio
import re
import requests
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("streamed_pk")

# --- CONFIGURATION & CATEGORY MAPPING ---
BASE_URL = "https://streamed.pk"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Mapping categories from streamed.pk docs to IPTV-friendly IDs/Logos
SPORTS_CONFIG = {
    "football": {"id": "Soccer.Dummy.us", "group": "Football"},
    "basketball": {"id": "Basketball.Dummy.us", "group": "Basketball"},
    "american football": {"id": "Football.Dummy.us", "group": "NFL & NCAA"},
    "hockey": {"id": "NHL.Hockey.Dummy.us", "group": "Hockey"},
    "tennis": {"id": "Tennis.Dummy.us", "group": "Tennis"},
    "motor sports": {"id": "Racing.Dummy.us", "group": "Motorsports"},
    "fight": {"id": "Fight.Dummy.us", "group": "MMA & Boxing"},
    "other": {"id": "Sports.Dummy.us", "group": "Other Sports"}
}

# --- API TOOLS ---
def get_live_matches():
    try:
        log.info(f"📡 Fetching live matches from {BASE_URL}...")
        res = requests.get(f"{BASE_URL}/api/matches/live", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        log.error(f"❌ Failed to reach API: {e}")
        return []

def get_embeds(source):
    try:
        res = requests.get(f"{BASE_URL}/api/stream/{source['source']}/{source['id']}", timeout=6)
        return [item.get("embedUrl") for item in res.json() if item.get("embedUrl")]
    except:
        return []

# --- SCRAPER ENGINE ---
async def extract_stream(page, embed_url):
    m3u8_link = None
    try:
        async def on_request(request):
            nonlocal m3u8_link
            if ".m3u8" in request.url and not m3u8_link:
                # Ignore common ad/tracking fragments
                if not any(x in request.url for x in ["telemetry", "analytics", "logger"]):
                    m3u8_link = request.url
                    log.info(f"  ⚡ Found stream link: {m3u8_link[:50]}...")

        page.on("request", on_request)
        await page.goto(embed_url, wait_until="load", timeout=20000)

        # Trigger play and bypass the initial 403 handshake
        for _ in range(3):
            if m3u8_link: break
            await page.mouse.click(300, 300)
            await asyncio.sleep(1.5)
            # Close ad tabs instantly
            if len(page.context.pages) > 1:
                for ad in page.context.pages[1:]: await ad.close()
        
        return m3u8_link
    except:
        return None

async def run():
    matches = get_live_matches()
    playlist = ["#EXTM3U"]
    count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT)
        
        for i, match in enumerate(matches, 1):
            title = re.sub(r'[^\x00-\x7F]+', '', match.get("title", "Match"))
            log.info(f"🎯 [{i}/{len(matches)}] Processing: {title}")
            
            for source in match.get("sources", []):
                embeds = get_embeds(source)
                for embed in embeds:
                    page = await ctx.new_page()
                    m3u8 = await extract_stream(page, embed)
                    await page.close()
                    
                    if m3u8:
                        # Extract the domain for the Referer fix
                        referer = re.search(r'https?://[^/]+', embed).group(0)
                        
                        # Apply category config
                        cat_key = match.get("category", "other").lower()
                        conf = SPORTS_CONFIG.get(cat_key, SPORTS_CONFIG["other"])
                        
                        # INTEGRATED SETTINGS: Header injection for VLC/Players
                        playlist.append(f'#EXTINF:-1 tvg-id="{conf["id"]}" group-title="{conf["group"]}", {title}')
                        playlist.append(f'#EXTVLCOPT:http-user-agent={USER_AGENT}')
                        playlist.append(f'#EXTVLCOPT:http-referrer={referer}/')
                        playlist.append(f'#EXTVLCOPT:http-origin={referer}')
                        playlist.append(m3u8)
                        count += 1
                        break
                if m3u8: break # Move to next match if we found a stream

        await browser.close()

    with open("StreamedPK.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"🏁 Finished! {count} streams written to StreamedPK.m3u8")

if __name__ == "__main__":
    asyncio.run(run())
