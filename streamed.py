import asyncio
import requests
import logging
import random
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

API_BASE = "https://a.streamed.pk/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://streamed.pk/",
}

async def extract_m3u8(page, embed_url):
    found_url = None
    stealth = Stealth()
    
    async def handle_route(route):
        # FIX: The 'nonlocal' declaration MUST come before any other use of the variable
        nonlocal found_url 
        url = route.request.url
        
        # Block tracking scripts that trigger bot detection
        if any(x in url for x in ["usrpubtrk.com", "doubleclick", "analytics", "telemetry"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            # Avoid capturing internal player telemetry files
            if "telemetry" not in url.lower():
                found_url = url
                log.info(f"  ⚡ Captured: {url[:60]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        await stealth.apply_stealth_async(page)
        
        parsed = urlparse(embed_url)
        await page.set_extra_http_headers({
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
            "Origin": f"{parsed.scheme}://{parsed.netloc}"
        })
        
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # Randomized clicking to trigger the stream play
        for _ in range(3):
            if found_url: break
            await page.mouse.click(640 + random.randint(-10, 10), 360 + random.randint(-10, 10))
            await asyncio.sleep(3)
            # Close pop-up tabs if they appear
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Extraction Error: {str(e)[:50]}")
        return None

async def run():
    log.info("📡 Fetching events...")
    try:
        events = requests.get(f"{API_BASE}/event", headers=HEADERS).json()
    except Exception as e:
        log.error(f"API Error: {e}")
        return

    playlist = ["#EXTM3U"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        for i, event in enumerate(events[:10], 1): # Process top 10
            title = event.get("title", "Unknown")
            eid = event.get("id")
            log.info(f"🎯 [{i}/10] {title}")

            sources = requests.get(f"{API_BASE}/source/{eid}", headers=HEADERS).json()
            page = await context.new_page()
            
            for source in sources:
                m3u8 = await extract_m3u8(page, source.get("embedUrl"))
                if m3u8:
                    playlist.append(f'#EXTINF:-1, {title}\n{m3u8}')
                    break
            await page.close()

        await browser.close()

    with open("StreamedSU.m3u8", "w") as f:
        f.write("\n".join(playlist))
    log.info("✅ Playlist updated.")

if __name__ == "__main__":
    asyncio.run(run())
