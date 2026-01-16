import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

async def capture_stream(context, url):
    page = await context.new_page()
    captured_m3u8 = None

    # This is the "Network Sniffer" - it watches every request the browser makes
    async def on_request(request):
        nonlocal captured_m3u8
        # We look for .m3u8, but ignore the common 'jwpltx' (player telemetry)
        if ".m3u8" in request.url and "jwpltx" not in request.url:
            if not captured_m3u8:
                captured_m3u8 = request.url
                log.info(f"      ✨ SUCCESS: {captured_m3u8[:70]}...")

    page.on("request", on_request)

    try:
        log.info(f"   ↳ Probing: {url}")
        # We use 'domcontentloaded' to start sniffing as early as possible
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Give it 15 seconds to autoplay and fire the network request
        for i in range(15):
            if captured_m3u8:
                return captured_m3u8
            await asyncio.sleep(1)
            
        # If no autoplay after 15s, try one "Emergency Click"
        log.info("      🖱️ No autoplay detected, trying emergency click...")
        await page.mouse.click(640, 360)
        await asyncio.sleep(10)
        
        return captured_m3u8
    except Exception as e:
        log.error(f"      ⚠️ Error: {e}")
        return None
    finally:
        await page.close()

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Test with the autoplay URL you provided
        url = "https://embedsports.top/embed/admin/19232/1"
        stream = await capture_stream(context, url)
        
        if stream:
            print(f"\nFINAL M3U8: {stream}")
            # Here you would save it to your .m3u8 file
        else:
            print("\n❌ Failed to capture.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
