import asyncio
import requests
import logging
from playwright.async_api import async_playwright

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

# integrated settings for stealth and referers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://streami.su/"
}

async def extract_m3u8(page, embed_url):
    found_url = None
    
    # Logic from HasData: Intercepting network requests directly
    async def intercept_network(request):
        nonlocal found_url
        if ".m3u8" in request.url and not found_url:
            # Filter out known analytics/tracking m3u8 files
            if "telemetry" not in request.url and "prd.jwpltx" not in request.url:
                found_url = request.url
                log.info(f"  ⚡ Captured: {found_url[:50]}...")

    page.on("request", intercept_network)

    try:
        # Integrated Referer logic to bypass 'Cannot GET' errors
        await page.set_extra_http_headers({"Referer": "https://streami.su/"})
        
        # Navigate and wait for content
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        # Interaction 1: Clear the 'fake' player overlay
        # We use a human-like click in the center of the player
        await page.mouse.click(640, 360)
        log.info("  👆 Interaction 1 (Ad/Bypass)")
        await asyncio.sleep(2)

        # Auto-close ad tabs logic from repo
        for p in page.context.pages:
            if p != page: await p.close()

        # Interaction 2: Force the video to start
        await page.mouse.dblclick(640, 360)
        log.info("  ▶️ Interaction 2 (Playback Trigger)")

        # Extended polling for the stream
        for _ in range(20):
            if found_url: break
            await asyncio.sleep(1)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Error: {str(e)[:40]}")
        return None

async def run():
    # Fetching live matches
    try:
        res = requests.get("https://streami.su/api/matches/live", headers=HEADERS, timeout=10)
        matches = res.json()
    except: return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # Launch with Stealth Args to bypass detection
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ])
        
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])

        for i, match in enumerate(matches[:15], 1): # Limit to 15 for speed
            title = match.get("title", "Unknown")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}/{len(matches)}] {title}")

            page = await context.new_page()
            stream_found = None

            for source in sources:
                s_name, s_id = source.get("source"), source.get("id")
                # Get the actual embed URLs
                try:
                    e_res = requests.get(f"https://streami.su/api/stream/{s_name}/{s_id}", headers=HEADERS).json()
                    embed_urls = [d.get("embedUrl") for d in e_res if d.get("embedUrl")]
                except: continue

                for url in embed_urls:
                    log.info(f"  ↳ Probing: {url[:45]}...")
                    stream_found = await extract_m3u8(page, url)
                    if stream_found: break
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
    log.info(f"\n🎉 Finished. {success_count} streams captured.")

if __name__ == "__main__":
    asyncio.run(run())
