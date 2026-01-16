import asyncio
import requests
import logging
import random
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# UPDATED: 'api.streamed.su' failed to resolve. Using the verified 'v3' endpoint.
API_BASE = "https://v3.streamed.su/api"

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
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(8) 

        for _ in range(3):
            if found_url: break
            await page.mouse.click(640 + random.randint(-10, 10), 360 + random.randint(-10, 10))
            await asyncio.sleep(3)
            
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception:
        return None

async def run():
    log.info(f"📡 Connecting to API: {API_BASE}...")
    try:
        # Fetching from the verified v3 matches endpoint
        response = requests.get(f"{API_BASE}/matches/all", headers=API_HEADERS, timeout=20)
        response.raise_for_status()
        matches = response.json()
    except Exception as e:
        log.error(f"❌ Connection Failed: {e}")
        log.info("💡 Trying fallback domain: https://streamed.su/api/matches/all")
        try:
            response = requests.get("https://streamed.su/api/matches/all", headers=API_HEADERS, timeout=20)
            matches = response.json()
        except:
            log.error("❌ All API domains failed to resolve.")
            return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        for i, match in enumerate(matches[:15], 1):
            title = match.get("title", "Match")
            match_id = match.get("id")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}] {title}")

            page = await context.new_page()
            
            target_urls = []
            if sources:
                for src in sources:
                    if src.get("source") and src.get("id"):
                        # Use the watch format from the commit diff
                        target_urls.append(f"https://streamed.su/watch/{src['source']}/{src['id']}")
            
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
