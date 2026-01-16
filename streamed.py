import asyncio
import logging
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

async def capture_stream(browser_context, embed_url):
    page = await browser_context.new_page()
    found_m3u8 = None

    # Listen for the actual stream request in the background
    async def intercept_request(request):
        nonlocal found_m3u8
        if ".m3u8" in request.url and not found_m3u8:
            found_m3u8 = request.url
            log.info(f"   ⚡ Captured: {found_m3u8[:60]}...")

    page.on("request", intercept_request)

    try:
        log.info(f"   ↳ Opening: {embed_url}")
        # Move to the embed page
        await page.goto(embed_url, wait_until="load", timeout=30000)
        
        # 1. Wait for the play button to appear (site-specific selector)
        # Often these players use a large central div or a button with class 'vjs-big-play-button'
        play_selectors = [
            "button.vjs-big-play-button", 
            ".play-button", 
            "#player",
            "canvas" # Some modern players use canvas for interaction
        ]
        
        await asyncio.sleep(5) # Give the player time to initialize

        # 2. Simulate the human click to start the stream
        for selector in play_selectors:
            try:
                if await page.is_visible(selector):
                    await page.click(selector)
                    log.info(f"   🖱️ Clicked player element: {selector}")
                    break
            except:
                continue
        
        # Fallback: Just click the center of the screen
        await page.mouse.click(640, 360)
        
        # 3. Wait for the network request to fire
        await asyncio.sleep(10)
        
        return found_m3u8
    except Exception as e:
        log.error(f"   ❌ Error capturing stream: {e}")
        return None
    finally:
        await page.close()

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Using a realistic User-Agent is critical here
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Test with your specific URL
        test_url = "https://embedsports.top/embed/admin/ppv-new-york-knicks-vs-golden-state-warriors/1"
        stream = await capture_stream(context, test_url)
        
        if stream:
            print(f"\nFINAL M3U8 LINK: {stream}")
        else:
            print("\nFailed to find stream.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
