import asyncio
import requests
import logging
import random
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Stealth import with fallback
try:
    from playwright_stealth import stealth_async as stealth
except ImportError:
    try:
        from playwright_stealth import stealth
    except ImportError:
        stealth = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

async def extract_m3u8(page, embed_url):
    found_url = None
    
    async def intercept_request(request):
        nonlocal found_url
        url = request.url
        if ".m3u8" in url and not found_url:
            if all(x not in url.lower() for x in ["telemetry", "logs", "analytics"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:70]}...")

    page.on("request", intercept_request)

    try:
        parsed_uri = urlparse(embed_url)
        base_domain = f"{parsed_uri.scheme}://{parsed_uri.netloc}/"
        
        await page.set_extra_http_headers({
            "Referer": base_domain,
            "Origin": base_domain
        })
        
        if stealth:
            await stealth(page)

        log.info(f"  ↳ Probing: {embed_url[:50]}...")
        await page.goto(embed_url, wait_until="load", timeout=45000)
        await asyncio.sleep(5)

        # --- THE INTERACTION STRATEGY ---
        # 1. Clear initial overlays
        log.info("  👆 Attempting to trigger player...")
        
        # We click a 3x3 grid in the center to ensure we hit the play button
        # regardless of how the player is sized or if there are invisible ads.
        search_grid = [
            (640, 360), (600, 360), (680, 360),
            (640, 320), (640, 400)
        ]

        for x, y in search_grid:
            if found_url: break
            await page.mouse.click(x, y)
            await asyncio.sleep(1.5)
            
            # Ad-Blocker Logic: Close any new tabs that opened from the click
            if len(page.context.pages) > 1:
                for p in page.context.pages:
                    if p != page:
                        await p.close()
                # Click again now that the ad is gone
                await page.mouse.click(x, y)

        # Final patience for the stream to initialize
        for _ in range(10):
            if found_url: break
            await asyncio.sleep(1)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Error: {str(e)[:30]}")
        return None

async def run():
    try:
        log.info("📡 Fetching matches...")
        res = requests.get("https://streami.su/api/matches/live", headers=HEADERS, timeout=15)
        matches = res.json()
    except Exception as e:
        log.error(f"API Error: {e}")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # Launch with 'real' browser flags
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent=HEADERS["User-Agent"]
        )

        # Process top 10 matches
        active_matches = matches[:10]
        for i, match in enumerate(active_matches, 1):
            title = match.get("title", "Unknown")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}/{len(active_matches)}] {title}")

            page = await context.new_page()
            stream_found = None

            for source in sources:
                try:
                    s_api = f"https://streami.su/api/stream/{source['source']}/{source['id']}"
                    e_res = requests.get(s_api, headers=HEADERS).json()
                    for d in e_res:
                        url = d.get("embedUrl")
                        if url:
                            stream_found = await extract_m3u8(page, url)
                            if stream_found: break
                except: continue
                if stream_found: break

            if stream_found:
                playlist.append(f'#EXTINF:-1, {title}\n{stream_found}')
                success_count += 1
                log.info(f"  ✅ SUCCESS")
            else:
                log.info(f"  ❌ FAILED")
            
            await page.close()
        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. {success_count} streams added.")

if __name__ == "__main__":
    asyncio.run(run())
