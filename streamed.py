import asyncio
import re
import requests
import logging
from datetime import datetime
from playwright.async_api import async_playwright

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
}

FALLBACK_LOGOS = {
    "american football": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/nfl.png?raw=true",
    "football": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/football.png?raw=true",
    "fight": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/mma.png?raw=true",
    "basketball": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/nba.png?raw=true",
    "motor sports": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/f1.png?raw=true",
    "darts": "https://github.com/BuddyChewChew/My-Streams/blob/main/Logos/sports/darts2.png?raw=true",
    "tennis": "http://drewlive24.duckdns.org:9000/Logos/Tennis-2.png",
    "rugby": "http://drewlive24.duckdns.org:9000/Logos/Rugby.png",
    "cricket": "http://drewlive24.duckdns.org:9000/Logos/Cricket.png",
    "golf": "http://drewlive24.duckdns.org:9000/Logos/Golf.png",
    "other": "http://drewlive24.duckdns.org:9000/Logos/DrewLiveSports.png"
}

TV_IDS = {
    "baseball": "MLB.Baseball.Dummy.us",
    "fight": "PPV.EVENTS.Dummy.us",
    "american football": "Football.Dummy.us",
    "afl": "AUS.Rules.Football.Dummy.us",
    "football": "Soccer.Dummy.us",
    "basketball": "Basketball.Dummy.us",
    "hockey": "NHL.Hockey.Dummy.us",
    "tennis": "Tennis.Dummy.us",
    "darts": "Darts.Dummy.us",
    "motor sports": "Racing.Dummy.us",
    "rugby": "Rugby.Dummy.us",
    "cricket": "Cricket.Dummy.us",
    "other": "Sports.Dummy.us"
}

total_matches = 0
total_embeds = 0
total_streams = 0
total_failures = 0


def strip_non_ascii(text: str) -> str:
    """Remove emojis and non-ASCII characters."""
    if not text:
        return ""
    return re.sub(r"[^\x00-\x7F]+", "", text)


def get_all_matches():
    endpoints = ["live"]
    all_matches = []
    for ep in endpoints:
        try:
            log.info(f"📡 Fetching {ep} matches...")
            res = requests.get(f"https://streami.su/api/matches/{ep}", timeout=10)
            res.raise_for_status()
            data = res.json()
            log.info(f"✅ {ep}: {len(data)} matches")
            all_matches.extend(data)
        except Exception as e:
            log.warning(f"⚠️ Failed fetching {ep}: {e}")
    log.info(f"🎯 Total matches collected: {len(all_matches)}")
    return all_matches


def get_embed_urls_from_api(source):
    try:
        s_name, s_id = source.get("source"), source.get("id")
        if not s_name or not s_id:
            return []
        res = requests.get(f"https://streami.su/api/stream/{s_name}/{s_id}", timeout=6)
        res.raise_for_status()
        data = res.json()
        return [d.get("embedUrl") for d in data if d.get("embedUrl")]
    except Exception:
        return []


async def extract_m3u8(page, embed_url):
    global total_failures
    found = None
    try:
        async def on_request(request):
            nonlocal found
            if ".m3u8" in request.url and not found:
                if "prd.jwpltx.com" in request.url:
                    return
                found = request.url
                log.info(f"  ⚡ Stream: {found}")

        page.on("request", on_request)
        await page.goto(embed_url, wait_until="domcontentloaded", timeout=5000)
        await page.bring_to_front()
        selectors = [
            "div.jw-icon-display[role='button']",
            ".jw-icon-playback",
            ".vjs-big-play-button",
            ".plyr__control",
            "div[class*='play']",
            "div[role='button']",
            "button",
            "canvas"
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click(timeout=300)
                    break
            except:
                continue

        try:
            await page.mouse.click(200, 200)
            log.info("  👆 First click triggered ad")
            pages_before = page.context.pages
            new_tab = None
            for _ in range(12):
                pages_now = page.context.pages
                if len(pages_now) > len(pages_before):
                    new_tab = [p for p in pages_now if p not in pages_before][0]
                    break
                await asyncio.sleep(0.25)
            if new_tab:
                try:
                    await asyncio.sleep(0.5)
                    url = (new_tab.url or "").lower()
                    log.info(f"  🚫 Forcing close on ad tab: {url if url else '(blank/new)'}")
                    await new_tab.close()
                except Exception:
                    log.info("  ⚠️ Ad tab close failed")
            await asyncio.sleep(1)
            await page.mouse.click(200, 200)
            log.info("  ▶️ Second click started player")
        except Exception as e:
            log.warning(f"⚠️ Momentum click sequence failed: {e}")

        for _ in range(4):
            if found:
                break
            await asyncio.sleep(0.25)

        if not found:
            html = await page.content()
            matches = re.findall(r'https?://[^\s\"\'<>]+\.m3u8(?:\?[^\"\'<>]*)?', html)
            if matches:
                found = matches[0]
                log.info(f"  🕵️ Fallback: {found}")

        return found
    except Exception as e:
        total_failures += 1
        log.warning(f"⚠️ {embed_url} failed: {e}")
        return None


def validate_logo(url, category):
    cat = (category or "other").lower().replace("-", " ").strip()
    fallback = FALLBACK_LOGOS.get(cat, FALLBACK_LOGOS["other"])
    if url:
        try:
            res = requests.head(url, timeout=2)
            if res.status_code in (200, 302):
                return url
        except Exception:
            pass
    return fallback


def build_logo_url(match):
    cat = (match.get("category") or "other").strip()
    teams = match.get("teams") or {}
    for side in ["away", "home"]:
        badge = teams.get(side, {}).get("badge")
        if badge:
            url = f"https://streami.su/api/images/badge/{badge}.webp"
            return validate_logo(url, cat), cat
    if match.get("poster"):
        url = f"https://streami.su/api/images/proxy/{match['poster']}.webp"
        return validate_logo(url, cat), cat
    return validate_logo(None, cat), cat


async def process_match(index, match, total, ctx):
    global total_embeds, total_streams
    title = strip_non_ascii(match.get("title", "Unknown Match"))
    log.info(f"\n🎯 [{index}/{total}] {title}")
    sources = match.get("sources", [])
    match_embeds = 0
    page = await ctx.new_page()
    for s in sources:
        embed_urls = get_embed_urls_from_api(s)
        total_embeds += len(embed_urls)
        match_embeds += len(embed_urls)
        if not embed_urls:
            continue
        log.info(f"  ↳ {len(embed_urls)} embed URLs")
        for i, embed in enumerate(embed_urls, start=1):
            log.info(f"     • ({i}/{len(embed_urls)}) {embed}")
            m3u8 = await extract_m3u8(page, embed)
            if m3u8:
                total_streams += 1
                log.info(f"     ✅ Stream OK for {title}")
                await page.close()
                return match, m3u8
    await page.close()
    log.info(f"     ❌ No working streams ({match_embeds} embeds)")
    return match, None


async def generate_playlist():
    global total_matches
    matches = get_all_matches()
    total_matches = len(matches)
    if not matches:
        log.warning("❌ No matches found.")
        return "#EXTM3U\n"

    content = ["#EXTM3U"]
    success = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome-beta")
        ctx = await browser.new_context(extra_http_headers=CUSTOM_HEADERS)
        sem = asyncio.Semaphore(2)

        async def worker(idx, m):
            async with sem:
                return await process_match(idx, m, total_matches, ctx)

        for i, m in enumerate(matches, 1):
            match, url = await worker(i, m)
            if not url:
                continue

            logo, raw_cat = build_logo_url(match)
            base_cat = (raw_cat or "other").strip().replace("-", " ").lower()
            display_cat = strip_non_ascii(base_cat.title())
            tv_id = TV_IDS.get(base_cat, TV_IDS["other"])
            title = strip_non_ascii(match.get("title", "Untitled"))

            content.append(
                f'#EXTINF:-1 tvg-id="{tv_id}" tvg-name="{title}" '
                f'tvg-logo="{logo or FALLBACK_LOGOS["other"]}" group-title="StreamedSU - {display_cat}",{title}'
            )
            content.append(f'#EXTVLCOPT:http-origin={CUSTOM_HEADERS["Origin"]}')
            content.append(f'#EXTVLCOPT:http-referrer={CUSTOM_HEADERS["Referer"]}')
            content.append(f'#EXTVLCOPT:user-agent={CUSTOM_HEADERS["User-Agent"]}')
            content.append(url)
            success += 1

        await browser.close()

    log.info(f"\n🎉 {success} working streams written to playlist.")
    return "\n".join(content)


if __name__ == "__main__":
    start = datetime.now()
    log.info("🚀 Starting StreamedSU scrape run (LIVE only)...")
    playlist = asyncio.run(generate_playlist())
    with open("StreamedSU.m3u8", "w", encoding="utf-8") as f:
        f.write(playlist)
    end = datetime.now()
    duration = (end - start).total_seconds()
    log.info("\n📊 FINAL SUMMARY ------------------------------")
    log.info(f"🕓 Duration: {duration:.2f} sec")
    log.info(f"📺 Matches:  {total_matches}")
    log.info(f"🔗 Embeds:   {total_embeds}")
    log.info(f"✅ Streams:  {total_streams}")
    log.info(f"❌ Failures: {total_failures}")
    log.info("------------------------------------------------")
