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
        # FIX: nonlocal must be the first line in the sub-function
        nonlocal found_url
        url = route.request.url
        
        # Block known tracking and telemetry to reduce detection
        if any(x in url for x in ["usrpubtrk.com", "doubleclick", "analytics", "telemetry"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            # Filter out internal JWPlayer or telemetry M3U8s
            if all(x not in url.lower() for x in ["prd.jwpltx", "telemetry"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:70]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        # Use the updated Class-based Stealth API
        await stealth.apply_stealth_async(page)
        
        parsed = urlparse(embed_url)
        await page.set_extra_http_headers({
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
            "Origin": f"{parsed.scheme}://{parsed.netloc}"
        })
        
        log.info(f"  ↳ Probing: {embed_url[:50]}...")
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(7)

        # Randomized interaction to bypass "click to play" overlays
        for attempt in range(3):
            if found_url: break
            
            rx = 640 + random.randint(-15, 15)
            ry = 360 + random.randint(-15, 15)
            
            log.info(f"  👆 Clicking Play Area at ({rx}, {ry})")
            await page.mouse.click(rx, ry)
            await asyncio.sleep(3)

            # Automatically close ad-tabs that open on click
            if len(page.context.pages) > 1:
                log.info("  🚫 Closing ad popup...")
                for p in page.context.pages:
                    if p != page: await p.close()
                await page.mouse.click(rx, ry)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Extraction Error: {str(e)[:40]}")
        return None

async def run():
    log.info("📡 Fetching event schedule from API...")
    try:
        events = requests.get(f"{API_BASE}/event", headers=HEADERS, timeout=15).json()
    except Exception as e:
        log.error(f"API Connection Error: {e}")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # Note: Added --disable-blink-features to further hide automation
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", 
            "--disable-web-security",
            "--disable-blink-features=AutomationControlled"
        ])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent=HEADERS["User-Agent"]
        )

        # Limits to 12 most recent events to stay within the 15-minute GitHub Action timeout
        for i, event in enumerate(events[:12], 1):
            title = event.get("title", "Unknown Match")
            eid = event.get("id")
            log.info(f"\n🎯 [{i}/12] Processing: {title}")

            try:
                sources = requests.get(f"{API_BASE}/source/{eid}", headers=HEADERS).json()
            except:
                continue

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
                log.info(f"  ✅ SUCCESSFULLY ADDED")
            else:
                log.info(f"  ❌ FAILED TO EXTRACT")
            
            await page.close()

        await browser.close()

    # Save the results to the file tracked by your YAML workflow
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Workflow Complete. Total Streams: {success_count}")

if __name__ == "__main__":
    asyncio.run(run())
