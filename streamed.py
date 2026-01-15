import asyncio
import re
import requests
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# Logging Configuration
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

# Settings - Ensure Referer matches the Origin for the 403 bypass
CUSTOM_HEADERS = {
    "Origin": "https://embedsports.top",
    "Referer": "https://embedsports.top/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

async def extract_m3u8(page, embed_url):
    found = None
    try:
        async def on_request(request):
            nonlocal found
            # Capture the .m3u8 but ignore tracking manifests
            if ".m3u8" in request.url and not found:
                if "prd.jwpltx.com" not in request.url and "telemetry" not in request.url:
                    found = request.url
                    log.info(f"  ⚡ Captured Stream: {found[:60]}...")

        page.on("request", on_request)
        
        # 1. Load the Embed Page
        await page.goto(embed_url, wait_until="load", timeout=15000)
        
        # 2. Click the "Start Button" (First click usually triggers ad)
        # We target the center of the player where the button usually sits
        await asyncio.sleep(2)
        await page.mouse.click(320, 240) 
        log.info("  👆 Clicked center (Start Button/Ad Trigger)")

        # 3. Wait and Close Ad Tabs
        await asyncio.sleep(1.5)
        pages = page.context.pages
        if len(pages) > 1:
            for p in pages[1:]:
                if p != page:
                    log.info(f"  🚫 Closing ad tab: {p.url[:40]}...")
                    await p.close()
        
        # 4. Second Click (Starts the actual video)
        await page.mouse.click(320, 240)
        log.info("  ▶️ Second click (Play Trigger)")
        
        # 5. Poll for the .m3u8 request
        for _ in range(20):
            if found: break
            await asyncio.sleep(0.5)

        return found
    except Exception as e:
        log.warning(f"  ⚠️ Failed extraction: {str(e)[:60]}")
        return None

def get_live_matches():
    try:
        # Fetching directly from the live endpoint
        res = requests.get("https://streami.su/api/matches/live", headers=CUSTOM_HEADERS, timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        log.error(f"❌ API Error: {e}")
        return []

def get_embed_urls_for_source(source):
    try:
        s_name, s_id = source.get("source"), source.get("id")
        res = requests.get(f"https://streami.su/api/stream/{s_name}/{s_id}", headers=CUSTOM_HEADERS, timeout=10)
        return [d.get("embedUrl") for d in res.json() if d.get("embedUrl")]
    except:
        return []

async def run_scraper():
    matches = get_live_matches()
    if not matches:
        log.error("No matches found.")
        return

    playlist_lines = ["#EXTM3U"]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Context needs the same headers as the requests to maintain session consistency
        context = await browser.new_context(
            user_agent=CUSTOM_HEADERS["User-Agent"],
            extra_http_headers={"Referer": CUSTOM_HEADERS["Referer"]}
        )

        for i, match in enumerate(matches, 1):
            title = match.get("title", "Unknown Event")
            log.info(f"\n🎯 [{i}/{len(matches)}] {title}")
            
            sources = match.get("sources", [])
            if not sources:
                log.info("  ❌ No sources available for this event.")
                continue

            extracted_url = None
            page = await context.new_page()
            
            for source in sources:
                embeds = get_embed_urls_for_source(source)
                for embed in embeds:
                    log.info(f"  ↳ Trying: {embed[:50]}...")
                    extracted_url = await extract_m3u8(page, embed)
                    if extracted_url: break
                if extracted_url: break
            
            if extracted_url:
                # Add VLC specific options to the playlist to bypass the 403 error
                playlist_lines.append(f'#EXTINF:-1, {title}')
                playlist_lines.append(f'#EXTVLCOPT:http-referrer={CUSTOM_HEADERS["Referer"]}')
                playlist_lines.append(f'#EXTVLCOPT:http-user-agent={CUSTOM_HEADERS["User-Agent"]}')
                playlist_lines.append(extracted_url)
                log.info(f"  ✅ Stream verified.")
            
            await page.close()

        await browser.close()

    # Save the playlist
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist_lines))
    log.info("\n🎉 Playlist generation complete.")

if __name__ == "__main__":
    asyncio.run(run_scraper())
