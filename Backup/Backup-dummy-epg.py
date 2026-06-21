import datetime
import gzip
import urllib.request
import xml.etree.ElementTree as ET
from xml.dom import minidom

def generate_multi_channel_epg():
    # 1. Configuration: Add your default logo URL here
    DEFAULT_LOGO = "https://github.com/BuddyChewChew/My-Streams/blob/main/Backup/dummy-logos/default.png?raw=true"
    BUD_LOGO = "https://github.com/BuddyChewChew/My-Streams/blob/main/Backup/dummy-logos/info.png?raw=true"
    IHEART_LOGO = "https://github.com/BuddyChewChew/My-Streams/blob/main/Backup/dummy-logos/iheart.png?raw=true"
    
    channels = [
        {"id": "bud.bud", "name": "6-20-26 Update", "logo": BUD_LOGO},
        {"id": "Fishing.bud", "name": "Fishing", "logo": DEFAULT_LOGO},
        {"id": "Movie.bud", "name": "Movie", "logo": DEFAULT_LOGO},
        {"id": "News.24.7.bud", "name": "News 24/7", "logo": DEFAULT_LOGO},
        {"id": "Outdoors.bud", "name": "Outdoors", "logo": DEFAULT_LOGO},
        {"id": "iheart.bud", "name": "iHeart Radio", "logo": IHEART_LOGO},
        {"id": "Channel6.bud", "name": "Channel Name 6", "logo": DEFAULT_LOGO},
        {"id": "Channel7.bud", "name": "Channel Name 7", "logo": DEFAULT_LOGO},
        {"id": "Channel8.bud", "name": "Channel Name 8", "logo": DEFAULT_LOGO},
        {"id": "Channel9.bud", "name": "Channel Name 9", "logo": DEFAULT_LOGO},
        {"id": "Channel10.bud", "name": "Channel Name 10", "logo": DEFAULT_LOGO},
        {"id": "Channel11.bud", "name": "Channel Name 11", "logo": DEFAULT_LOGO}
    ]
    
    CUSTOM_MESSAGES = [
        "ENJOY SOME FREE TV 😜",
        "Discord: https://discord.gg/fnsWGDy2mm",
        ""
    ]
    
    filename = "epg.xml"
    
    # 2. Generate the Clean ID List (epg_ids.txt)
    with open("epg_ids.txt", "w", encoding="utf-8") as f:
        for ch in channels:
            f.write(f"{ch['id']}\n")
    
    # 3. Create XML Root
    tv = ET.Element('tv')
    
    # 4. Add Channel Definitions with Logos
    for ch in channels:
        chan_elem = ET.SubElement(tv, 'channel', id=ch["id"])
        ET.SubElement(chan_elem, 'display-name').text = ch["name"]
        ET.SubElement(chan_elem, 'icon', src=ch["logo"])
    
    # 5. Generate Programming
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    base_start = now_utc.replace(minute=0, second=0, microsecond=0)
    
    for ch in channels:
        if ch["id"] == "bud.bud":
            prog_start = base_start
            prog_stop = base_start + datetime.timedelta(hours=24)
            start_str = prog_start.strftime('%Y%m%d%H%M%S +0000')
            stop_str = prog_stop.strftime('%Y%m%d%H%M%S +0000')
            
            prog = ET.SubElement(tv, 'programme', start=start_str, stop=stop_str, channel=ch["id"])
            ET.SubElement(prog, 'title', lang="en").text = "Added WhiplashTV. More channels to come." 
            # Description now only contains the custom messages
            full_description = "\n".join(CUSTOM_MESSAGES)
            ET.SubElement(prog, 'desc', lang="en").text = full_description
            
        else:
            # Generates 24 blocks of 1 hour each using the channel name
            for i in range(24):
                prog_start = base_start + datetime.timedelta(hours=i)
                prog_stop = prog_start + datetime.timedelta(hours=1)
                start_str = prog_start.strftime('%Y%m%d%H%M%S +0000')
                stop_str = prog_stop.strftime('%Y%m%d%H%M%S +0000')
                
                prog = ET.SubElement(tv, 'programme', start=start_str, stop=stop_str, channel=ch["id"])
                ET.SubElement(prog, 'title', lang="en").text = ch['name']
                ET.SubElement(prog, 'desc', lang="en").text = ch['name']

    # 6. Format and Save XML
    xml_string = ET.tostring(tv, encoding='utf-8')
    pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
        
    print(f"Successfully generated {filename} with clean 1-hour labels.")


def merge_epgs():
    """
    Fetches the multi-epg-light gzip EPG, merges it with the local
    dummy epg.xml (channels + programmes from both), and writes the
    combined result to merged-epg.xml. epg.xml itself is left untouched.
    """
    LIGHT_EPG_URL = "https://github.com/BuddyChewChew/multi-epg-light/raw/refs/heads/main/epgs/light-epg.xml.gz"
    LOCAL_EPG_FILE = "epg.xml"
    OUTPUT_FILE = "merged-epg.xml.gz"

    # 1. Download the remote gzip EPG
    print(f"Downloading {LIGHT_EPG_URL} ...")
    req = urllib.request.Request(LIGHT_EPG_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        compressed_data = response.read()

    # 2. Decompress and parse it
    xml_bytes = gzip.decompress(compressed_data)
    light_root = ET.fromstring(xml_bytes)

    # 3. Parse the local dummy epg.xml
    dummy_tree = ET.parse(LOCAL_EPG_FILE)
    dummy_root = dummy_tree.getroot()

    # 4. Build merged root, dummy channels/programmes first, then light-epg's
    merged_root = ET.Element('tv', {'generator-info-name': 'BuddyChewChew-Merged-EPG'})

    for tag in ('channel', 'programme'):
        for elem in dummy_root.findall(tag):
            merged_root.append(elem)
        for elem in light_root.findall(tag):
            merged_root.append(elem)

    # 5. Write merged-epg.xml.gz (gzip-compressed to keep the repo lightweight)
    ET.indent(ET.ElementTree(merged_root), space="  ")
    xml_bytes_out = ET.tostring(merged_root, encoding="utf-8", xml_declaration=True)
    with gzip.open(OUTPUT_FILE, "wb") as f:
        f.write(xml_bytes_out)

    dummy_channel_count = len(dummy_root.findall('channel'))
    light_channel_count = len(light_root.findall('channel'))
    print(f"Successfully generated {OUTPUT_FILE} "
          f"({dummy_channel_count} dummy channels + {light_channel_count} light-epg channels).")

if __name__ == "__main__":
    generate_multi_channel_epg()
    merge_epgs()
