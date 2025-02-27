Run the 'setup_service.bat' to install the 'thetvapp-m3u.exe' as a Windows service.

This script will:	

    Download and unzip firefox for Playwright. (size 238mb's)
    Add the necessary firewall rule to allow traffic on port 4124.
    Install m3u-playlist-proxy.exe as a service using NSSM.
    Configure the service to start automatically on system boot.
    Launch the service in your default browser, using the correct local IP address.

If the script cannot locate the correct local IP address, it will fall back to using localhost. To access the thetvapp-m3u from other devices on the network, the service should be accessed using your local IP address.
Finding your local IP address:

    Open Command Prompt.
    Type ipconfig and press Enter.
    Look for the section corresponding to your network connection (e.g., Wi-Fi or Ethernet).
    Find the IPv4 Address, which will be in the format 192.168.x.x or similar. Use this IP address along with the port 4123 to access the service from other devices.
