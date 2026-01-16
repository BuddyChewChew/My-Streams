import asyncio
import requests
import logging
import os
import random
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Robust stealth import handling
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
        # Capture the actual stream link
        if ".m3u8" in url and not found_url:
            if all(x not in url.lower() for x in ["telemetry", "prd.jwpltx", "omtrdc", "logs", "analytics", "doubleclick"]):
                found_url = url
                log.info(f"  ⚡ Captured: {url[:70]}...")

    page.on("request", intercept_request)

    try:
        if stealth:
            try:
                await stealth(page)
            except:
                pass
        
        # FIX: Dynamically set Referer based on the embed provider URL
        parsed_uri = urlparse(embed_url)
        base_domain = f"{parsed_uri.scheme}://{parsed_uri.netloc}/"
        
        await page.set_extra_http_headers({
            "Referer": base_domain,
            "Origin": base_domain
        })
        
        log.info(f"  ↳ Probing: {embed_url[:50]}...")
        # Wait for domcontentloaded to be faster than full 'load'
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=45000)
        
        # Give the player time to initialize
        await asyncio.sleep(6)

        # Interaction: Click three points in the center area to bypass overlays
        # This handles players where the play button might be slightly offset
        points = [(640, 360), (600, 360), (680, 360)]
        for x, y in points:
            if found_url: break
            await page.mouse.click(x, y)
            await asyncio.sleep(1)

        log.info("  👆 Interaction Sequence (Bypass)")

        # Close any popups that opened from the clicks
        for p in page.context.pages:
            if p != page: await p.close()

        # Final wait loop for the link to appear in traffic
        for _ in range(15):
            if found_url: break
            await asyncio.sleep(1)

        return found_url
    except Exception as e:
        log.warning(f"  ⚠️ Error: {str(e)[:40]}")
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
        
        browser_context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent=HEADERS["User-Agent"]
        )

        # Process top 12 matches for stability
        active_matches = matches[:12]
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
