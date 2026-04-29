import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin

def generate_vod_m3u():
    base_url = "http://23.147.64.113/movies/Other/"
    output_dir = "vod"
    output_file = os.path.join(output_dir, "movies.m3u")
    
    # Ensure the vod directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Supported video extensions
    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.m4v')
    
    m3u_content = ["#EXTM3U"]
    
    # Find all links in the directory listing
    for link in soup.find_all('a'):
        href = link.get('href')
        
        # Filter for video files and skip parent directories/relative paths
        if href and href.lower().endswith(video_extensions):
            file_name = requests.utils.unquote(href).strip('/')
            # Clean up the name for the display title (remove extension)
            display_name = os.path.splitext(file_name)[0].replace('%20', ' ')
            
            full_url = urljoin(base_url, href)
            
            # TiviMate VOD formatting
            m3u_content.append(f'#EXTINF:-1 tvg-name="{display_name}" group-title="Other Movies",{display_name}')
            m3u_content.append(full_url)

    # Save the file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    
    print(f"Successfully generated {output_file} with {len(m3u_content)//2} movies.")

if __name__ == "__main__":
    generate_vod_m3u()
