import asyncio
import re
import requests
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# Logging Setup integrated from job-logs.txt [cite: 360, 427]
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
    
    async def handle_request(request):
        nonlocal found_url
        if ".m3u8" in request.url and not found_url:
            # Filter out known analytics/player provider URLs
            if "prd.jwpltx.com" not in request.url:
                found_url = request.url
                log.info(f"  ⚡ Captured: {found_url[:60]}...")

    page.on("request", handle_request)

    try:
        # Prevent "Cannot GET" by setting specific Referer for the target domain
        await page.set_extra_http_headers({"Referer": "https://streami.su/"})
        await page.goto(embed_url, wait_until="load", timeout=20000)
        await asyncio.sleep(3)

        async def try_click_player():
            # Standard player centers for common sources (Charlie/Delta) [cite: 386, 427]
            await page.mouse.click(320, 240)
            for frame in page.frames:
                try:
                    await frame.click("body", timeout=500, position={"x": 320, "y": 240})
                except:
                    continue

        # First Click: Often triggers a popup ad [cite: 387, 427]
        await try_click_player()
        log.info("  👆 Interaction 1 (Ad Trigger)")
        await asyncio.sleep(2)

        # Close any spawned ad tabs [cite: 428]
        for p in page.context.pages:
            if p != page: await p.close()

        # Second Click: Triggers actual playback [cite: 429]
        await try_click_player()
        log.info("  ▶️ Interaction 2 (Play Trigger)")

        # Poll for network capture
        for _ in range(20):
            if found_url: break
            await asyncio.sleep(0.5)

        # Fallback: HTML Content Scan
        if not found_url:
            content = await page.content()
            match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', content)
            if match:
                found_url = match.group(1)
                log.info("  🔎 Captured via HTML Scan")

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Page error: {str(e)[:50]}")
        return None

def get_matches():
    try:
        res = requests.get("https://streami.su/api/matches/live", headers=CUSTOM_HEADERS, timeout=10)
        return res.json()
    except: return []

def get_embeds(source):
    try:
        s_name, s_id = source.get("source"), source.get("id")
        res = requests.get(f"https://streami.su/api/stream/{s_name}/{s_id}", headers=CUSTOM_HEADERS, timeout=10)
        return [d.get("embedUrl") for d in res.json() if d.get("embedUrl")]
    except: return []

async def run():
    matches = get_matches()
    if not matches: 
        log.error("No live matches found.")
        return

    playlist = ["#EXTM3U"]
    success = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=CUSTOM_HEADERS["User-Agent"],
            viewport={'width': 1280, 'height': 720}
        )

        for i, match in enumerate(matches, 1):
            title = match.get("title", "Unknown")
            # Re-integrating metadata for better M3U experience
            group = match.get("category", "Sports")
            logo = match.get("logo", "")
            
            sources = match.get("sources", [])
            log.info(f"\n🎯 [{i}/{len(matches)}] {title}")

            if not sources: continue
            
            stream_found = None
            page = await context.new_page()

            for source in sources:
                embed_urls = get_embeds(source)
                for url in embed_urls:
                    log.info(f"  ↳ Probing: {url[:50]}...")
                    stream_found = await extract_m3u8(page, url)
                    if stream_found: break
                if stream_found: break

            if stream_found:
                # Integrated M3U8 tags for Logos and Groups
                playlist.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}", {title}')
                playlist.append(f'#EXTVLCOPT:http-referrer={CUSTOM_HEADERS["Referer"]}')
                playlist.append(f'#EXTVLCOPT:http-user-agent={CUSTOM_HEADERS["User-Agent"]}')
                playlist.append(stream_found)
                success += 1
                log.info(f"  ✅ SUCCESS: {title}") [cite: 430]
            else:
                log.info(f"  ❌ FAILED: {title}")

            await page.close()

        await browser.close()

    # Save final playlist
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info(f"\n🎉 Done. {success} streams added.")

if __name__ == "__main__":
    asyncio.run(run())
