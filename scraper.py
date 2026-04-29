import requests
from bs4 import BeautifulSoup
import os
import re
from urllib.parse import urljoin, unquote

# --- CONFIGURATION ---
# This pulls the key from the GitHub Secret environment variable
OMDB_API_KEY = os.environ.get("OMDB_API_KEY")
BASE_URL = "http://23.147.64.113/movies/Other/"
OUTPUT_DIR = "vod"
# ---------------------

def get_movie_poster(title):
    """Fetches the poster URL from OMDb."""
    if not OMDB_API_KEY:
        print("Error: No OMDB_API_KEY found in environment variables.")
        return ""
    
    # Try to extract year if it's in the filename (e.g. "Movie Name (2023)")
    year_match = re.search(r'\((\d{4})\)', title)
    year = year_match.group(1) if year_match else ""
    clean_title = re.sub(r'\(.*?\)', '', title).strip()

    params = {
        "apikey": OMDB_API_KEY,
        "t": clean_title,
        "y": year if year else None
    }

    try:
        response = requests.get("http://www.omdbapi.com/", params=params, timeout=5)
        data = response.json()
        
        if data.get("Response") == "True":
            poster_url = data.get("Poster")
            if poster_url and poster_url.startswith("http"):
                return poster_url
    except Exception as e:
        print(f"Error fetching poster for {clean_title}: {e}")
    
    return ""

def generate_vod_m3u():
    output_file = os.path.join(OUTPUT_DIR, "movies.m3u")
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    try:
        response = requests.get(BASE_URL, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error accessing source: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.m4v')
    m3u_content = ["#EXTM3U"]
    
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and href.lower().endswith(video_extensions):
            file_name = unquote(href).strip('/')
            display_name = os.path.splitext(file_name)[0]
            
            print(f"Searching OMDb for: {display_name}...")
            poster_url = get_movie_poster(display_name)
            full_url = urljoin(BASE_URL, href)
            
            logo_attr = f' tvg-logo="{poster_url}"' if poster_url else ""
            m3u_content.append(f'#EXTINF:-1 tvg-name="{display_name}"{logo_attr} group-title="Other Movies",{display_name}')
            m3u_content.append(full_url)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    
    print(f"\nSuccess! Generated {output_file}.")

if __name__ == "__main__":
    generate_vod_m3u()
