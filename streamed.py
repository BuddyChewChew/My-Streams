import asyncio
import requests
import logging
import random
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configure logging for GitHub Actions visibility
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

API_BASE = "https://a.streamed.pk/api"

# Essential headers to avoid the JSON Decode Error (HTML block page)
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Referer": "https://streamed.pk/",
    "Origin": "https://streamed.pk",
    "Accept": "application/json, text/plain, */*"
}

# Your specific authorization headers for the video player
PLAYER_HEADERS = {
    "Origin": "https://embedsports.top",
    "Referer": "https://embedsports.top/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
}

async def extract_m3u8(page, embed_url):
    """Intercepts the .m3u8 stream URL while bypassing tracking/ads."""
    found_url = None
    stealth = Stealth()
    
    async def handle_route(route):
        nonlocal found_url
        url = route.request.url
        
        # Block high-frequency tracking scripts found in job-logs
        if any(x in url for x in ["usrpubtrk.com", "doubleclick", "analytics", "telemetry"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            # Filter for the actual stream, excluding internal telemetry
            if all(x not in url.lower() for x in ["telemetry", "prd.jwpltx"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:60]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        await stealth.apply_stealth_async(page)
        await page.set_extra_http_headers(PLAYER_HEADERS)
        
        log.info(f"  ↳ Probing Player: {embed_url[:50]}...")
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)

        # Interaction loop to bypass ad-overlays and trigger stream
        for _ in range(3):
            if found_url: break
            await page.mouse.click(640 + random.randint(-15, 15), 360 + random.randint(-15, 15))
            await asyncio.sleep(3)
            
            # Auto-close popup tabs triggered by clicks
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception:
        return None

async def run():
    log.info("📡 Fetching Live Matches...")
    try:
        # Step 1: Get Live Matches using API_HEADERS
        response = requests.get(f"{API_BASE}/matches/live", headers=API_HEADERS, timeout=20)
        if response.status_code != 200:
            log.error(f"❌ API Access Blocked: Status {response.status_code}")
            return
        matches = response.json()
    except Exception as e:
        log.error(f"❌ API Error: {e}")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        # Process first 10 live matches
        for i, match in enumerate(matches[:10], 1):
            title = match.get("title", "Match")
            match_id = match.get("id")
            log.info(f"\n🎯 [{i}/10] {title}")

            # Step 2: Fetch available sources for this match
            try:
                src_resp = requests.get(f"{API_BASE}/source/{match_id}", headers=API_HEADERS, timeout=10)
                sources = src_resp.json()
            except: continue

            page = await context.new_page()
            found_stream = None

            # Step 3: Provider-specific routing (Alpha, Delta, etc.)
            for s in sources:
                provider = s.get("source").lower()
                sid = s.get("id")
                try:
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
                success += 1
                log.info(f"  ✅ SUCCESS")
            else:
                log.info(f"  ❌ FAILED")
            
            await page.close()

        await browser.close()

    # Save playlist to file
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. Total Streams: {success}")

if __name__ == "__main__":
    asyncio.run(run())
