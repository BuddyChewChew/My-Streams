import asyncio
import re
import requests
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# Logging Configuration
logging.basicConfig(
    filename="scrape.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"))
logging.getLogger("").addHandler(console)
log = logging.getLogger("scraper")

CUSTOM_HEADERS = {
    "Origin": "https://embedsports.top",
    "Referer": "https://embedsports.top/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

async def extract_m3u8(page, embed_url):
    found_url = None
    
    # 1. Network Interception Listener
    async def handle_request(request):
        nonlocal found_url
        url = request.url
        if ".m3u8" in url and not found_url:
            if "prd.jwpltx.com" not in url and "telemetry" not in url:
                found_url = url
                log.info(f"  ⚡ Captured via Network: {url[:60]}...")

    page.on("request", handle_request)

    try:
        # 2. Navigate to page
        await page.goto(embed_url, wait_until="load", timeout=20000)
        await asyncio.sleep(2)

        # 3. Handle Ad-Click and Player Start
        # Click center of player
        await page.mouse.click(320, 240)
        log.info("  👆 First click (Ad/Start)")
        await asyncio.sleep(2)

        # Close any popups/ads
        pages = page.context.pages
        if len(pages) > 1:
            for p in pages[1:]:
                if p != page:
                    await p.close()

        # Click again to play
        await page.mouse.click(320, 240)
        log.info("  ▶️ Second click (Play)")

        # 4. Wait/Poll for URL
        for _ in range(20):
            if found_url: break
            await asyncio.sleep(0.5)

        # 5. Fallback: Search Page Content via Regex
        if not found_url:
            content = await page.content()
            match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', content)
            if match:
                found_url = match.group(1)
                log.info(f"  🔎 Captured via Regex: {found_url[:60]}...")

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Error: {str(e)[:50]}")
        return None

def get_live_matches():
    try:
        res = requests.get("https://streami.su/api/matches/live", headers=CUSTOM_HEADERS, timeout=10)
        return res.json()
    except Exception:
        return []

def get_embeds(source):
    try:
        s_name, s_id = source.get("source"), source.get("id")
        res = requests.get(f"https://streami.su/api/stream/{s_name}/{s_id}", headers=CUSTOM_HEADERS, timeout=10)
        return [d.get("embedUrl") for d in res.json() if d.get("embedUrl")]
    except:
        return []

async def run():
    matches = get_live_matches()
    if not matches:
        log.info("No live matches found.")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # Added arguments to look more like a real browser
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})

        for i, match in enumerate(matches, 1):
            title = match.get("title", "Unknown")
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}/{len(matches)}] {title}")

            if not sources:
                continue

            found_stream = None
            page = await context.new_page()

            # Try sources one by one
            for source in sources:
                embed_urls = get_embeds(source)
                for url in embed_urls:
                    log.info(f"  ↳ Trying: {url[:50]}...")
                    found_stream = await extract_m3u8(page, url)
                    if found_stream: break
                if found_stream: break

            if found_stream:
                playlist.append(f'#EXTINF:-1, {title}')
                playlist.append(f'#EXTVLCOPT:http-referrer={CUSTOM_HEADERS["Referer"]}')
                playlist.append(f'#EXTVLCOPT:http-user-agent={CUSTOM_HEADERS["User-Agent"]}')
                playlist.append(found_stream)
                success_count += 1
                log.info("  ✅ Success")
            else:
                log.info("  ❌ No stream found")

            await page.close()

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    
    log.info(f"\n🎉 Finished. Created playlist with {success_count} streams.")

if __name__ == "__main__":
    asyncio.run(run())
