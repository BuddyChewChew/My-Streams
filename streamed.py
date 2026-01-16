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

    # Intercept network requests to find the .m3u8
    async def handle_request(request):
        nonlocal captured_url
        url = request.url
        if ".m3u8" in url and not captured_url:
            # Exclude typical tracking/ads that might use m3u8
            if "telemetry" not in url.lower() and "analytics" not in url.lower():
                captured_url = url
                log.info(f"      ⚡ Captured: {url[:50]}...")

    page.on("request", handle_request)

    try:
        log.info(f"   ↳ Loading: {embed_url}")
        # Stealth and headers to avoid detection
        await page.goto(embed_url, wait_until="load", timeout=45000)
        await asyncio.sleep(5) 

        # The "Click to Play" triggers. We try common play button selectors.
        play_selectors = ["button.vjs-big-play-button", ".play-button", "video", "canvas", ".player-poster"]
        
        clicked = False
        for selector in play_selectors:
            if await page.is_visible(selector):
                await page.click(selector)
                log.info(f"      🖱️ Clicked: {selector}")
                clicked = True
                break
        
        if not clicked:
            # Absolute fallback: Click the center of the video area
            await page.mouse.click(640, 360)
            log.info("      🖱️ Center-click fallback")

        # Wait for the background XHR to fire after the click
        await asyncio.sleep(10)
        return captured_url

    except Exception as e:
        log.error(f"      ⚠️ Error: {str(e)[:50]}")
        return None
    finally:
        await page.close()

async def main():
    log.info("📡 Fetching matches from API...")
    try:
        r = requests.get(API_URL, timeout=10)
        matches = r.json()
    except:
        log.error("❌ Failed to fetch matches.")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        # Setup context with realistic resolution and User-Agent
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # We limit to 10 matches to ensure the GitHub Action stays under the time limit
        for i, match in enumerate(matches[:10], 1):
            title = match.get("title", "Unknown Event")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}] {title}")

            found_m3u8 = None
            for src in sources:
                # Construct the embedsports URL you identified
                s_id = src.get("id")
                if s_id:
                    embed_url = f"https://embedsports.top/embed/admin/{s_id}/1"
                    found_m3u8 = await get_stream_link(context, embed_url)
                    if found_m3u8: break
            
            if found_m3u8:
                playlist.append(f'#EXTINF:-1, {title}\n{found_m3u8}')
                success += 1
            else:
                log.info("   ❌ No stream captured.")

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Done! Total: {success}")

if __name__ == "__main__":
    asyncio.run(main())
