import asyncio
import requests
import logging
import random
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# API endpoint from your recommendation
API_BASE = "https://streami.su/api"

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Referer": "https://streamed.su/",
    "Origin": "https://streamed.su",
    "Accept": "application/json, text/plain, */*"
}

PLAYER_HEADERS = {
    "Origin": "https://streamed.su",
    "Referer": "https://streamed.su/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
}

async def extract_m3u8(page, embed_url):
    """Intercepts the .m3u8 stream URL while bypassing ads."""
    found_url = None
    stealth = Stealth()
    
    async def handle_route(route):
        nonlocal found_url
        url = route.request.url
        if any(x in url for x in ["usrpubtrk.com", "doubleclick", "analytics", "telemetry"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            if all(x not in url.lower() for x in ["telemetry", "prd.jwpltx"]):
                found_url = url
                log.info(f"   ⚡ Captured: {url[:60]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        await stealth.apply_stealth_async(page)
        await page.set_extra_http_headers(PLAYER_HEADERS)
        
        log.info(f"   ↳ Probing: {embed_url}")
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(8) 

        for _ in range(2): 
            if found_url: break
            # Targeted click to bypass overlays
            await page.mouse.click(640 + random.randint(-10, 10), 360 + random.randint(-10, 10))
            await asyncio.sleep(4)
            
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception:
        return None

async def run():
    log.info(f"📡 Using API: {API_BASE}")
    try:
        response = requests.get(f"{API_BASE}/matches/all", headers=API_HEADERS, timeout=15)
        response.raise_for_status()
        matches = response.json()
    except Exception as e:
        log.error(f"❌ API Access Failed: {e}")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        # Process first 12 matches to stay within action limits
        for i, match in enumerate(matches[:12], 1):
            title = match.get("title", "Match")
            match_id = match.get("id")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}] {title}")

            page = await context.new_page()
            
            target_urls = []
            # Priority 1: Use specific IDs from sources array
            if sources:
                for src in sources:
                    s_provider = src.get("source")
                    s_id = src.get("id")
                    if s_provider and s_id:
                        target_urls.append(f"https://streamed.su/watch/{s_provider}/{s_id}")
            
            # Priority 2: Use top-level match ID as fallback
            if match_id:
                target_urls.append(f"https://streamed.su/watch/main/{match_id}")

            found_stream = None
            for embed_url in target_urls:
                found_stream = await extract_m3u8(page, embed_url)
                if found_stream: break
            
            if found_stream:
                playlist.append(f'#EXTINF:-1, {title}\n{found_stream}')
                success += 1
                log.info(f"   ✅ SUCCESS")
            else:
                log.info(f"   ❌ FAILED")
            
            await page.close()

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. Total Streams: {success}")

if __name__ == "__main__":
    asyncio.run(run())
