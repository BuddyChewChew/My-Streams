import asyncio
import requests
import logging
import random
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Set up logging to match the format in your GitHub Action logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

API_BASE = "https://a.streamed.pk/api"
# Enhanced headers to bypass blocks that cause "Expecting value: line 1 column 1" errors
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://streamed.pk/",
    "Origin": "https://streamed.pk",
}

async def extract_m3u8(page, embed_url):
    """Uses Playwright to capture the .m3u8 stream from a specific embed URL."""
    found_url = None
    stealth = Stealth()
    
    async def handle_route(route):
        nonlocal found_url
        url = route.request.url
        # Block heavy tracking to speed up the GitHub runner
        if any(x in url for x in ["doubleclick", "analytics", "telemetry", "usrpubtrk"]):
            await route.abort()
        elif ".m3u8" in url and not found_url:
            # Avoid telemetry streams; grab the actual match stream
            if "telemetry" not in url.lower() and "jwpltx" not in url.lower():
                found_url = url
                log.info(f"  ⚡ Captured: {url[:65]}...")
            await route.continue_()
        else:
            await route.continue_()

    await page.route("**/*", handle_route)

    try:
        await stealth.apply_stealth_async(page)
        # Set the referer to the provider's domain for access
        parsed = urlparse(embed_url)
        await page.set_extra_http_headers({"Referer": f"{parsed.scheme}://{parsed.netloc}/"})
        
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(6)

        # Trigger the player via simulated mouse clicks
        for _ in range(3):
            if found_url: break
            await page.mouse.click(640 + random.randint(-20, 20), 360 + random.randint(-20, 20))
            await asyncio.sleep(4)
            # Close popup ad tabs immediately
            if len(page.context.pages) > 1:
                log.info("  🚫 Closing ad-tab...")
                for p in page.context.pages:
                    if p != page: await p.close()

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Playwright Error: {str(e)[:50]}")
        return None

async def run():
    log.info("📡 Fetching Live Matches...")
    try:
        # Step 1: Use the Live Matches endpoint you found
        response = requests.get(f"{API_BASE}/matches/live", headers=HEADERS, timeout=20)
        if response.status_code != 200:
            log.error(f"❌ API Error: Received status {response.status_code}")
            return
        matches = response.json()
    except Exception as e:
        log.error(f"❌ API Error: {e}. The site may be blocking the Action runner IP.")
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

        # Process the first 10 live matches
        for i, match in enumerate(matches[:10], 1):
            title = match.get("title", "Match")
            match_id = match.get("id")
            log.info(f"\n🎯 [{i}/10] {title}")

            # Step 2: Get sources for the specific match
            try:
                src_resp = requests.get(f"{API_BASE}/source/{match_id}", headers=HEADERS, timeout=10)
                sources_list = src_resp.json()
            except: continue

            page = await context.new_page()
            found_stream = None

            # Step 3: Iterate through provider-specific endpoints (Alpha, Bravo, etc.)
            for source_obj in sources_list:
                provider = source_obj.get("source", "").lower() # e.g., 'delta'
                sid = source_obj.get("id")
                
                if not provider or not sid: continue
                
                try:
                    # Construct provider URL: /api/stream/[provider]/[id]
                    stream_api_url = f"{API_BASE}/stream/{provider}/{sid}"
                    res = requests.get(stream_api_url, headers=HEADERS, timeout=10).json()
                    
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
            
            await page.close()

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Done. Saved {success} streams to StreamedSU.m3u8")

if __name__ == "__main__":
    asyncio.run(run())
