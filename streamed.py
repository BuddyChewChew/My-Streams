import asyncio
import requests
import logging
import random
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configure logging for GitHub Actions visibility
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# The API endpoint is correct, but it requires specific headers to not redirect
API_BASE = "https://a.streamed.pk/api"

# These headers are essential to avoid the "Expecting value: line 1 column 1" error
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Referer": "https://streamed.pk/",
    "Origin": "https://streamed.pk",
    "Accept": "application/json, text/plain, */*"
}

# Your custom headers for the actual video player authorization
PLAYER_HEADERS = {
    "Origin": "https://embedsports.top",
    "Referer": "https://embedsports.top/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
}

async def extract_m3u8(page, embed_url):
    """Uses Playwright to intercept the M3U8 stream URL from the player."""
    found_url = None
    stealth = Stealth()
    
    async def handle_route(route):
        nonlocal found_url
        url = route.request.url
        # Block tracking scripts identified in your job-logs.txt
        if any(x in url for x in ["usrpubtrk.com", "doubleclick", "analytics", "telemetry"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            # Filter out internal telemetry streams
            if all(x not in url.lower() for x in ["telemetry", "prd.jwpltx"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:60]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        await stealth.apply_stealth_async(page)
        # Apply your authorization headers for the player
        await page.set_extra_http_headers(PLAYER_HEADERS)
        
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(7)

        # Simulate clicks to trigger the video stream and bypass ad-overlays
        for _ in range(3):
            if found_url: break
            await page.mouse.click(640 + random.randint(-15, 15), 360 + random.randint(-15, 15))
            await asyncio.sleep(4)
            # Close popup ads that trigger on click
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception:
        return None

async def run():
    log.info("📡 Fetching Live Match List...")
    try:
        # Step 1: Request live matches using API_HEADERS to prevent blocks
        response = requests.get(f"{API_BASE}/matches/live", headers=API_HEADERS, timeout=20)
        if response.status_code != 200:
            log.error(f"❌ API Access Denied: Status {response.status_code}")
            return
        matches = response.json()
    except Exception as e:
        log.error(f"❌ Request Error: {e}")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # Launch browser with settings to avoid detection 
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        # Process the top 10 currently live matches
        for i, match in enumerate(matches[:10], 1):
            title = match.get("title", "Match")
            match_id = match.get("id")
            log.info(f"\n🎯 [{i}/10] {title}")

            # Step 2: Get available sources for the match
            try:
                src_resp = requests.get(f"{API_BASE}/source/{match_id}", headers=API_HEADERS, timeout=10)
                sources = src_resp.json()
            except: continue

            page = await context.new_page()
            found_stream = None

            # Step 3: Iterate through provider endpoints (alpha, delta, etc.)
            for s in sources:
                provider = s.get("source").lower()
                sid = s.get("id")
                try:
                    # Construct the dynamic provider URL
                    stream_api = f"{API_BASE}/stream/{provider}/{sid}"
                    res = requests.get(stream_api, headers=API_HEADERS, timeout=10).json()
                    
                    for item in res:
                        embed_url = item.get("embedUrl")
                        if embed_url:
                            found_stream = await extract_m3u8(page, embed_url)
                            if found_stream: break
                except: continue
                if found_stream: break
            
            if found_stream:
                playlist.append(f'#EXTINF:-1, {title}\n{found_stream}')
                success_count += 1
            
            await page.close()

        await browser.close()

    # Save the final playlist for your GitHub Action to commit 
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Process Complete. Total Streams: {success_count}")

if __name__ == "__main__":
    asyncio.run(run())
