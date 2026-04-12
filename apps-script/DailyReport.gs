// ============================================================
// DailyReport.gs — Jointure des données + écriture BASE sheets
// S'appuie sur les données déjà synchées par Meta Ads.gs et GHL_Sync.gs
// ============================================================

// ---- IDs des AdSets par funnel ----
var VSL_ADSET_IDS = ['120243478853250073', '120243478850530073'];
var FOLLOW_ADSET_IDS = ['120241964220250073', '120241957177550073'];

// ---- IDs des calendriers GHL ----
var CAL_VSL_ID = '8ECqPVcPGz81JGlzCmoG';
var CAL_FOLLOW_ID = 'AQ8RmdYw7iyru79Axymf';

// ---- Slack Webhook (optionnel) ----
// Creer un webhook Slack : https://api.slack.com/messaging/webhooks
var SLACK_WEBHOOK_URL = PropertiesService.getScriptProperties().getProperty('SLACK_WEBHOOK_URL') || '';

// ============================================================
// FONCTION PRINCIPALE — A lancer apres Meta Ads + GHL sync
// ============================================================
function buildDailyReport() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  var dateISO = Utilities.formatDate(yesterday, 'Europe/Paris', 'yyyy-MM-dd');
  var dateFR = Utilities.formatDate(yesterday, 'Europe/Paris', 'dd/MM');
  var dateFRFull = Utilities.formatDate(yesterday, 'Europe/Paris', 'dd/MM/yyyy');

  Logger.log('=== Building Daily Report for ' + dateISO + ' ===');

  // 1. Lire AdSet_Raw pour separer VSL vs Follow
  var adsetData = readAdSetDataForDate(ss, dateISO);

  // 2. Agreger par funnel
  var vslMetrics = aggregateAdSets(adsetData, VSL_ADSET_IDS);
  var followMetrics = aggregateAdSets(adsetData, FOLLOW_ADSET_IDS);

  // 3. Lire GHL_Raw_Data pour les calls
  var ghlData = readGHLDataForDate(ss, dateFRFull);

  // 4. Lire les calls par calendrier (GHL_Calls_Raw ou GHL_Raw_Data)
  var vslCalls = getCallsForCalendar(ss, dateISO, CAL_VSL_ID);
  var followCalls = getCallsForCalendar(ss, dateISO, CAL_FOLLOW_ID);

  // 5. Lire KPI Closer pour le closing du jour
  var closingData = readCloserEOD(ss, yesterday);

  // 6. Ecrire Data_Funnel_VSL
  writeDataFunnelVSL(ss, dateFR, vslMetrics, vslCalls, closingData);

  // 7. Ecrire Data_Funnel_Follow
  writeDataFunnelFollow(ss, dateFR, followMetrics, followCalls, closingData);

  // 8. Envoyer Slack report (si webhook configure)
  if (SLACK_WEBHOOK_URL) {
    sendSlackReport(dateFR, vslMetrics, followMetrics, vslCalls, followCalls, closingData);
  }

  Logger.log('=== Daily Report complete ===');
}

// ============================================================
// LECTURE AdSet_Raw
// ============================================================
function readAdSetDataForDate(ss, dateISO) {
  var sheet = ss.getSheetByName('AdSet_Raw');
  if (!sheet || sheet.getLastRow() <= 1) return [];

  var data = sheet.getDataRange().getValues();
  var headers = data[0];
  var results = [];

  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    var cellDate = row[0];
    var cellDateStr = '';

    if (cellDate instanceof Date) {
      cellDateStr = Utilities.formatDate(cellDate, 'Europe/Paris', 'yyyy-MM-dd');
    } else {
      cellDateStr = String(cellDate);
    }

    if (cellDateStr === dateISO) {
      results.push({
        adsetName: String(row[1] || ''),
        adsetId: String(row[2] || ''),
        spend: parseFloat(row[3] || 0),
        impressions: parseInt(row[4] || 0),
        clicks: parseInt(row[5] || 0),
        cpm: parseFloat(row[6] || 0),
        cpc: parseFloat(row[7] || 0),
        ctr: parseFloat(row[8] || 0),
        reach: parseInt(row[9] || 0),
        profileVisits: parseInt(row[10] || 0),
        costPerPV: parseFloat(row[11] || 0),
        videoViews: parseInt(row[12] || 0),
        engagements: parseInt(row[13] || 0),
        saves: parseInt(row[14] || 0),
        likes: parseInt(row[15] || 0)
      });
    }
  }

  return results;
}

function aggregateAdSets(allData, adsetIds) {
  var result = {
    spend: 0, impressions: 0, clicks: 0, ctr: 0, cpc: 0,
    reach: 0, profileVisits: 0, videoViews: 0, engagements: 0
  };

  var matched = allData.filter(function(row) {
    return adsetIds.indexOf(row.adsetId) !== -1;
  });

  matched.forEach(function(row) {
    result.spend += row.spend;
    result.impressions += row.impressions;
    result.clicks += row.clicks;
    result.reach += row.reach;
    result.profileVisits += row.profileVisits;
    result.videoViews += row.videoViews;
    result.engagements += row.engagements;
  });

  if (result.impressions > 0) {
    result.ctr = Math.round((result.clicks / result.impressions) * 10000) / 100;
  }
  if (result.clicks > 0) {
    result.cpc = Math.round((result.spend / result.clicks) * 1000) / 1000;
  }

  return result;
}

// ============================================================
// LECTURE GHL_Raw_Data
// ============================================================
function readGHLDataForDate(ss, dateFRFull) {
  var sheet = ss.getSheetByName('GHL_Raw_Data');
  if (!sheet || sheet.getLastRow() <= 1) return null;

  var data = sheet.getDataRange().getValues();

  for (var i = 1; i < data.length; i++) {
    var cellDate = data[i][0];
    var normalized = '';
    if (cellDate instanceof Date) {
      normalized = Utilities.formatDate(cellDate, 'Europe/Paris', 'dd/MM/yyyy');
    } else {
      normalized = String(cellDate);
    }

    if (normalized === dateFRFull) {
      return {
        booked: parseInt(data[i][1] || 0),
        confirmed: parseInt(data[i][2] || 0),
        cancelled: parseInt(data[i][3] || 0),
        new_: parseInt(data[i][4] || 0),
        showed: parseInt(data[i][5] || 0),
        noshow: parseInt(data[i][6] || 0)
      };
    }
  }

  return { booked: 0, confirmed: 0, cancelled: 0, new_: 0, showed: 0, noshow: 0 };
}

// ============================================================
// CALLS PAR CALENDRIER — via API GHL directe
// ============================================================
function getCallsForCalendar(ss, dateISO, calendarId) {
  try {
    var cfg = ss.getSheetByName('GHL_Config');
    var apiKey = cfg.getRange('B2').getValue();
    var locationId = 'TTzAZhJJwPHQobNiXjWJ';

    var startTime = new Date(dateISO + 'T00:00:00+02:00').getTime();
    var endTime = new Date(dateISO + 'T23:59:59+02:00').getTime();

    var url = 'https://services.leadconnectorhq.com/calendars/events'
      + '?locationId=' + locationId
      + '&calendarId=' + calendarId
      + '&startTime=' + startTime
      + '&endTime=' + endTime;

    var response = UrlFetchApp.fetch(url, {
      headers: {
        'Authorization': 'Bearer ' + apiKey,
        'Version': '2021-07-28',
        'Content-Type': 'application/json'
      },
      muteHttpExceptions: true
    });

    var data = JSON.parse(response.getContentText());
    var events = (data.events || []).filter(function(e) { return !e.deleted; });

    var counts = { booked: 0, confirmed: 0, showed: 0, cancelled: 0, noshow: 0 };
    events.forEach(function(e) {
      counts.booked++;
      var status = (e.appointmentStatus || '').toLowerCase();
      if (status === 'confirmed') counts.confirmed++;
      if (status === 'showed') counts.showed++;
      if (status === 'cancelled') counts.cancelled++;
      if (status === 'no_show') counts.noshow++;
    });

    return counts;
  } catch (e) {
    Logger.log('Error getting calls for calendar ' + calendarId + ': ' + e.message);
    return { booked: 0, confirmed: 0, showed: 0, cancelled: 0, noshow: 0 };
  }
}

// ============================================================
// LECTURE KPI Closer du jour
// ============================================================
function readCloserEOD(ss, targetDate) {
  var sheet = ss.getSheetByName('KPI Closer_Léa');
  if (!sheet || sheet.getLastRow() <= 1) return { closers: [], totalCalls: 0, totalVentes: 0, totalCash: 0 };

  var data = sheet.getDataRange().getValues();
  var targetStr = Utilities.formatDate(targetDate, 'Europe/Paris', 'M/d/yyyy');
  var closers = [];
  var totalCalls = 0, totalVentes = 0, totalCashContracte = 0, totalCashCollecte = 0;

  for (var i = 1; i < data.length; i++) {
    var submittedAt = String(data[i][18] || ''); // Column S = Submitted At
    if (submittedAt.indexOf(targetStr) === -1) continue;

    var closer = {
      name: String(data[i][0] || ''),
      callsPlanifies: parseInt(data[i][1] || 0),
      callsRecus: parseInt(data[i][2] || 0),
      followUps: parseInt(data[i][3] || 0),
      acomptes: parseInt(data[i][4] || 0),
      ventes: parseInt(data[i][5] || 0),
      cashContracte: parseFloat(data[i][6] || 0),
      cashCollecte: parseFloat(data[i][7] || 0),
      qualifLeads: parseInt(data[i][16] || 0),
      debrief: String(data[i][17] || '')
    };

    closers.push(closer);
    totalCalls += closer.callsRecus;
    totalVentes += closer.ventes;
    totalCashContracte += closer.cashContracte;
    totalCashCollecte += closer.cashCollecte;
  }

  return {
    closers: closers,
    totalCalls: totalCalls,
    totalVentes: totalVentes,
    totalCashContracte: totalCashContracte,
    totalCashCollecte: totalCashCollecte
  };
}

// ============================================================
// ECRITURE Data_Funnel_VSL
// ============================================================
function writeDataFunnelVSL(ss, dateFR, metrics, calls, closing) {
  var sheet = ss.getSheetByName('Data_Funnel_VSL');
  if (!sheet) return;

  var coutCall = calls.booked > 0 ? Math.round(metrics.spend / calls.booked * 100) / 100 : '-';
  var coutVente = closing.totalVentes > 0 ? Math.round(metrics.spend / closing.totalVentes * 100) / 100 : '-';
  var roas = metrics.spend > 0 && closing.totalCashCollecte > 0
    ? Math.round(closing.totalCashCollecte / metrics.spend * 100) / 100 : 0;

  // Opt-ins = complete_registration from Meta (pas dispo dans AdSet_Raw, on met 0 pour l'instant)
  var row = [
    dateFR,                   // Date
    metrics.spend,            // Ad Spend
    metrics.impressions,      // Impressions
    metrics.clicks,           // Link Clicks
    metrics.ctr,              // CTR
    metrics.cpc,              // CPC
    '',                       // LPV (pas dans AdSet_Raw)
    '',                       // Opt-ins (pas dans AdSet_Raw, a enrichir)
    '',                       // Taux Opt-in
    '',                       // Surveys
    '',                       // Taux Survey
    '',                       // Qualifies
    '',                       // Taux Qualif
    calls.booked,             // Calls Bookes
    '',                       // Taux Booking
    calls.showed,             // Calls Recus
    '',                       // Taux Show
    closing.totalVentes,      // Ventes
    '',                       // Taux Closing
    closing.totalCashContracte, // Cash Contracte
    closing.totalCashCollecte,  // Cash Collecte
    '',                       // Cout/Opt-in
    coutCall,                 // Cout/Call
    coutVente,                // Cout/Vente
    roas                      // ROAS
  ];

  upsertDailyRow(sheet, dateFR, row);
  Logger.log('Data_Funnel_VSL written for ' + dateFR);
}

// ============================================================
// ECRITURE Data_Funnel_Follow
// ============================================================
function writeDataFunnelFollow(ss, dateFR, metrics, calls, closing) {
  var sheet = ss.getSheetByName('Data_Funnel_Follow');
  if (!sheet) return;

  var coutPV = metrics.profileVisits > 0
    ? Math.round(metrics.spend / metrics.profileVisits * 1000) / 1000 : '-';
  var coutCall = calls.booked > 0
    ? Math.round(metrics.spend / calls.booked * 100) / 100 : '-';

  var row = [
    dateFR,                   // Date
    metrics.spend,            // Ad Spend
    metrics.impressions,      // Impressions
    metrics.clicks,           // Clicks
    metrics.ctr,              // CTR
    metrics.cpc,              // CPC
    metrics.reach,            // Reach
    metrics.profileVisits,    // Profile Visits
    coutPV,                   // Cout/PV
    '',                       // New Followers (from Meta_Ads_Raw)
    '',                       // Cout/Follower
    '',                       // DMs envoyes (from setter)
    '',                       // Liens envoyes (from setter)
    '',                       // Taux Lien
    calls.booked,             // Calls Bookes
    '',                       // Taux Booking
    calls.showed,             // Calls Recus
    '',                       // Taux Show
    0,                        // Ventes (closing commun, dur a splitter)
    '',                       // Taux Closing
    0,                        // Cash Contracte
    0,                        // Cash Collecte
    coutCall,                 // Cout/Call
    '-',                      // Cout/Vente
    0                         // ROAS
  ];

  upsertDailyRow(sheet, dateFR, row);
  Logger.log('Data_Funnel_Follow written for ' + dateFR);
}

// ============================================================
// UPSERT : mise a jour si la date existe, sinon append
// ============================================================
function upsertDailyRow(sheet, dateFR, rowData) {
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    var dates = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
    for (var i = 0; i < dates.length; i++) {
      if (String(dates[i][0]).trim() === dateFR) {
        sheet.getRange(i + 2, 1, 1, rowData.length).setValues([rowData]);
        return;
      }
    }
  }
  sheet.appendRow(rowData);
}

// ============================================================
// SLACK REPORT
// ============================================================
function sendSlackReport(dateFR, vsl, follow, vslCalls, followCalls, closing) {
  var closerLines = '';
  closing.closers.forEach(function(c) {
    closerLines += c.name + ': ' + c.callsRecus + ' calls, '
      + c.ventes + ' ventes, ' + c.cashCollecte + '€ collecte'
      + (c.qualifLeads > 0 ? ' | Qualif: ' + c.qualifLeads + '/10' : '') + '\n';
  });

  if (!closerLines) closerLines = '_En attente des EOD closers_\n';

  var message = ':bar_chart: *Daily Report Gigi Academy — ' + dateFR + '*\n'
    + '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
    + ':dart: *FUNNEL VSL (Lead)*\n'
    + 'Spend: ' + vsl.spend + '€ | Impressions: ' + vsl.impressions + ' | Clicks: ' + vsl.clicks + '\n'
    + 'CTR: ' + vsl.ctr + '% | CPC: ' + vsl.cpc + '€\n'
    + 'Calls bookes: ' + vslCalls.booked + ' | Calls recus: ' + vslCalls.showed + '\n'
    + '\n'
    + ':iphone: *FUNNEL FOLLOW (Traffic)*\n'
    + 'Spend: ' + follow.spend + '€ | Impressions: ' + follow.impressions + ' | Clicks: ' + follow.clicks + '\n'
    + 'Profile Visits: ' + follow.profileVisits + ' | CTR: ' + follow.ctr + '% | CPC: ' + follow.cpc + '€\n'
    + 'Calls bookes: ' + followCalls.booked + ' | Calls recus: ' + followCalls.showed + '\n'
    + '\n'
    + ':moneybag: *CLOSING*\n'
    + closerLines
    + 'Total: ' + closing.totalVentes + ' ventes | ' + closing.totalCashContracte + '€ contracte | ' + closing.totalCashCollecte + '€ collecte\n'
    + '\n'
    + ':robot_face: _Report auto — Gigi KPI_';

  var payload = JSON.stringify({ text: message });

  UrlFetchApp.fetch(SLACK_WEBHOOK_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: payload,
    muteHttpExceptions: true
  });

  Logger.log('Slack report sent.');
}

// ============================================================
// SETUP TRIGGER — a lancer une seule fois
// ============================================================
function setupReportTrigger() {
  // Supprimer les anciens triggers
  ScriptApp.getProjectTriggers()
    .filter(function(t) { return t.getHandlerFunction() === 'buildDailyReport'; })
    .forEach(function(t) { ScriptApp.deleteTrigger(t); });

  // Creer le trigger quotidien a 21h30 Europe/Paris
  ScriptApp.newTrigger('buildDailyReport')
    .timeBased()
    .atHour(21)
    .nearMinute(30)
    .everyDays(1)
    .inTimezone('Europe/Paris')
    .create();

  Logger.log('Trigger set: buildDailyReport at 21:30 Europe/Paris daily');
}

// ============================================================
// TEST MANUEL
// ============================================================
function testReport() {
  buildDailyReport();
}
