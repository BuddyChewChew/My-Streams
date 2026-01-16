import asyncio
import requests
import logging
import random
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# API Setup
API_BASE = "https://a.streamed.pk/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://streamed.pk/",
}

async def extract_m3u8(page, embed_url):
    found_url = None
    stealth = Stealth()
    
    # 1. Block tracking and intercept M3U8
    async def handle_route(route):
        url = route.request.url
        if any(x in url for x in ["usrpubtrk.com", "doubleclick", "analytics", "telemetry"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            nonlocal found_url
            found_url = url
            log.info(f"  ⚡ Captured: {url[:70]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        # Apply new Stealth API
        await stealth.apply_stealth_async(page)
        
        parsed = urlparse(embed_url)
        await page.set_extra_http_headers({
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
            "Origin": f"{parsed.scheme}://{parsed.netloc}"
        })
        
        log.info(f"  ↳ Probing: {embed_url[:50]}...")
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(7)

        # 2. Clicking Strategy
        for attempt in range(3):
            if found_url: break
            rx = 640 + random.randint(-20, 20)
            ry = 360 + random.randint(-20, 20)
            
            log.info(f"  👆 Clicking at ({rx}, {ry})")
            await page.mouse.click(rx, ry)
            await asyncio.sleep(3)

            # Close Ad-Tabs
            if len(page.context.pages) > 1:
                log.info("  🚫 Closing ad popup...")
                for p in page.context.pages:
                    if p != page: await p.close()
                await page.mouse.click(rx, ry)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Error: {str(e)[:40]}")
        return None

async def run():
    log.info("📡 Fetching events...")
    try:
        events = requests.get(f"{API_BASE}/event", headers=HEADERS, timeout=15).json()
    except Exception as e:
        log.error(f"API Error: {e}")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-web-security"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720}, user_agent=HEADERS["User-Agent"])

        # Limit to 12 matches for stability
        for i, event in enumerate(events[:12], 1):
            title = event.get("title", "Unknown")
            eid = event.get("id")
            log.info(f"\n🎯 [{i}/12] {title}")

            try:
                sources_res = requests.get(f"{API_BASE}/source/{eid}", headers=HEADERS, timeout=10)
                sources = sources_res.json()
            except: continue

            page = await context.new_page()
            stream_found = None

            for source in sources:
                url = source.get("embedUrl")
                if url:
                    stream_found = await extract_m3u8(page, url)
                    if stream_found: break
            
            if stream_found:
                playlist.append(f'#EXTINF:-1, {title}\n{stream_found}')
                success_count += 1
                log.info(f"  ✅ SUCCESS")
            else:
                log.info(f"  ❌ FAILED")
            
            await page.close()

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. {success_count} streams added.")

if __name__ == "__main__":
    asyncio.run(run())
