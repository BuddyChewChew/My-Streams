import asyncio
import requests
import logging
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configure logging for GitHub Actions visibility
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# The data source for match IDs
API_URL = "https://streami.su/api/matches/all"

async def extract_stream(context, embed_url):
    page = await context.new_page()
    final_m3u8 = None

    # This function captures the ACTUAL stream after the handshake
    async def capture_network_traffic(request):
        nonlocal final_m3u8
        url = request.url
        # We look for .m3u8 but ignore telemetry (jwpltx)
        if ".m3u8" in url and "jwpltx" not in url.lower():
            if not final_m3u8:
                final_m3u8 = url
                log.info(f"      ⚡ Handshake Success: {url[:60]}...")

    page.on("request", capture_network_traffic)

    try:
        log.info(f"   ↳ Opening: {embed_url}")
        
        # We must set these headers to match your Chrome DevTools discovery
        await page.set_extra_http_headers({
            "Referer": "https://streamed.su/",
            "Origin": "https://streamed.su"
        })

        # Navigate to the player page
        await page.goto(embed_url, wait_until="load", timeout=45000)
        
        # Wait 10 seconds for Autoplay to trigger the HEAD request
        await asyncio.sleep(10)
        
        if final_m3u8:
            log.info("      ✨ Stream captured via autoplay.")
            return final_m3u8

        # If no autoplay, click the player to force the handshake
        log.info("      🖱️ No autoplay; clicking player to trigger stream...")
        # Common selectors for the embedhd player
        for selector in ["button.vjs-big-play-button", "video", "canvas", ".play-button"]:
            try:
                if await page.is_visible(selector):
                    await page.click(selector, force=True)
                    break
            except: continue
        
        # Fallback click in the center
        await page.mouse.click(640, 360)
        
        # Final wait for the XHR to fire
        await asyncio.sleep(12)
        return final_m3u8

    except Exception as e:
        log.error(f"      ⚠️ Page Error: {str(e)[:50]}")
        return None
    finally:
        await page.close()

async def main():
    log.info("📡 Fetching Matches from API...")
    try:
        r = requests.get(API_URL, timeout=15)
        matches = r.json()
    except Exception as e:
        log.error(f"❌ API Failure: {e}")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Stealthed context to avoid bot detection
        stealth = Stealth()
        
        # Process top 12 matches to stay within GitHub Action time limits
        for i, match in enumerate(matches[:12], 1):
            title = match.get("title", "Unknown Event")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}] {title}")

            captured = None
            for src in sources:
                s_id = src.get("id")
                if s_id:
                    # Construct URL: https://embedsports.top/embed/admin/{id}/1
                    target = f"https://embedsports.top/embed/admin/{s_id}/1"
                    captured = await extract_stream(context, target)
                    if captured: break
            
            if captured:
                playlist.append(f'#EXTINF:-1, {title}\n{captured}')
                success += 1
            else:
                log.info("   ❌ FAILED")

        await browser.close()

    # Save to file
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished! Total: {success}")

if __name__ == "__main__":
    asyncio.run(main())
