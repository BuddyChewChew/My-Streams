import asyncio
import requests
import logging
import random
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# Using the API domain you confirmed is working
API_BASE = "https://streami.su/api"

# These must match the domain we are probing to pass security checks
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Referer": "https://streamed.su/",
    "Origin": "https://streamed.su",
}

async def extract_m3u8(page, embed_url):
    found_url = None
    stealth = Stealth()
    
    async def handle_route(route):
        nonlocal found_url
        url = route.request.url
        if any(x in url for x in ["analytics", "doubleclick", "usrpubtrk"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            # Filter for actual video fragments, not telemetry
            if "jwpltx" not in url.lower():
                found_url = url
                log.info(f"   ⚡ Captured: {url[:50]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        await stealth.apply_stealth_async(page)
        await page.set_extra_http_headers(COMMON_HEADERS)
        
        log.info(f"   ↳ Probing: {embed_url}")
        # Use a longer timeout and wait for network idle to ensure the player initializes
        await page.goto(embed_url, wait_until="networkidle", timeout=45000)
        await asyncio.sleep(10) 

        # Interaction to bypass the "Click to Play" overlay
        for _ in range(3):
            if found_url: break
            # Click exactly in the center where the Play button usually sits
            await page.mouse.click(640, 360)
            await asyncio.sleep(5)
            
            # Close ad-popups
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception as e:
        log.debug(f"Error: {e}")
        return None

async def run():
    log.info(f"📡 API Fetch: {API_BASE}/matches/all")
    try:
        # We use streami.su for data, but streamed.su for the browser
        resp = requests.get(f"{API_BASE}/matches/all", headers=COMMON_HEADERS, timeout=15)
        matches = resp.json()
    except Exception as e:
        log.error(f"❌ API Error: {e}")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-web-security"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        # Process top 10 matches
        for i, match in enumerate(matches[:10], 1):
            title = match.get("title", "Match")
            match_id = match.get("id")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}] {title}")

            page = await context.new_page()
            
            # Build URL list based on your live.json structure
            target_urls = []
            for src in sources:
                if src.get("source") and src.get("id"):
                    target_urls.append(f"https://streamed.su/watch/{src['source']}/{src['id']}")
            
            # Always fallback to the main match ID
            target_urls.append(f"https://streamed.su/watch/main/{match_id}")

            found_stream = None
            for url in target_urls:
                found_stream = await extract_m3u8(page, url)
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
    log.info(f"\n🎉 Finished. Total: {success}")

if __name__ == "__main__":
    asyncio.run(run())
