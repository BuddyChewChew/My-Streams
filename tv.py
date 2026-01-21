import asyncio
import urllib.parse
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

M3U8_FILE = "TheTVApp.m3u8"
BASE_URL = "https://thetvapp.to"
CHANNEL_LIST_URL = f"{BASE_URL}/tv"

SECTIONS_TO_APPEND = {
    "/nba": "NBA",
    "/mlb": "MLB",
    "/wnba": "WNBA",
    "/nfl": "NFL",
    "/ncaaf": "NCAAF",
    "/ncaab": "NCAAB",
    "/soccer": "Soccer",
    "/ppv": "PPV",
    "/events": "Events"
}

SPORTS_METADATA = {
    "MLB": {"tvg-id": "MLB.Baseball.Dummy.us", "logo": "http://drewlive24.duckdns.org:9000/Logos/Baseball-2.png"},
    "PPV": {"tvg-id": "PPV.EVENTS.Dummy.us", "logo": "http://drewlive24.duckdns.org:9000/Logos/PPV.png"},
    "NFL": {"tvg-id": "NFL.Dummy.us", "logo": "http://drewlive24.duckdns.org:9000/Logos/NFL.png"},
    "NCAAF": {"tvg-id": "NCAA.Football.Dummy.us", "logo": "http://drewlive24.duckdns.org:9000/Logos/CFB.png"},
    "NBA": {"tvg-id": "NBA.Basketball.Dummy.us", "logo": "http://drewlive24.duckdns.org:9000/Logos/NBA.png"}
}

def extract_real_m3u8(url: str):
    if "ping.gif" in url and "mu=" in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        mu = qs.get("mu", [None])[0]
        if mu:
            return urllib.parse.unquote(mu)
    if ".m3u8" in url:
        return url
    return None

async def scrape_tv_urls():
    urls = []
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("🔄 Loading /tv channel list...")
        await page.goto(CHANNEL_LIST_URL)
        links = await page.locator("ol.list-group a").all()
        hrefs_and_titles = [(await link.get_attribute("href"), await link.text_content())
                            for link in links if await link.get_attribute("href")]
        await page.close()

        for href, title_raw in hrefs_and_titles:
            full_url = BASE_URL + href
            title = " - ".join(line.strip() for line in title_raw.splitlines() if line.strip())
            print(f"🎯 Scraping TV page: {full_url}")

            for quality in ["SD", "HD"]:
                stream_url = None
                try:
                    new_page = await context.new_page()
                except Exception as e:
                    print(f"❌ Error creating new page for {full_url}: {e}")
                    continue

                async def handle_response(response):
                    nonlocal stream_url
                    real = extract_real_m3u8(response.url)
                    if real and not stream_url:
                        stream_url = real

                new_page.on("response", handle_response)
                try:
                    await new_page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    print(f"Timeout or navigation error at {full_url}: {e}")
                    await new_page.close()
                    continue

                try:
                    await new_page.get_by_text(f"Load {quality} Stream", exact=True).click(timeout=5000)
                except:
                    pass

                await asyncio.sleep(4)
                await new_page.close()

                if stream_url:
                    urls.append((stream_url, "TV", f"{title} {quality}"))
                    print(f"✅ {quality}: {stream_url}")
                else:
                    print(f"❌ {quality} not found")

        await browser.close()
    return urls

async def scrape_section_urls(context, section_path, group_name):
    urls = []
    section_url = BASE_URL + section_path
    print(f"\n📁 Loading section: {section_url}")

    try:
        page = await context.new_page()
        await page.goto(section_url, wait_until="domcontentloaded", timeout=60000)
        links = await page.locator("ol.list-group a").all()
    except Exception as e:
        print(f"Error loading section page {section_url}: {e}")
        return urls

    if not links:
        await page.close()
        return urls

    hrefs_and_titles = []
    for link in links:
        try:
            href = await link.get_attribute("href")
            title_raw = await link.text_content()
            if href and title_raw:
                title = " - ".join(line.strip() for line in title_raw.splitlines() if line.strip())
                hrefs_and_titles.append((href, title))
        except:
            continue

    await page.close()

    if not hrefs_and_titles:
        return urls

    for href, title in hrefs_and_titles:
        full_url = BASE_URL + href
        print(f"🎯 Scraping {group_name}: {title}")

        for quality in ["SD", "HD"]:
            stream_url = None
            try:
                new_page = await context.new_page()
            except Exception as e:
                print(f"❌ Error creating new page for {full_url}: {e}")
                continue

            async def handle_response(response):
                nonlocal stream_url
                real = extract_real_m3u8(response.url)
                if real and not stream_url:
                    stream_url = real

            new_page.on("response", handle_response)
            try:
                await new_page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"Timeout or navigation error at {full_url}: {e}")
                await new_page.close()
                continue
            try:
                await new_page.get_by_text(f"Load {quality} Stream", exact=True).click(timeout=5000)
                await asyncio.sleep(4)
            except:
                pass
            await new_page.close()

            if stream_url:
                urls.append((stream_url, group_name, f"{title} {quality}"))
                print(f"✅ {quality}: {stream_url}")
            else:
                print(f"❌ {quality} not found")
    return urls

async def scrape_all_sports_sections():
    all_urls = []
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context()

        for section_path, group_name in SECTIONS_TO_APPEND.items():
            try:
                section_urls = await scrape_section_urls(context, section_path, group_name)
                if section_urls:
                    all_urls.extend(section_urls)
            except Exception as e:
                print(f"Exception for {section_path}: {e}")
                continue

        await browser.close()
    return all_urls

def clean_m3u_header(lines):
    lines = [line for line in lines if not line.strip().startswith("#EXTM3U")]
    timestamp = int(datetime.utcnow().timestamp())
    lines.insert(0, f'#EXTM3U url-tvg="https://tvpass.org/epg.xml" # Updated: {timestamp}')
    return lines

def replace_tv_urls(lines, tv_urls):
    updated = []
    tv_idx = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("http") and tv_idx < len(tv_urls):
            group, title = tv_urls[tv_idx][1], tv_urls[tv_idx][2]
            if i > 0 and lines[i - 1].startswith("#EXTINF"):
                extinf = lines[i - 1]
                if "," in extinf:
                    parts = extinf.split(",")
                    parts[-1] = title
                    extinf = ",".join(parts)
                updated[-1] = extinf
            updated.append(tv_urls[tv_idx][0])
            tv_idx += 1
        else:
            updated.append(line)
        i += 1
    return updated

def refresh_sports_sections(lines, new_sports_urls):
    cleaned_lines = []
    i = 0
    sports_groups = set(SECTIONS_TO_APPEND.values())
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            group = line.split('group-title="')[1].split('"')[0] if 'group-title="' in line else ""
            if group.replace("TheTVApp - ", "") in sports_groups:
                i += 2
                continue
        cleaned_lines.append(line)
        i += 1

    for url, group, title in new_sports_urls:
        meta = SPORTS_METADATA.get(group, {})
        tvg_id = meta.get("tvg-id", "")
        logo = meta.get("logo", "")
        display_title = title.replace(",", " -")
        ext = (
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{title}" tvg-logo="{logo}" '
            f'group-title="TheTVApp - {group}",{display_title}'
            if tvg_id or logo else
            f'#EXTINF:-1 tvg-name="{title}" group-title="TheTVApp - {group}",{display_title}'
        )
        cleaned_lines.append(ext)
        cleaned_lines.append(url)
    return cleaned_lines

async def main():
    if not Path(M3U8_FILE).exists():
        print(f"❌ File not found: {M3U8_FILE}")
        return

    with open(M3U8_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    lines = clean_m3u_header(lines)

    print("🔧 Replacing /tv stream URLs...")
    tv_new_urls = await scrape_tv_urls()
    if tv_new_urls:
        lines = replace_tv_urls(lines, tv_new_urls)

    print("\n📦 Refreshing all sports sections...")
    sports_new_urls = await scrape_all_sports_sections()
    if sports_new_urls:
        lines = refresh_sports_sections(lines, sports_new_urls)

    with open(M3U8_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n✅ {M3U8_FILE} fully refreshed and working.")

if __name__ == "__main__":
    asyncio.run(main())
