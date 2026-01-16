import asyncio
import re
import requests
import logging
from playwright.async_api import async_playwright

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://streami.su/"
}

async def extract_m3u8(page, embed_url):
    found_url = None
    
    async def intercept_request(request):
        nonlocal found_url
        if ".m3u8" in request.url and not found_url:
            if "telemetry" not in request.url and "prd.jwpltx" not in request.url:
                found_url = request.url
                log.info(f"  ⚡ Captured: {found_url[:60]}...")

    page.on("request", intercept_request)

    try:
        await page.set_extra_http_headers({"Referer": "https://streami.su/"})
        await page.goto(embed_url, wait_until="load", timeout=30000)
        await asyncio.sleep(5)

        # Bypass overlays with a smart click
        await page.mouse.click(640, 360)
        log.info("  👆 Interaction 1 (Ad/Overlay)")
        await asyncio.sleep(2)

        # Close popups
        for p in page.context.pages:
            if p != page: await p.close()

        # Trigger Playback
        await page.mouse.dblclick(640, 360)
        log.info("  ▶️ Interaction 2 (Start Stream)")

        for _ in range(25):
            if found_url: break
            await asyncio.sleep(1)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Page error: {str(e)[:50]}")
        return None

async def run():
    try:
        res = requests.get("https://streami.su/api/matches/live", headers=HEADERS, timeout=10)
        matches = res.json()
    except: return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # Launch with automation bypass
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])

        for i, match in enumerate(matches[:15], 1):
            title = match.get("title", "Unknown")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}/{len(matches)}] {title}")

            page = await context.new_page()
            stream_found = None

            for source in sources:
                try:
                    s_name, s_id = source.get("source"), source.get("id")
                    e_res = requests.get(f"https://streami.su/api/stream/{s_name}/{s_id}", headers=HEADERS).json()
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

    # Save with the EXACT filename the YML is looking for
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Finished. {success_count} streams added.")

if __name__ == "__main__":
    asyncio.run(run())
