import asyncio
import requests
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scraper")

API_URL = "https://streami.su/api/matches/all"

async def get_stream_link(context, embed_url):
    page = await context.new_page()
    captured_url = None

    # Injecting headers found in your DevTools to bypass the handshake security
    async def intercept_headers(route):
        headers = {
            **route.request.headers,
            "Referer": embed_url,
            "Origin": "https://embedhd.org",
            "Sec-Fetch-Site": "same-origin",
        }
        await route.continue_(headers=headers)

    await page.route("**/*", intercept_headers)

    async def handle_request(request):
        nonlocal captured_url
        url = request.url
        if ".m3u8" in url and not captured_url:
            if "epicquesthero" in url or "m3u8" in url.lower():
                if "jwpltx" not in url.lower():
                    captured_url = url
                    log.info(f"      ✨ Captured: {url[:50]}...")

    page.on("request", handle_request)

    try:
        await page.goto(embed_url, wait_until="load", timeout=45000)
        await asyncio.sleep(12) 
        if not captured_url:
            # Fallback: Physical click to trigger the XHR
            await page.mouse.click(640, 360)
            await asyncio.sleep(12) 
        return captured_url
    except:
        return None
    finally:
        await page.close()

async def main():
    log.info("📡 Starting Hourly TiviMate Scraper...")
    try:
        r = requests.get(API_URL, timeout=15)
        matches = r.json()
    except: return

    # TiviMate requires these headers passed in the playlist string
    playlist = ["#EXTM3U"]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        # Matching your Firefox 147 User-Agent
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0"
        context = await browser.new_context(user_agent=ua)
        
        for i, match in enumerate(matches[:15], 1): # Top 15 live games
            title = match.get("title", "Event")
            sources = match.get("sources", [])
            if not sources: continue
            
            log.info(f"🎯 [{i}] {title}")
            s_id = sources[0].get("id")
            target = f"https://embedsports.top/embed/admin/{s_id}/1"
            
            link = await get_stream_link(context, target)
            
            if link:
                # TiviMate format: URL|Referer=...&User-Agent=...
                # Note: We use the Referer required by the stream host epicquesthero
                final_link = f"{link}|Referer=https://exposestrat.com/&User-Agent={ua}"
                playlist.append(f'#EXTINF:-1, {title}\n{final_link}')
            else:
                log.info("      ❌ Failed")

        await browser.close()

    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    log.info("🎉 Playlist Updated.")

if __name__ == "__main__":
    asyncio.run(main())
