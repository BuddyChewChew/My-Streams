import asyncio
import requests
import logging
import os
from playwright.async_api import async_playwright
# Import the stealth module correctly
import playwright_stealth

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
        # Look for master.m3u8 or index.m3u8 but skip known ad/telemetry domains
        if ".m3u8" in url and not found_url:
            if all(x not in url.lower() for x in ["telemetry", "prd.jwpltx", "omtrdc", "logs", "doubleclick", "analytics"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:70]}...")

    page.on("request", intercept_request)

    try:
        # FIX: Call the function inside the module
        await playwright_stealth.stealth_async(page)
        
        await page.set_extra_http_headers({"Referer": "https://streami.su/"})
        
        # Increase timeout and use 'commit' for faster response capture
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=45000)
        
        # Interaction 1: Click to clear overlays/ads
        await asyncio.sleep(3)
        await page.mouse.click(640, 360)
        log.info("  👆 Interaction 1 (Bypass)")

        # Close any popups that opened from the first click
        for p in page.context.pages:
            if p != page: await p.close()

        # Interaction 2: Double click to trigger player play
        if not found_url:
            await asyncio.sleep(2)
            await page.mouse.dblclick(640, 360)
            log.info("  ▶️ Interaction 2 (Play Trigger)")

        # Wait loop to give the stream time to start
        for _ in range(20):
            if found_url: break
            await asyncio.sleep(1)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Error on {embed_url[:30]}: {str(e)[:40]}")
        return None

async def run():
    try:
        log.info("📡 Fetching live matches...")
        res = requests.get("https://streami.su/api/matches/live", headers=HEADERS, timeout=15)
        matches = res.json()
    except Exception as e:
        log.error(f"Failed to fetch matches: {e}")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security"
            ]
        )
        
        # Use a single context for all pages to mimic a real session
        browser_context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent=HEADERS["User-Agent"]
        )

        # Process first 15 matches to ensure we stay under GitHub time limits
        active_matches = matches[:15]
        for i, match in enumerate(active_matches, 1):
            title = match.get("title", "Unknown")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}/{len(active_matches)}] {title}")

            page = await browser_context.new_page()
            stream_found = None

            for source in sources:
                try:
                    s_name, s_id = source.get("source"), source.get("id")
                    s_api = f"https://streami.su/api/stream/{s_name}/{s_id}"
                    e_res = requests.get(s_api, headers=HEADERS).json()
                    
                    for d in e_res:
                        url = d.get("embedUrl")
                        if not url: continue
                        log.info(f"  ↳ Probing: {url[:50]}...")
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

    # Always write the file, even if empty, to satisfy the YAML check
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. {success_count} streams added.")

if __name__ == "__main__":
    asyncio.run(run())
