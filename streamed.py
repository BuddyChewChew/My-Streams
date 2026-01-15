import asyncio
import re
import requests
import logging
from datetime import datetime
from playwright.async_api import async_playwright

# Logging Setup
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
            if "prd.jwpltx.com" not in request.url and "telemetry" not in request.url:
                found_url = request.url
                log.info(f"  ⚡ Captured: {found_url[:70]}...")

    page.on("request", handle_request)

    try:
        # 1. Bypass "Cannot GET" and Load
        await page.set_extra_http_headers({"Referer": "https://streami.su/"})
        await page.goto(embed_url, wait_until="networkidle", timeout=25000)
        await asyncio.sleep(4)

        # 2. Try to find the actual Play button selector first
        play_selectors = [".jw-display-icon-container", ".vjs-big-play-button", "button.play", ".plyr__play-large"]
        clicked = False
        for selector in play_selectors:
            try:
                if await page.is_visible(selector, timeout=2000):
                    await page.click(selector)
                    clicked = True
                    break
            except: continue

        # 3. If no selector found, use coordinate clicking
        if not clicked:
            await page.mouse.click(320, 240)
        
        log.info("  👆 Interaction 1 (Start/Ad)")
        await asyncio.sleep(3)

        # 4. Clean up any Ad tabs
        for p in page.context.pages:
            if p != page: await p.close()

        # 5. Final click to trigger the stream
        await page.mouse.click(320, 240)
        log.info("  ▶️ Interaction 2 (Triggering Stream)")

        # 6. Wait for capture
        for _ in range(30):
            if found_url: break
            await asyncio.sleep(0.5)

        # Fallback HTML Scan
        if not found_url:
            content = await page.content()
            match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', content)
            if match:
                found_url = match.group(1)
                log.info("  🔎 Found via HTML Regex")

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Extract Error: {str(e)[:50]}")
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
        log.info("No live matches.")
        return

    playlist = ["#EXTM3U"]
    success_count = 0

    async with async_playwright() as p:
        # LAUNCH WITH STEALTH ARGUMENTS
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent=CUSTOM_HEADERS["User-Agent"],
            viewport={'width': 1280, 'height': 720}
        )

        for i, match in enumerate(matches, 1):
            title = match.get("title", "Unknown")
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
                playlist.append(f'#EXTINF:-1, {title}')
                playlist.append(f'#EXTVLCOPT:http-referrer={CUSTOM_HEADERS["Referer"]}')
                playlist.append(f'#EXTVLCOPT:http-user-agent={CUSTOM_HEADERS["User-Agent"]}')
                playlist.append(stream_found)
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
