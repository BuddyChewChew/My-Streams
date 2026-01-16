import asyncio
import requests
import logging
import random
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# New API Base
API_BASE = "https://a.streamed.pk/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://streamed.pk/",
    "Origin": "https://streamed.pk"
}

async def extract_m3u8(page, embed_url):
    found_url = None
    
    async def intercept_request(request):
        nonlocal found_url
        url = request.url
        if ".m3u8" in url and not found_url:
            if all(x not in url.lower() for x in ["telemetry", "logs", "prd.jwpltx", "analytics"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:70]}...")

    page.on("request", intercept_request)

    try:
        # Set Referer to match the embed provider
        parsed_uri = urlparse(embed_url)
        await page.set_extra_http_headers({
            "Referer": f"{parsed_uri.scheme}://{parsed_uri.netloc}/",
            "Origin": f"{parsed_uri.scheme}://{parsed_uri.netloc}"
        })
        
        await stealth_async(page)
        log.info(f"  ↳ Probing Player: {embed_url[:50]}...")
        
        # Go to embed and wait
        await page.goto(embed_url, wait_until="load", timeout=45000)
        await asyncio.sleep(6)

        # Multi-click strategy to bypass the "Ad-Overlay"
        center = (640, 360)
        for _ in range(2):
            if found_url: break
            await page.mouse.click(*center)
            await asyncio.sleep(2)
            # Close popups
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page: await p.close()
                await page.mouse.click(*center) # Re-click after closing ad

        return found_url
    except Exception:
        return None

async def run():
    log.info("📡 Fetching events from a.streamed.pk...")
    try:
        # Step 1: Get the live event list
        events_res = requests.get(f"{API_BASE}/event", headers=HEADERS, timeout=15)
        events = events_res.json()
    except Exception as e:
        log.error(f"Failed to fetch event list: {e}")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        # Process first 10 live events
        for i, event in enumerate(events[:10], 1):
            title = event.get("title", "Unknown Event")
            event_id = event.get("id")
            log.info(f"\n🎯 [{i}/10] {title}")

            # Step 2: Get sources for this specific event
            try:
                sources_res = requests.get(f"{API_BASE}/source/{event_id}", headers=HEADERS, timeout=10)
                sources = sources_res.json() # This returns a list of embed sources
            except:
                log.info("  ❌ Could not fetch sources for this event")
                continue

            page = await context.new_page()
            stream_found = None

            # Step 3: Loop through sources (HD, SD, etc.) until one works
            for source in sources:
                embed_url = source.get("embedUrl")
                if not embed_url: continue
                
                stream_found = await extract_m3u8(page, embed_url)
                if stream_found: break
            
            if stream_found:
                playlist.append(f'#EXTINF:-1, {title}\n{stream_found}')
                success_count += 1
                log.info(f"  ✅ SUCCESS")
            else:
                log.info(f"  ❌ FAILED")
            
            await page.close()

        await browser.close()

    # Save final M3U8
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. {success_count} streams added.")

if __name__ == "__main__":
    asyncio.run(run())
