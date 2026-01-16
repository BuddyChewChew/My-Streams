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

    # Listen for background requests
    async def handle_request(request):
        nonlocal captured_url
        url = request.url
        if ".m3u8" in url and not captured_url:
            if all(x not in url.lower() for x in ["telemetry", "analytics", "prd.jwpltx"]):
                captured_url = url
                log.info(f"      ⚡ Captured: {url[:50]}...")

    page.on("request", handle_request)

    try:
        log.info(f"   ↳ Loading: {embed_url}")
        # Realistic User-Agent is mandatory for embedsports.top
        await page.goto(embed_url, wait_until="load", timeout=45000)
        
        # --- Case 1: Wait for Autoplay ---
        await asyncio.sleep(7) 
        if captured_url:
            log.info("      ✨ Autoplay detected.")
            return captured_url

        # --- Case 2: Click to Play ---
        log.info("      🖱️ No autoplay. Attempting manual click...")
        # Common selectors for the play button
        selectors = ["button.vjs-big-play-button", ".play-button", "video", "canvas"]
        for selector in selectors:
            try:
                if await page.is_visible(selector):
                    await page.click(selector, force=True)
                    break
            except: continue
        
        # Final fallback: Click exactly in the middle of the player
        await page.mouse.click(640, 360)
        
        await asyncio.sleep(10) # Wait for stream to start after click
        return captured_url

    except Exception as e:
        log.error(f"      ⚠️ Error: {str(e)[:40]}")
        return None
    finally:
        await page.close()

async def main():
    log.info("📡 Fetching Matches...")
    try:
        r = requests.get(API_URL, timeout=10)
        matches = r.json()
    except:
        log.error("❌ API Failed.")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        # Use Chromium with Stealth
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Process first 10 live matches
        for i, match in enumerate(matches[:10], 1):
            title = match.get("title", "Unknown Event")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}] {title}")

            found_m3u8 = None
            for src in sources:
                s_id = src.get("id")
                if s_id:
                    # Target the embed URL directly
                    target = f"https://embedsports.top/embed/admin/{s_id}/1"
                    found_m3u8 = await get_stream_link(context, target)
                    if found_m3u8: break
            
            if found_m3u8:
                playlist.append(f'#EXTINF:-1, {title}\n{found_m3u8}')
                success += 1
            else:
                log.info("   ❌ FAILED")

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished! Streams Captured: {success}")

if __name__ == "__main__":
    asyncio.run(main())
