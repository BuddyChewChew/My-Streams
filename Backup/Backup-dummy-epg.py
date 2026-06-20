import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom

def generate_multi_channel_epg():
    # 1. Configuration: Add your default logo URL here
    DEFAULT_LOGO = "https://github.com/BuddyChewChew/My-Streams/blob/main/Backup/dummy-logos/default.png?raw=true"
    INFO_LOGO = "https://github.com/BuddyChewChew/My-Streams/blob/main/Backup/dummy-logos/info.png?raw=true"
    
    channels = [
        {"id": "INFO.bud", "name": "INFO CHANNEL", "logo": INFO_LOGO},
        {"id": "Fishing.bud", "name": "Fishing", "logo": DEFAULT_LOGO},
        {"id": "Movie.bud", "name": "Movie", "logo": DEFAULT_LOGO},
        {"id": "News.24.7.bud", "name": "News 24/7", "logo": DEFAULT_LOGO},
        {"id": "Outdoors.bud", "name": "Outdoors", "logo": DEFAULT_LOGO},
        {"id": "Channel5.bud", "name": "Channel Name 5", "logo": DEFAULT_LOGO},
        {"id": "Channel6.bud", "name": "Channel Name 6", "logo": DEFAULT_LOGO},
        {"id": "Channel7.bud", "name": "Channel Name 7", "logo": DEFAULT_LOGO},
        {"id": "Channel8.bud", "name": "Channel Name 8", "logo": DEFAULT_LOGO},
        {"id": "Channel9.bud", "name": "Channel Name 9", "logo": DEFAULT_LOGO},
        {"id": "Channel10.bud", "name": "Channel Name 10", "logo": DEFAULT_LOGO},
        {"id": "Channel11.bud", "name": "Channel Name 11", "logo": DEFAULT_LOGO}
    ]
    
    CUSTOM_MESSAGES = [
        "(CC)=CORDCUTTER ● (KSTV)=KSTV ● (PTV)=PEAKYTV",
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
        if ch["id"] == "INFO.bud":
            prog_start = base_start
            prog_stop = base_start + datetime.timedelta(hours=24)
            start_str = prog_start.strftime('%Y%m%d%H%M%S +0000')
            stop_str = prog_stop.strftime('%Y%m%d%H%M%S +0000')
            
            prog = ET.SubElement(tv, 'programme', start=start_str, stop=stop_str, channel=ch["id"])
            ET.SubElement(prog, 'title', lang="en").text = "Added WhiplashTV Adult Channels and testing a new source for LIVE TV." 
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

if __name__ == "__main__":
    generate_multi_channel_epg()
