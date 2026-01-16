import asyncio
import requests
import logging
import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

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
            # Ignore telemetry and ads
            if all(x not in url for x in ["telemetry", "prd.jwpltx", "omtrdc", "logs"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:60]}...")

    page.on("request", intercept_request)

    try:
        await stealth_async(page)
        
        # Set referer specifically for the embed provider
        await page.set_extra_http_headers({"Referer": "https://streami.su/"})
        
        # 'load' is safer than 'networkidle' for streaming pages
        await page.goto(embed_url, wait_until="load", timeout=30000)
        await asyncio.sleep(5)

        # Interaction 1: Clear overlay
        await page.mouse.click(640, 360)
        log.info("  👆 Interaction 1 (Bypass)")
        await asyncio.sleep(2)

        # Close any popups that opened
        pages = page.context.pages
        for p in pages:
            if p != page: await p.close()

        # Interaction 2: Start playback
        if not found_url:
            await page.mouse.click(640, 360) 
            await asyncio.sleep(1)
            await page.mouse.dblclick(640, 360)
            log.info("  ▶️ Interaction 2 (Retry)")

        # Wait loop for the m3u8 to appear in network logs
        for _ in range(15):
            if found_url: break
            await asyncio.sleep(1)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Timeout/Error: {str(e)[:40]}")
        return None

async def run():
    try:
        res = requests.get("https://streami.su/api/matches/live", headers=HEADERS, timeout=10)
        matches = res.json()
    except Exception as e:
        log.error(f"Failed to fetch matches: {e}")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # Standard launch is more "bulletproof" for GitHub Actions than persistent_context
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        
        browser_context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent=HEADERS["User-Agent"]
        )

        # Process first 20 matches
        for i, match in enumerate(matches[:20], 1):
            title = match.get("title", "Unknown")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}/{len(matches[:20])}] {title}")

            page = await browser_context.new_page()
            stream_found = None

            for source in sources:
                try:
                    s_name, s_id = source.get("source"), source.get("id")
                    e_url = f"https://streami.su/api/stream/{s_name}/{s_id}"
                    e_res = requests.get(e_url, headers=HEADERS).json()
                    
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

    # Final Save
    output_file = "StreamedSU.m3u8"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. {success_count} streams added.")

if __name__ == "__main__":
    asyncio.run(run())
