import asyncio
import requests
import logging
import random
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

API_BASE = "https://a.streamed.pk/api"
# Enhanced headers to bypass API-level bot detection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://streamed.pk/",
    "Origin": "https://streamed.pk",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

async def extract_m3u8(page, embed_url):
    found_url = None
    stealth = Stealth()
    
    async def handle_route(route):
        nonlocal found_url
        url = route.request.url
        
        # Block heavy tracking scripts to speed up loading and reduce footprint
        if any(x in url for x in ["doubleclick", "analytics", "telemetry", "usrpubtrk"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            if "telemetry" not in url.lower() and "jwpltx" not in url.lower():
                found_url = url
                log.info(f"  ⚡ Captured: {url[:65]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        await stealth.apply_stealth_async(page)
        
        # Set referer to the specific embed source
        parsed = urlparse(embed_url)
        await page.set_extra_http_headers({
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
        })
        
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(6)

        # Interaction loop to trigger player
        for _ in range(3):
            if found_url: break
            # Click near the center of the viewport
            await page.mouse.click(640 + random.randint(-20, 20), 360 + random.randint(-20, 20))
            await asyncio.sleep(4)
            
            # Close popup tabs triggered by the click
            if len(page.context.pages) > 1:
                log.info("  🚫 Closing ad-tab...")
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Playwright Error: {str(e)[:50]}")
        return None

async def run():
    log.info("📡 Fetching events...")
    try:
        response = requests.get(f"{API_BASE}/event", headers=HEADERS, timeout=20)
        # Check if we got a real JSON response or an HTML error page
        if response.status_code != 200:
            log.error(f"❌ API Error: Received status {response.status_code}")
            return
        events = response.json()
    except json.JSONDecodeError:
        log.error("❌ API Error: API returned HTML/text instead of JSON. The site might be under maintenance or blocking the runner IP.")
        return
    except Exception as e:
        log.error(f"❌ Connection Error: {e}")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled"
        ])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        # Process the first 10 live/upcoming events
        for i, event in enumerate(events[:10], 1):
            title = event.get("title", "Match")
            eid = event.get("id")
            log.info(f"\n🎯 [{i}/10] {title}")

            try:
                src_resp = requests.get(f"{API_BASE}/source/{eid}", headers=HEADERS, timeout=10)
                sources = src_resp.json()
            except:
                continue

            page = await context.new_page()
            found = None
            for s in sources:
                url = s.get("embedUrl")
                if url:
                    found = await extract_m3u8(page, url)
                    if found: break
            
            if found:
                playlist.append(f'#EXTINF:-1, {title}\n{found}')
                success += 1
            
            await page.close()

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Done. Saved {success} streams to StreamedSU.m3u8")

if __name__ == "__main__":
    asyncio.run(run())
