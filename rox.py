import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from requests.exceptions import RequestException
import logging

BASE_URL = "https://roxiestreams.live"

TV_INFO = {
    "ppv": ("PPV.EVENTS.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/PPV.png"),
    "soccer": ("Soccer.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/Soccer.png"),
    "ufc": ("UFC.Fight.Pass.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/CombatSports2.png"),
    "fighting": ("PPV.EVENTS.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/Combat-Sports.png"),
    "nfl": ("Football.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/Maxx.png"),
    "f1": ("Racing.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/F1.png"),
    "motorsports": ("Racing.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/F1.png"),
    "wwe": ("PPV.EVENTS.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/WWE2.png"),
    "nba": ("NBA.Basketball.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/Basketball-2.png"),
    "mlb": ("MLB.Baseball.Dummy.us", "http://drewlive24.duckdns.org:9000/Logos/Baseball3.png")
}

DISCOVERY_KEYWORDS = list(TV_INFO.keys()) + ['streams']
SECTION_BLOCKLIST = ['olympia']

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': BASE_URL
})

M3U8_REGEX = re.compile(r'https?://[^\s"\'<>`]+\.m3u8')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def discover_sections(base_url):
    """
    Step 1: Scrapes the base_url to find main category links (e.g., /nba, /ufc).
    """
    logging.info(f"Discovering sections on {base_url}...")
    sections_found = []
    try:
        resp = SESSION.get(base_url, timeout=10)
        resp.raise_for_status()
    except RequestException as e:
        logging.error(f"Failed to fetch base URL {base_url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    discovered_urls = set()

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        title = a_tag.get_text(strip=True)

        if not href or href.startswith(('#', 'javascript:', 'mailto:')) or not title:
            continue

        abs_url = urljoin(base_url, href)

        if any(blocked in abs_url.lower() for blocked in SECTION_BLOCKLIST):
            pass
        elif (urlparse(abs_url).netloc == urlparse(base_url).netloc and
                any(keyword in abs_url.lower() for keyword in DISCOVERY_KEYWORDS) and
                abs_url not in discovered_urls):

            discovered_urls.add(abs_url)
            logging.info(f"  [Found] {title} -> {abs_url}")
            sections_found.append((abs_url, title))

    return sections_found

def discover_event_links(section_url):
    """
    Step 2: Visits an index page (like /nba) and finds all links
    to actual event pages (like /nba-streams-1).
    Returns a set of tuples: (event_url, event_title)
    """
    events = set()
    try:
        resp = SESSION.get(section_url, timeout=10)
        resp.raise_for_status()
    except RequestException as e:
        logging.warning(f"  Failed to fetch section page {section_url}: {e}")
        return events

    soup = BeautifulSoup(resp.text, 'html.parser')

    event_table = soup.find('table', id='eventsTable') 

    if not event_table:
        return events 

    for a_tag in event_table.find_all('a', href=True):
        href = a_tag['href']
        title = a_tag.get_text(strip=True)
        if not href or not title:
            continue

        abs_url = urljoin(section_url, href)

        if abs_url.startswith(BASE_URL):
            events.add((abs_url, title))

    return events

def extract_m3u8_links(page_url):
    """
    Step 3: Visits an event page and extracts all .m3u8 links from the raw HTML.
    """
    links = set()
    try:
        resp = SESSION.get(page_url, timeout=10)
        resp.raise_for_status()
        links.update(M3U8_REGEX.findall(resp.text))
    except RequestException as e:
        logging.warning(f"    Failed to fetch event page {page_url}: {e}")

    return links

def check_stream_status(m3u8_url):
    """
    Step 4: Validates a .m3u8 link with a HEAD request.
    """
    try:
        resp = SESSION.head(m3u8_url, timeout=5, allow_redirects=True)
        if resp.status_code == 200:
            return True
        else:
            logging.warning(f"    [BAD STATUS {resp.status_code}] {m3u8_url}")
            return False
    except RequestException:
        logging.info(f"    [DEAD LINK] {m3u8_url}")
        return False

def get_tv_info(url):
    """Matches a URL against the TV_INFO dict to get logo and ID."""
    for key, value in TV_INFO.items():
        if key in url.lower():
            return value
    return ("Unknown.Dummy.us", "")


def main():
    playlist_lines = ["#EXTM3U"]

    sections = list(discover_sections(BASE_URL))
    if not sections:
        logging.error("No sections discovered.")
        return

    logging.info(f"Found {len(sections)} sections. Scraping for events...")

    for section_url, section_title in sections:
        logging.info(f"\n--- Processing Section: {section_title} ({section_url}) ---")

        tv_id, logo = get_tv_info(section_url)

        event_links = discover_event_links(section_url)

        pages_to_scrape = set()

        if event_links:
            logging.info(f"  Found {len(event_links)} event sub-pages.")
            pages_to_scrape.update(event_links)
        else:
            logging.info(f"  No sub-pages found. Scraping as a direct event page.")
            pages_to_scrape.add((section_url, section_title))

        if not pages_to_scrape:
            logging.info("  No event pages to scrape for this section.")
            continue

        valid_count_for_section = 0

        for event_url, event_title in pages_to_scrape:
            logging.info(f"  Scraping: {event_title} ({event_url})")
            m3u8_links = extract_m3u8_links(event_url)

            if not m3u8_links:
                logging.info(f"    No links found for {event_title}.")
                continue

            logging.info(f"    Found {len(m3u8_links)} potential links. Validating...")

            for link in m3u8_links:
                if check_stream_status(link):
                    logging.info(f"    [OK] {link}")

                    playlist_lines.append(f'#EXTINF:-1 tvg-logo="{logo}" tvg-id="{tv_id}" group-title="Roxiestreams",Roxiestreams - {event_title}')
                    playlist_lines.append(link)
                    valid_count_for_section += 1

        logging.info(f"  Added {valid_count_for_section} valid streams for {section_title} section.")

    output_filename = "Roxiestreams.m3u"
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(playlist_lines))
        logging.info(f"\n--- SUCCESS ---")
        logging.info(f"Playlist saved as {output_filename}")
        logging.info(f"Total valid streams found: {(len(playlist_lines) - 1) // 2}")
    except IOError as e:
        logging.error(f"Failed to write file {output_filename}: {e}")

if __name__ == "__main__":
    main()