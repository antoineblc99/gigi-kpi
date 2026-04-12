// ============================================================
// GIGI KPI — Apps Script de collecte automatique
// Tourne tous les jours a 21h30 via trigger Google
// ============================================================

// ---- CONFIG ----
const SHEET_ID = '1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo';

// Meta Ads
const META_ACCESS_TOKEN = PropertiesService.getScriptProperties().getProperty('META_ACCESS_TOKEN');
const META_AD_ACCOUNT_ID = PropertiesService.getScriptProperties().getProperty('META_AD_ACCOUNT_ID');
const CAMPAIGN_VSL_ID = '120243478827620073';
const CAMPAIGN_FOLLOW_ID = '120241957177570073';
const ADSET_IDS = {
  vsl_broad: '120243478853250073',
  vsl_retargeting: '120243478850530073',
  follow_broad: '120241964220250073',
  follow_lookalike: '120241957177550073'
};

// GHL
const GHL_API_KEY_CELL = 'GHL_Config!B2'; // Lue depuis le sheet
const GHL_LOCATION_ID = 'TTzAZhJJwPHQobNiXjWJ';
const CALENDAR_VSL_ID = '8ECqPVcPGz81JGlzCmoG';
const CALENDAR_FOLLOW_ID = 'AQ8RmdYw7iyru79Axymf';

// ---- UTILS ----

function getSpreadsheet() {
  return SpreadsheetApp.openById(SHEET_ID);
}

function todayStr() {
  const d = new Date();
  return Utilities.formatDate(d, 'Europe/Paris', 'dd/MM');
}

function todayISO() {
  const d = new Date();
  return Utilities.formatDate(d, 'Europe/Paris', 'yyyy-MM-dd');
}

function yesterdayISO() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return Utilities.formatDate(d, 'Europe/Paris', 'yyyy-MM-dd');
}

function getGhlApiKey() {
  const ss = getSpreadsheet();
  return ss.getRange(GHL_API_KEY_CELL).getValue();
}

function usdToEur(usd) {
  // Approximation — a ajuster si besoin
  return Math.round(usd * 0.92 * 100) / 100;
}

// ---- META ADS API ----

function metaApiCall(endpoint, params) {
  const baseUrl = 'https://graph.facebook.com/v21.0';
  params.access_token = META_ACCESS_TOKEN;

  const queryString = Object.entries(params)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&');

  const url = `${baseUrl}/${endpoint}?${queryString}`;

  try {
    const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    const json = JSON.parse(response.getContentText());
    if (json.error) {
      Logger.log(`Meta API error: ${JSON.stringify(json.error)}`);
      return null;
    }
    return json;
  } catch (e) {
    Logger.log(`Meta API exception: ${e.message}`);
    return null;
  }
}

function getCampaignInsights(campaignId, dateStr) {
  const result = metaApiCall(`${campaignId}/insights`, {
    time_range: JSON.stringify({ since: dateStr, until: dateStr }),
    fields: 'spend,impressions,clicks,cpc,cpm,ctr,reach,actions,cost_per_action_type',
    level: 'campaign'
  });

  if (!result || !result.data || result.data.length === 0) return null;
  return result.data[0];
}

function getAdsetInsights(adsetId, dateStr) {
  const result = metaApiCall(`${adsetId}/insights`, {
    time_range: JSON.stringify({ since: dateStr, until: dateStr }),
    fields: 'spend,impressions,clicks,cpc,cpm,ctr,reach,actions,cost_per_action_type,adset_name,adset_id',
    level: 'adset'
  });

  if (!result || !result.data || result.data.length === 0) return null;
  return result.data[0];
}

function getAdInsights(campaignId, dateStr) {
  const result = metaApiCall(`${campaignId}/insights`, {
    time_range: JSON.stringify({ since: dateStr, until: dateStr }),
    fields: 'spend,impressions,clicks,cpc,cpm,ctr,reach,actions,cost_per_action_type,ad_name,ad_id,adset_name',
    level: 'ad',
    limit: '100'
  });

  if (!result || !result.data) return [];
  return result.data;
}

function extractAction(data, actionType) {
  if (!data || !data.actions) return 0;
  const action = data.actions.find(a => a.action_type === actionType);
  return action ? parseInt(action.value) : 0;
}

function extractCostPerAction(data, actionType) {
  if (!data || !data.cost_per_action_type) return 0;
  const action = data.cost_per_action_type.find(a => a.action_type === actionType);
  return action ? parseFloat(action.value) : 0;
}

// ---- GHL API ----

function ghlApiCall(endpoint, params) {
  const apiKey = getGhlApiKey();
  const baseUrl = 'https://services.leadconnectorhq.com';

  const queryString = params
    ? '?' + Object.entries(params).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&')
    : '';

  const url = `${baseUrl}${endpoint}${queryString}`;

  try {
    const response = UrlFetchApp.fetch(url, {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Version': '2021-07-28',
        'Content-Type': 'application/json'
      },
      muteHttpExceptions: true
    });
    return JSON.parse(response.getContentText());
  } catch (e) {
    Logger.log(`GHL API exception: ${e.message}`);
    return null;
  }
}

function getCalendarEvents(calendarId, startDate, endDate) {
  const startTime = new Date(startDate + 'T00:00:00+02:00').getTime();
  const endTime = new Date(endDate + 'T23:59:59+02:00').getTime();

  const result = ghlApiCall('/calendars/events', {
    locationId: GHL_LOCATION_ID,
    calendarId: calendarId,
    startTime: startTime.toString(),
    endTime: endTime.toString()
  });

  if (!result || !result.events) return [];
  return result.events;
}

function countEventsByStatus(events) {
  const counts = { total: 0, confirmed: 0, cancelled: 0, showed: 0, noshow: 0 };
  events.forEach(e => {
    counts.total++;
    if (e.appointmentStatus === 'confirmed') counts.confirmed++;
    if (e.appointmentStatus === 'cancelled') counts.cancelled++;
    if (e.appointmentStatus === 'showed') counts.showed++;
    if (e.appointmentStatus === 'no_show') counts.noshow++;
  });
  return counts;
}

// ---- WRITE TO SHEETS ----

function appendRow(sheetName, values) {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    Logger.log(`Sheet not found: ${sheetName}`);
    return;
  }
  sheet.appendRow(values);
}

function findOrCreateTodayRow(sheetName, dateStr) {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) return null;

  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (data[i][0] === dateStr) {
      return i + 1; // row number (1-indexed)
    }
  }
  return null; // not found, will append
}

// ---- MAIN FUNCTIONS ----

/**
 * Fonction principale — appeler chaque jour
 */
function dailySync() {
  const date = todayISO();
  const dateDisplay = todayStr();

  Logger.log(`=== Daily Sync: ${date} ===`);

  // 1. Meta Ads
  syncMetaAds(date, dateDisplay);

  // 2. GHL Calendar Events
  syncGhlCalendar(date, dateDisplay);

  // 3. Update Data_Funnel_VSL
  updateDataFunnelVSL(date, dateDisplay);

  // 4. Update Data_Funnel_Follow
  updateDataFunnelFollow(date, dateDisplay);

  // 5. Update sync timestamp
  const ss = getSpreadsheet();
  ss.getSheetByName('GHL_Config').getRange('B4').setValue(new Date());

  Logger.log('=== Sync complete ===');
}

function syncMetaAds(date, dateDisplay) {
  Logger.log('Syncing Meta Ads...');

  // Campaign level — VSL
  const vslData = getCampaignInsights(CAMPAIGN_VSL_ID, date);
  if (vslData) {
    const spend = parseFloat(vslData.spend || 0);
    const impressions = parseInt(vslData.impressions || 0);
    const clicks = parseInt(vslData.clicks || 0);
    const ctr = parseFloat(vslData.ctr || 0);
    const cpc = parseFloat(vslData.cpc || 0);
    const cpm = parseFloat(vslData.cpm || 0);
    const reach = parseInt(vslData.reach || 0);
    const linkClicks = extractAction(vslData, 'link_click');
    const lpv = extractAction(vslData, 'landing_page_view');
    const leads = extractAction(vslData, 'offsite_complete_registration_add_meta_leads');

    // DashBoard_Funnel VSL (format existant)
    const existingRow = findOrCreateTodayRow('DashBoard_Funnel VSL', dateDisplay);
    const ss = getSpreadsheet();
    const dashSheet = ss.getSheetByName('DashBoard_Funnel VSL');
    const rowData = [dateDisplay, spend, impressions, linkClicks, ctr, cpc, lpv, leads, leads > 0 ? spend / leads : ''];

    if (existingRow) {
      dashSheet.getRange(existingRow, 1, 1, rowData.length).setValues([rowData]);
    } else {
      dashSheet.appendRow(rowData);
    }
  }

  // Campaign level — Follow
  const followData = getCampaignInsights(CAMPAIGN_FOLLOW_ID, date);
  if (followData) {
    const spend = parseFloat(followData.spend || 0);
    const impressions = parseInt(followData.impressions || 0);
    const clicks = parseInt(followData.clicks || 0);
    const profileVisits = extractAction(followData, 'link_click');

    // Meta_Ads_Raw
    appendRow('Meta_Ads_Raw', [
      date, spend, impressions, clicks,
      parseFloat(followData.cpm || 0),
      parseFloat(followData.cpc || 0),
      parseFloat(followData.ctr || 0),
      parseInt(followData.reach || 0),
      '', // followers (not available from API directly)
      profileVisits,
      '', '', '', // results, cost/result, cost/follower
      new Date(),
      '' // IG total followers
    ]);
  }

  // AdSet level — all
  Object.entries(ADSET_IDS).forEach(([name, adsetId]) => {
    const data = getAdsetInsights(adsetId, date);
    if (data && parseFloat(data.spend || 0) > 0) {
      appendRow('AdSet_Raw', [
        date,
        data.adset_name || name,
        adsetId,
        parseFloat(data.spend || 0),
        parseInt(data.impressions || 0),
        parseInt(data.clicks || 0),
        parseFloat(data.cpm || 0),
        parseFloat(data.cpc || 0),
        parseFloat(data.ctr || 0),
        parseInt(data.reach || 0),
        extractAction(data, 'link_click'),
        extractCostPerAction(data, 'link_click'),
        '', '', '', '', // video views, engagements, saves, likes (need separate query)
        new Date()
      ]);
    }
  });

  // Ad/Creative level — both campaigns
  [CAMPAIGN_VSL_ID, CAMPAIGN_FOLLOW_ID].forEach(campaignId => {
    const ads = getAdInsights(campaignId, date);
    ads.forEach(ad => {
      if (parseFloat(ad.spend || 0) > 0) {
        appendRow('Creative_Raw', [
          date,
          ad.ad_name || '',
          ad.ad_id || '',
          ad.adset_name || '',
          parseFloat(ad.spend || 0),
          parseInt(ad.impressions || 0),
          parseInt(ad.clicks || 0),
          parseFloat(ad.cpm || 0),
          parseFloat(ad.cpc || 0),
          parseFloat(ad.ctr || 0),
          parseInt(ad.reach || 0),
          extractAction(ad, 'link_click'),
          extractCostPerAction(ad, 'link_click'),
          '', '', '', '', // video views, engagements, saves, likes
          new Date()
        ]);
      }
    });
  });

  Logger.log('Meta Ads sync done.');
}

function syncGhlCalendar(date, dateDisplay) {
  Logger.log('Syncing GHL Calendar...');

  // VSL Calendar
  const vslEvents = getCalendarEvents(CALENDAR_VSL_ID, date, date);
  vslEvents.forEach(event => {
    if (!event.deleted) {
      appendRow('GHL_Calls_Raw', [
        dateDisplay,
        'VSL',
        event.title || '',
        '', // email (not in event data)
        event.appointmentStatus || '',
        event.assignedUserId || '',
        event.createdBy ? event.createdBy.source : '',
        event.dateAdded || ''
      ]);
    }
  });

  // Follow/Standard Calendar
  const followEvents = getCalendarEvents(CALENDAR_FOLLOW_ID, date, date);
  followEvents.forEach(event => {
    if (!event.deleted) {
      appendRow('GHL_Calls_Raw', [
        dateDisplay,
        'Follow',
        event.title || '',
        '',
        event.appointmentStatus || '',
        event.assignedUserId || '',
        event.createdBy ? event.createdBy.source : '',
        event.dateAdded || ''
      ]);
    }
  });

  Logger.log(`GHL Calendar sync done. VSL: ${vslEvents.length}, Follow: ${followEvents.length}`);
}

function updateDataFunnelVSL(date, dateDisplay) {
  Logger.log('Updating Data_Funnel_VSL...');

  const vslData = getCampaignInsights(CAMPAIGN_VSL_ID, date);
  if (!vslData) return;

  const spend = parseFloat(vslData.spend || 0);
  const impressions = parseInt(vslData.impressions || 0);
  const linkClicks = extractAction(vslData, 'link_click');
  const ctr = parseFloat(vslData.ctr || 0);
  const cpc = parseFloat(vslData.cpc || 0);
  const lpv = extractAction(vslData, 'landing_page_view');
  const optins = extractAction(vslData, 'offsite_complete_registration_add_meta_leads');

  // GHL calls for VSL today
  const vslEvents = getCalendarEvents(CALENDAR_VSL_ID, date, date);
  const vslCounts = countEventsByStatus(vslEvents.filter(e => !e.deleted));

  const tauxOptin = lpv > 0 ? (optins / lpv * 100).toFixed(1) + '%' : '0%';
  const coutOptin = optins > 0 ? (spend / optins).toFixed(2) : '-';
  const coutCall = vslCounts.confirmed > 0 ? (spend / vslCounts.confirmed).toFixed(2) : '-';

  const row = [
    dateDisplay,          // Date
    spend,                // Ad Spend
    impressions,          // Impressions
    linkClicks,           // Link Clicks
    ctr,                  // CTR
    cpc,                  // CPC
    lpv,                  // LPV
    optins,               // Opt-ins
    tauxOptin,            // Taux Opt-in
    '',                   // Surveys (manual or separate sync)
    '',                   // Taux Survey
    '',                   // Qualifies
    '',                   // Taux Qualif
    vslCounts.total,      // Calls Bookes
    '',                   // Taux Booking
    vslCounts.showed,     // Calls Recus
    '',                   // Taux Show
    0,                    // Ventes (from closer EOD)
    '',                   // Taux Closing
    0,                    // Cash Contracte
    0,                    // Cash Collecte
    coutOptin,            // Cout/Opt-in
    coutCall,             // Cout/Call
    '-',                  // Cout/Vente
    0                     // ROAS
  ];

  const existingRow = findOrCreateTodayRow('Data_Funnel_VSL', dateDisplay);
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName('Data_Funnel_VSL');

  if (existingRow) {
    sheet.getRange(existingRow, 1, 1, row.length).setValues([row]);
  } else {
    sheet.appendRow(row);
  }

  Logger.log('Data_Funnel_VSL updated.');
}

function updateDataFunnelFollow(date, dateDisplay) {
  Logger.log('Updating Data_Funnel_Follow...');

  const followData = getCampaignInsights(CAMPAIGN_FOLLOW_ID, date);
  if (!followData) return;

  const spend = parseFloat(followData.spend || 0);
  const impressions = parseInt(followData.impressions || 0);
  const clicks = parseInt(followData.clicks || 0);
  const ctr = parseFloat(followData.ctr || 0);
  const cpc = parseFloat(followData.cpc || 0);
  const reach = parseInt(followData.reach || 0);
  const profileVisits = extractAction(followData, 'link_click');
  const coutPV = profileVisits > 0 ? (spend / profileVisits).toFixed(3) : '-';

  // GHL calls for Follow today
  const followEvents = getCalendarEvents(CALENDAR_FOLLOW_ID, date, date);
  const followCounts = countEventsByStatus(followEvents.filter(e => !e.deleted));
  const coutCall = followCounts.confirmed > 0 ? (spend / followCounts.confirmed).toFixed(2) : '-';

  const row = [
    dateDisplay,            // Date
    spend,                  // Ad Spend
    impressions,            // Impressions
    clicks,                 // Clicks
    ctr,                    // CTR
    cpc,                    // CPC
    reach,                  // Reach
    profileVisits,          // Profile Visits
    coutPV,                 // Cout/PV
    '',                     // New Followers (manual or IG API)
    '',                     // Cout/Follower
    '',                     // DMs envoyes (from setter)
    '',                     // Liens envoyes (from setter)
    '',                     // Taux Lien
    followCounts.total,     // Calls Bookes
    '',                     // Taux Booking
    followCounts.showed,    // Calls Recus
    '',                     // Taux Show
    0,                      // Ventes
    '',                     // Taux Closing
    0,                      // Cash Contracte
    0,                      // Cash Collecte
    coutCall,               // Cout/Call
    '-',                    // Cout/Vente
    0                       // ROAS
  ];

  const existingRow = findOrCreateTodayRow('Data_Funnel_Follow', dateDisplay);
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName('Data_Funnel_Follow');

  if (existingRow) {
    sheet.getRange(existingRow, 1, 1, row.length).setValues([row]);
  } else {
    sheet.appendRow(row);
  }

  Logger.log('Data_Funnel_Follow updated.');
}

// ---- SETUP ----

/**
 * Lancer une fois pour configurer le trigger quotidien
 */
function setupDailyTrigger() {
  // Supprimer les anciens triggers
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === 'dailySync') {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  // Creer le trigger quotidien a 21h30 Europe/Paris
  ScriptApp.newTrigger('dailySync')
    .timeBased()
    .atHour(21)
    .nearMinute(30)
    .everyDays(1)
    .inTimezone('Europe/Paris')
    .create();

  Logger.log('Daily trigger set for 21:30 Europe/Paris');
}

/**
 * Lancer une fois pour sauvegarder les tokens dans les proprietes du script
 * Modifier les valeurs ci-dessous avant d'executer
 */
function setApiTokens() {
  const props = PropertiesService.getScriptProperties();

  // ---- MODIFIER CES VALEURS ----
  props.setProperty('META_ACCESS_TOKEN', 'COLLE_TON_TOKEN_META_ICI');
  props.setProperty('META_AD_ACCOUNT_ID', 'act_XXXXXXXXXX');
  // --------------------------------

  Logger.log('API tokens saved to script properties.');
}

/**
 * Test rapide — lancer manuellement pour verifier que tout marche
 */
function testSync() {
  Logger.log('Testing sync...');
  dailySync();
  Logger.log('Test complete. Check the sheets.');
}
