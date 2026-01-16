import asyncio
import requests
import logging
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

API_URL = "https://streami.su/api/matches/all"

async def get_stream_link(context, embed_url):
    page = await context.new_page()
    captured_url = None

    # Sniffer for the epicquesthero.com link you found
    async def handle_request(request):
        nonlocal captured_url
        url = request.url
        if ".m3u8" in url and not captured_url:
            # We explicitly allow links from the host you discovered
            if "epicquesthero.com" in url or "m3u8" in url.lower():
                if "jwpltx" not in url.lower():
                    captured_url = url
                    log.info(f"      ✨ SUCCESS: {url[:60]}...")

    page.on("request", handle_request)

    try:
        log.info(f"   ↳ Loading: {embed_url}")
        
        # We set the User-Agent and Referer to match your successful manual test
        await page.set_extra_http_headers({
            "Referer": "https://exposestrat.com/",
            "Origin": "https://exposestrat.com"
        })

        await page.goto(embed_url, wait_until="load", timeout=45000)
        
        # Wait for Autoplay (very common on epicquesthero sources)
        await asyncio.sleep(12) 
        if captured_url: return captured_url

        # Click interaction if autoplay fails
        log.info("      🖱️ Triggering manual click...")
        await page.mouse.click(640, 360)
        
        await asyncio.sleep(15) 
        return captured_url

    except Exception as e:
        log.error(f"      ⚠️ Error: {str(e)[:40]}")
        return None
    finally:
        await page.close()

async def main():
    log.info("📡 Starting Scraper...")
    try:
        r = requests.get(API_URL, timeout=15)
        matches = r.json()
    except: return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-web-security"])
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
                    # Target the admin embed you confirmed works
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
    log.info(f"\n🎉 Completed. Captured: {success}")

if __name__ == "__main__":
    asyncio.run(main())
