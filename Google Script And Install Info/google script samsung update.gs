function doGet(e) {
  const params = e.parameter;
  const region = (params.region || 'us').toLowerCase().trim();
  const service = params.service;
  const sort = params.sort || 'name';
  if (!service) {
    return handleError('Error: No service type provided');
  }
  // Handle Pluto TV service
  if (service.toLowerCase() === 'plutotv') {
    return handlePluto(region, sort);
  }
  // Handle Plex service with updated User-Agent
  if (service.toLowerCase() === 'plex') {
    return handlePlex(region, sort);
  }
  // Handle SamsungTVPlus service
  if (service.toLowerCase() === 'samsungtvplus') {
    return handleSamsungTVPlus(region, sort);
  }
  // Handle Roku service
  if (service.toLowerCase() === 'roku') {
    return handleRoku(sort);
  }
  // Handle Stirr service
  if (service.toLowerCase() === 'stirr') {
    return handleStirr(sort);
  }
  // Handle Tubi service with new URL
  if (service.toLowerCase() === 'tubi') {
    return handleTubi(service);
  }
  // Handle PBSKids service
  if (service.toLowerCase() === 'pbskids') {
    return handlePBSKids(service);
  }
  // Handle PBS service
  if (service.toLowerCase() === 'pbs') {
    return handlePBS();
  }
  // If no matching service was found, return an error
  return handleError('Error: Unsupported service type provided');
}

//------ Service Functions ------//

function handlePluto(region, sort) {
  const PLUTO_URL = 'https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/PlutoTV/.channels.json.gz';
  const STREAM_URL_TEMPLATE = 'https://jmp2.uk/plu-{id}.m3u8';
  sort = sort || 'name';
  let data;
  try {
    Logger.log('Fetching new Pluto data from URL: ' + PLUTO_URL);
    const response = UrlFetchApp.fetch(PLUTO_URL);
    let gzipBlob = response.getBlob();
    gzipBlob = gzipBlob.setContentType('application/x-gzip');
    const extractedBlob = Utilities.ungzip(gzipBlob);
    const extractedData = extractedBlob.getDataAsString();
    data = JSON.parse(extractedData);
    Logger.log('Data successfully extracted and parsed.');
  } catch (error) {
    Logger.log('Error fetching or processing Pluto data: ' + error.stack);
    return handleError('Error fetching Pluto data: ' + error.message);
  }
  let output = `#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/${region}.xml.gz"\n`;
  const regionNameMap = {
    ar: "Argentina", br: "Brazil", ca: "Canada", cl: "Chile", de: "Germany",
    dk: "Denmark", es: "Spain", fr: "France", gb: "United Kingdom", it: "Italy",
    mx: "Mexico", no: "Norway", se: "Sweden", us: "United States"
  };
  let channels = {};
  if (region === 'all') {
    for (const regionKey in data.regions) {
      const regionData = data.regions[regionKey];
      const regionFullName = regionNameMap[regionKey] || regionKey.toUpperCase();
      for (const channelKey in regionData.channels) {
        const channel = { ...regionData.channels[channelKey], region: regionFullName };
        const uniqueChannelId = `${channelKey}-${regionKey}`;
        channels[uniqueChannelId] = channel;
      }
    }
  } else {
    if (!data.regions[region]) {
      return handleError(`Error: Region '${region}' not found in Pluto data.`);
    }
    channels = data.regions[region].channels || {};
  }
  const sortedChannelIds = Object.keys(channels).sort((a, b) => {
    const channelA = channels[a];
    const channelB = channels[b];
    if (sort === 'chno') {
      return channelA.chno - channelB.chno;
    } else {
      return channelA.name.localeCompare(channelB.name);
    }
  });
  sortedChannelIds.forEach(channelId => {
    const channel = channels[channelId];
    const { chno, name, logo, group, region: channelRegion } = channel;
    const groupTitle = region === 'all' ? `${channelRegion}` : group;
    output += `#EXTINF:-1 channel-id="${channelId}" tvg-id="${channelId}" tvg-chno="${chno}" tvg-name="${name}" tvg-logo="${logo}" group-title="${groupTitle}", ${name}\n`;
    output += STREAM_URL_TEMPLATE.replace('{id}', channelId.split('-')[0]) + '\n';
  });
  output = output.replace(/tvg-id="(.*?)-\w{2}"/g, 'tvg-id="$1"');
  return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
}

function handlePlex(region, sort) {
  const PLEX_URL = 'https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/Plex/.channels.json.gz';
  const CHANNELS_JSON_URL = 'https://raw.githubusercontent.com/Mikoshi-nyudo/plex-channels-list/refs/heads/main/plex/channels.json';
  const STREAM_URL_TEMPLATE = 'https://jmp2.uk/plex-{id}.m3u8';
  const USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36';
  sort = sort || 'name';
  let data;
  let plexChannels = [];
  try {
    Logger.log('Fetching new Plex data from URL: ' + PLEX_URL);
    const options = {
      'headers': { 'User-Agent': USER_AGENT }
    };
    const response = UrlFetchApp.fetch(PLEX_URL, options);
    let gzipBlob = response.getBlob();
    gzipBlob = gzipBlob.setContentType('application/x-gzip');
    const extractedBlob = Utilities.ungzip(gzipBlob);
    const extractedData = extractedBlob.getDataAsString();
    data = JSON.parse(extractedData);
    Logger.log('Fetching new channels.json data from URL: ' + CHANNELS_JSON_URL);
    const channelsResponse = UrlFetchApp.fetch(CHANNELS_JSON_URL, options);
    plexChannels = JSON.parse(channelsResponse.getContentText());
  } catch (error) {
    Logger.log('Error fetching Plex or channels data: ' + error.stack);
    return handleError('Error fetching Plex or channels data: ' + error.message);
  }
  let output = `#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/Plex/${region}.xml.gz"\n`;
  const regionNameMap = {
    us: "United States", mx: "Mexico", es: "Spain", ca: "Canada", au: "Australia", nz: "New Zealand"
  };
  let channels = {};
  if (region === 'all') {
    for (const regionKey in data.regions) {
      const regionData = data.regions[regionKey];
      const regionFullName = regionNameMap[regionKey] || regionKey.toUpperCase();
      for (const channelKey in data.channels) {
        const channel = data.channels[channelKey];
        if (channel.regions.includes(regionKey)) {
          const uniqueChannelId = `${channelKey}-${regionKey}`;
          channels[uniqueChannelId] = { ...channel, region: regionFullName, group: regionFullName, originalId: channelKey };
        }
      }
    }
  } else {
    if (!data.regions[region]) {
      return handleError(`Error: Region '${region}' not found in Plex data.`);
    }
    for (const channelKey in data.channels) {
      const channel = data.channels[channelKey];
      if (channel.regions.includes(region)) {
        const matchingChannel = plexChannels.find(ch => ch.Title === channel.name);
        const genre = matchingChannel && matchingChannel.Genre ? matchingChannel.Genre : 'Uncategorized';
        channels[channelKey] = { ...channel, group: genre, originalId: channelKey };
      }
    }
  }
  const sortedChannelIds = Object.keys(channels).sort((a, b) => {
    const channelA = channels[a];
    const channelB = channels[b];
    return sort === 'chno' ? (channelA.chno - channelB.chno) : channelA.name.localeCompare(channelB.name);
  });
  sortedChannelIds.forEach(channelId => {
    const channel = channels[channelId];
    const { chno, name, logo, group, originalId } = channel;
    output += `#EXTINF:-1 channel-id="${channelId}" tvg-id="${channelId}" tvg-chno="${chno || ''}" tvg-name="${name}" tvg-logo="${logo}" group-title="${group}", ${name}\n`;
    output += STREAM_URL_TEMPLATE.replace('{id}', originalId) + '\n';
  });
  output = output.replace(/tvg-id="(.*?)-\w{2}"/g, 'tvg-id="$1"');
  return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
}

function handleSamsungTVPlus(region, sort) {
    const SAMSUNG_URL = 'https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/SamsungTVPlus/.channels.json.gz';
    const STREAM_URL_TEMPLATE = 'https://jmp2.uk/{slug}';
    sort = sort || 'name';
    let data;
    
    try {
      Logger.log('Fetching new SamsungTVPlus data from URL: ' + SAMSUNG_URL);
      const response = UrlFetchApp.fetch(SAMSUNG_URL);
      let gzipBlob = response.getBlob();
      gzipBlob = gzipBlob.setContentType('application/x-gzip');
      const extractedBlob = Utilities.ungzip(gzipBlob);
      const extractedData = extractedBlob.getDataAsString();
      data = JSON.parse(extractedData);
    } catch (error) {
      Logger.log('Error fetching or processing SamsungTVPlus data: ' + error.stack);
      return handleError('Error fetching SamsungTVPlus data: ' + error.message);
    }
    
    let output = `#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/SamsungTVPlus/${region}.xml.gz"\n`;
    let channels = {};
    
    if (region === 'all') {
      for (const regionKey in data.regions) {
        const regionData = data.regions[regionKey];
        const regionFullName = regionData.name || regionKey.toUpperCase();
        for (const channelKey in regionData.channels) {
          const channel = { 
            ...regionData.channels[channelKey], 
            region: regionFullName,
            regionKey: regionKey,
            uniqueId: `${channelKey}-${regionKey}`
          };
          channels[channel.uniqueId] = channel;
        }
      }
    } else {
      if (!data.regions[region]) {
        return handleError(`Error: Region '${region}' not found in SamsungTVPlus data.`);
      }
      for (const channelKey in data.regions[region].channels) {
        const channel = { 
          ...data.regions[region].channels[channelKey],
          uniqueId: channelKey
        };
        channels[channelKey] = channel;
      }
    }
    
    const sortedChannelIds = Object.keys(channels).sort((a, b) => {
      const channelA = channels[a];
      const channelB = channels[b];
      if (sort === 'chno') {
        return channelA.chno - channelB.chno;
      } else {
        return channelA.name.localeCompare(channelB.name);
      }
    });
    
    sortedChannelIds.forEach(channelId => {
      const channel = channels[channelId];
      const { chno, name, logo, group, region: channelRegion, slug } = channel;
      const groupTitle = region === 'all' ? `${channelRegion}` : group;
      
      // Use the channel's slug or fall back to 'stvp-{id}' if not provided
      const channelSlug = slug ? 
        slug.replace('{id}', channel.uniqueId.split('-')[0]) : 
        `stvp-${channel.uniqueId.split('-')[0]}`;
      const streamUrl = STREAM_URL_TEMPLATE.replace('{slug}', channelSlug);
      
      output += `#EXTINF:-1 channel-id="${channelId}" tvg-id="${channelId}" tvg-chno="${chno}" tvg-name="${name}" tvg-logo="${logo}" group-title="${groupTitle}", ${name}\n`;
      output += streamUrl + '\n';
    });
    
    return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
  }

function handleRoku(sort) {
  const ROKU_URL = 'https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/Roku/.channels.json.gz';
  const STREAM_URL_TEMPLATE = 'https://jmp2.uk/rok-{id}.m3u8';
  sort = sort || 'name';
  let data;
  try {
    Logger.log('Fetching new Roku data from URL: ' + ROKU_URL);
    const response = UrlFetchApp.fetch(ROKU_URL);
    let gzipBlob = response.getBlob();
    gzipBlob = gzipBlob.setContentType('application/x-gzip');
    const extractedBlob = Utilities.ungzip(gzipBlob);
    const extractedData = extractedBlob.getDataAsString();
    data = JSON.parse(extractedData);
  } catch (error) {
    Logger.log('Error fetching or processing Roku data: ' + error.stack);
    return handleError('Error fetching Roku data: ' + error.message);
  }
  let output = `#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/Roku/all.xml.gz"\n`;
  let channels = data.channels || {};
  const sortedChannelIds = Object.keys(channels).sort((a, b) => {
    const channelA = channels[a];
    const channelB = channels[b];
    if (sort === 'chno') {
      return channelA.chno - channelB.chno;
    } else {
      return channelA.name.localeCompare(channelB.name);
    }
  });
  sortedChannelIds.forEach(channelId => {
    const channel = channels[channelId];
    const { chno, name, logo, groups } = channel;
    const groupTitle = groups && groups.length > 0 ? groups[0] : 'Uncategorized';
    output += `#EXTINF:-1 channel-id="${channelId}" tvg-id="${channelId}" tvg-chno="${chno}" tvg-name="${name}" tvg-logo="${logo}" group-title="${groupTitle}", ${name}\n`;
    output += STREAM_URL_TEMPLATE.replace('{id}', channelId) + '\n';
  });
  return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
}

function handleStirr(sort) {
  const STIRR_URL = 'https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/Stirr/.channels.json.gz';
  sort = sort || 'name';
  let data;
  try {
    Logger.log('Fetching new Stirr data from URL: ' + STIRR_URL);
    const response = UrlFetchApp.fetch(STIRR_URL);
    let gzipBlob = response.getBlob();
    gzipBlob = gzipBlob.setContentType('application/x-gzip');
    const extractedBlob = Utilities.ungzip(gzipBlob);
    const extractedData = extractedBlob.getDataAsString();
    data = JSON.parse(extractedData);
  } catch (error) {
    Logger.log('Error fetching or processing Stirr data: ' + error.stack);
    return handleError('Error fetching Stirr data: ' + error.message);
  }
  let output = `#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/Stirr/all.xml.gz"\n`;
  let channels = data.channels || {};
  const sortedChannelIds = Object.keys(channels).sort((a, b) => {
    const channelA = channels[a];
    const channelB = channels[b];
    if (sort === 'chno') {
      return channelA.chno - channelB.chno;
    } else {
      return channelA.name.localeCompare(channelB.name);
    }
  });
  sortedChannelIds.forEach(channelId => {
    const channel = channels[channelId];
    const { chno, name, logo, groups } = channel;
    const groupTitle = groups && groups.length > 0 ? groups.join(', ') : 'Uncategorized';
    const streamUrl = `https://jmp2.uk/str-${channelId}.m3u8`;
    output += `#EXTINF:-1 channel-id="${channelId}" tvg-id="${channelId}" tvg-chno="${chno}" tvg-name="${name}" tvg-logo="${logo}" group-title="${groupTitle}", ${name}\n`;
    output += `${streamUrl}\n`;
  });
  return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
}

function handleTubi(service) {
  let data;
  try {
    Logger.log('Fetching new Tubi data');
    const playlistUrl = 'https://raw.githubusercontent.com/BuddyChewChew/tubi-scraper/refs/heads/main/tubi_playlist.m3u';
    const options = {
      'headers': {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
      }
    };
    const response = UrlFetchApp.fetch(playlistUrl, options);
    data = response.getContentText();
    let epgUrl = 'https://raw.githubusercontent.com/BuddyChewChew/tubi-scraper/refs/heads/main/tubi_epg.xml';
    let output = `#EXTM3U url-tvg="${epgUrl}"\n`;
    output += data;
    return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
  } catch (error) {
    Logger.log('Error fetching Tubi data: ' + error.stack);
    return handleError('Error fetching Tubi data: ' + error.message);
  }
}

function handlePBSKids(service) {
  if (service.toLowerCase() !== 'pbskids') return;
  let data;
  try {
    Logger.log('Fetching new PBS Kids data');
    const APP_URL = 'https://i.mjh.nz/PBS/.kids_app.json.gz';
    const response = UrlFetchApp.fetch(APP_URL);
    let gzipBlob = response.getBlob();
    gzipBlob = gzipBlob.setContentType('application/x-gzip');
    const extractedBlob = Utilities.ungzip(gzipBlob);
    const extractedData = extractedBlob.getDataAsString();
    data = JSON.parse(extractedData);
    let output = `#EXTM3U url-tvg="https://github.com/matthuisman/i.mjh.nz/raw/master/PBS/kids_all.xml.gz"\n`;
    const sortedKeys = Object.keys(data.channels).sort((a, b) => {
      const channelA = data.channels[a].name.toLowerCase();
      const channelB = data.channels[b].name.toLowerCase();
      return channelA.localeCompare(channelB);
    });
    sortedKeys.forEach(key => {
      const channel = data.channels[key];
      const { logo, name, url } = channel;
      output += `#EXTINF:-1 channel-id="pbskids-${key}" tvg-id="${key}" tvg-name="${name}" tvg-logo="${logo}", ${name}\n${url}\n`;
    });
    return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
  } catch (error) {
    Logger.log('Error fetching PBS Kids data: ' + error.stack);
    return handleError('Error fetching PBS Kids data: ' + error.message);
  }
}

function handlePBS() {
  const DATA_URL = 'https://i.mjh.nz/PBS/.app.json.gz';
  const EPG_URL = 'https://i.mjh.nz/PBS/all.xml.gz';
  let data;
  try {
    Logger.log('Fetching new PBS data from URL: ' + DATA_URL);
    const response = UrlFetchApp.fetch(DATA_URL);
    let gzipBlob = response.getBlob();
    gzipBlob = gzipBlob.setContentType('application/x-gzip');
    const extractedBlob = Utilities.ungzip(gzipBlob);
    const extractedData = extractedBlob.getDataAsString();
    data = JSON.parse(extractedData);
  } catch (error) {
    Logger.log('Error fetching or processing PBS data: ' + error.stack);
    return handleError('Error fetching PBS data: ' + error.message);
  }
  let output = `#EXTM3U x-tvg-url="${EPG_URL}"\n`;
  Object.keys(data.channels).forEach(key => {
    const channel = data.channels[key];
    output += `#EXTINF:-1 channel-id="pbs-${key}" tvg-id="${key}" tvg-name="${channel.name}" tvg-logo="${channel.logo}", ${channel.name}\n`;
    output += `#KODIPROP:inputstream.adaptive.manifest_type=mpd\n`;
    output += `#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha\n`;
    output += `#KODIPROP:inputstream.adaptive.license_key=${channel.license}|Content-Type=application%2Foctet-stream&user-agent=okhttp%2F4.9.0|R{SSM}|\n`;
    output += `${channel.url}|user-agent=okhttp%2F4.9.0\n`;
  });
  return ContentService.createTextOutput(output).setMimeType(ContentService.MimeType.TEXT);
}

//------ Other Functions ------//

function handleError(errorMessage) {
  return ContentService.createTextOutput(errorMessage)
    .setMimeType(ContentService.MimeType.TEXT);
}
