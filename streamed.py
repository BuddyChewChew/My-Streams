import asyncio
import requests
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

API_URL = "https://streami.su/api/matches/all"

async def get_stream_link(context, embed_url):
    page = await context.new_page()
    captured_url = None

    # THE FIX: Dynamically set headers to match the EXACT page you are on
    async def intercept_headers(route):
        url = route.request.url
        headers = {
            **route.request.headers,
            "Referer": embed_url,
            "Origin": "https://embedhd.org",
            "Sec-Fetch-Site": "same-origin", # Matches your DevTools 'same-origin' requirement
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }
        await route.continue_(headers=headers)

    # Apply the logic to all requests on the page
    await page.route("**/*", intercept_headers)

    async def handle_request(request):
        nonlocal captured_url
        if ".m3u8" in request.url and not captured_url:
            if "epicquesthero" in request.url or "m3u8" in request.url.lower():
                captured_url = request.url
                log.info(f"      ✨ SUCCESS: {captured_url[:60]}...")

    page.on("request", handle_request)

    try:
        log.info(f"   ↳ Probing: {embed_url}")
        
        # Navigate using the browser version you used (Firefox/147)
        await page.goto(embed_url, wait_until="load", timeout=45000)
        
        # Long wait for the 200 OK handshake you saw in DevTools
        await asyncio.sleep(15) 
        if captured_url: return captured_url

        # Force trigger if autoplay is blocked
        log.info("      🖱️ Clicking player to force handshake...")
        await page.mouse.click(640, 360)
        
        await asyncio.sleep(15) 
        return captured_url

    except Exception as e:
        log.error(f"      ⚠️ Page Error: {str(e)[:40]}")
        return None
    finally:
        await page.close()

async def main():
    log.info("📡 Starting Same-Origin Mimicry Scraper...")
    try:
        r = requests.get(API_URL, timeout=15)
        matches = r.json()
    except: return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        # Launch with specific flags to allow cross-origin spoofing
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", 
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process"
        ])
        
        # Use the exact Firefox 147 User-Agent you provided
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0"
        )
        
        for i, match in enumerate(matches[:12], 1):
            title = match.get("title", "Event")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}] {title}")

            found = None
            for src in sources:
                s_id = src.get("id")
                if s_id:
                    # Construct the target URL correctly
                    target = f"https://embedsports.top/embed/admin/{s_id}/1"
                    found = await get_stream_link(context, target)
                    if found: break
            
            if found:
                playlist.append(f'#EXTINF:-1, {title}\n{found}')
                success += 1
            else:
                log.info("   ❌ FAILED")

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Process Complete. Total captured: {success}")

if __name__ == "__main__":
    asyncio.run(main())
