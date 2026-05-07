/**
 * gigi-data-os — UTM Tracker
 *
 * Captures UTM + click params on first arrival, persists them in cookie+localStorage
 * for 30 days, and auto-fills any matching hidden form fields.
 *
 * Convention (Meta Ads):
 *   utm_source   = facebook | instagram | manual
 *   utm_medium   = paid | organic | dm
 *   utm_campaign = {{campaign.id}}
 *   utm_content  = {{ad.id}}        ← used as attribution_ad_id
 *   utm_term     = {{adset.id}}
 *   fbclid       = (auto, Meta click id)
 *
 * Usage on giginails.com landing pages:
 *   <script src="/utm-tracker.js" defer></script>
 *
 * Or inline (Webflow / GHL / static site head):
 *   <script>{{ paste contents of this file }}</script>
 */
(function () {
  'use strict';

  var TRACKED_PARAMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid'];
  var COOKIE_NAME = 'gigi_attribution';
  var STORAGE_KEY = 'gigi_attribution';
  var COOKIE_DAYS = 30;
  var DOMAIN = (function () {
    var h = location.hostname;
    if (!h || h === 'localhost') return null;
    var parts = h.split('.');
    if (parts.length <= 2) return h;
    return '.' + parts.slice(-2).join('.');
  })();

  function readQuery() {
    var qs = location.search.replace(/^\?/, '');
    if (!qs) return {};
    var out = {};
    qs.split('&').forEach(function (kv) {
      if (!kv) return;
      var eq = kv.indexOf('=');
      var k = decodeURIComponent(eq < 0 ? kv : kv.slice(0, eq));
      var v = eq < 0 ? '' : decodeURIComponent(kv.slice(eq + 1).replace(/\+/g, ' '));
      if (TRACKED_PARAMS.indexOf(k) !== -1 && v) out[k] = v;
    });
    return out;
  }

  function readStored() {
    try {
      var ls = localStorage.getItem(STORAGE_KEY);
      if (ls) return JSON.parse(ls);
    } catch (_) {}
    var match = document.cookie.match(new RegExp('(?:^|;\\s*)' + COOKIE_NAME + '=([^;]+)'));
    if (match) {
      try { return JSON.parse(decodeURIComponent(match[1])); } catch (_) {}
    }
    return null;
  }

  function persist(data) {
    var payload = JSON.stringify(data);
    try { localStorage.setItem(STORAGE_KEY, payload); } catch (_) {}
    var exp = new Date(Date.now() + COOKIE_DAYS * 864e5).toUTCString();
    var cookie = COOKIE_NAME + '=' + encodeURIComponent(payload) + ';expires=' + exp + ';path=/;SameSite=Lax';
    if (DOMAIN) cookie += ';domain=' + DOMAIN;
    document.cookie = cookie;
  }

  function fillHiddenInputs(data) {
    Object.keys(data).forEach(function (key) {
      var inputs = document.querySelectorAll(
        'input[name="' + key + '"], input[name="' + key.replace('utm_', '') + '"]'
      );
      inputs.forEach(function (el) {
        if (!el.value) el.value = data[key];
      });
    });
    // Also expose attribution_ad_id alias (= utm_content)
    if (data.utm_content) {
      var aid = document.querySelectorAll('input[name="attribution_ad_id"]');
      aid.forEach(function (el) { if (!el.value) el.value = data.utm_content; });
    }
  }

  // --- run --------------------------------------------------------------------
  var fresh = readQuery();
  var stored = readStored() || {};
  var merged = {};
  TRACKED_PARAMS.forEach(function (k) {
    var v = fresh[k] || stored[k];
    if (v) merged[k] = v;
  });
  if (fresh.utm_source) {
    // New campaign click → overwrite stale attribution
    merged = Object.assign({}, fresh);
    merged.first_seen_at = new Date().toISOString();
  } else if (!stored.first_seen_at && Object.keys(merged).length) {
    merged.first_seen_at = new Date().toISOString();
  } else if (stored.first_seen_at) {
    merged.first_seen_at = stored.first_seen_at;
  }

  if (Object.keys(merged).length) persist(merged);

  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }
  ready(function () { fillHiddenInputs(merged); });

  // expose for debugging / programmatic access
  window.gigiAttribution = {
    get: function () { return readStored() || {}; },
    fill: function () { fillHiddenInputs(readStored() || {}); }
  };
})();
