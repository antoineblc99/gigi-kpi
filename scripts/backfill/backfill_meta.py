"""Backfill Meta Ads → Meta_Ads_Raw (Follow), Meta_Ads_Raw_VSL, AdSet_Raw, Creative_Raw."""
import os
import time
from datetime import date, datetime, timedelta
from typing import Iterable

import requests

from auth import get_sheets_service

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
META_TOKEN = os.environ["META_ACCESS_TOKEN"]
META_BASE = "https://graph.facebook.com/v21.0"

CAMPAIGN_VSL = "120243478827620073"
CAMPAIGN_FOLLOW = "120241957177570073"
IG_USER_ID = "17841448640931967"  # giginails77
ADSETS = {
    "vsl_broad": "120243478853250073",
    "vsl_retargeting": "120243478850530073",
    "follow_broad": "120241964220250073",
    "follow_lookalike": "120241957177550073",
}

COMMON = ("spend,impressions,clicks,cpc,cpm,ctr,reach,frequency,actions,"
          "cost_per_action_type,video_thruplay_watched_actions")
FIELDS_CAMPAIGN = COMMON
FIELDS_ADSET = COMMON + ",adset_name,adset_id"
FIELDS_AD = COMMON + ",ad_name,ad_id,adset_name"

# Meta action_type mappings
ACT_LINK_CLICK = "link_click"
ACT_LPV = "landing_page_view"
ACT_LEAD = "offsite_complete_registration_add_meta_leads"
ACT_POST_ENGAGEMENT = "post_engagement"
ACT_POST_SAVE = "onsite_conversion.post_save"
ACT_POST_REACTION = "post_reaction"
ACT_VIDEO_VIEW = "video_view"


def meta_get(endpoint: str, params: dict) -> dict:
    params = {**params, "access_token": META_TOKEN}
    for attempt in range(3):
        r = requests.get(f"{META_BASE}/{endpoint}", params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"Meta API {r.status_code}: {r.text}")
    raise RuntimeError(f"Meta API retries exhausted on {endpoint}")


def insights(node_id: str, day: str, level: str, fields: str, limit: int = 200) -> list[dict]:
    params = {
        "time_range": f'{{"since":"{day}","until":"{day}"}}',
        "fields": fields,
        "level": level,
        "limit": limit,
    }
    out, url, p = [], f"{META_BASE}/{node_id}/insights", params
    # basic paging
    data = meta_get(f"{node_id}/insights", p)
    out.extend(data.get("data", []))
    while "paging" in data and "next" in data["paging"]:
        r = requests.get(data["paging"]["next"], timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        out.extend(data.get("data", []))
    return out


def av(row: dict, field: str, action_type: str) -> float:
    for a in row.get(field, []) or []:
        if a.get("action_type") == action_type:
            return float(a.get("value", 0))
    return 0


def action_value(row: dict, action_type: str) -> float:
    return av(row, "actions", action_type)


def cost_per_action(row: dict, action_type: str) -> float:
    return av(row, "cost_per_action_type", action_type)


def thruplay(row: dict) -> float:
    return av(row, "video_thruplay_watched_actions", ACT_VIDEO_VIEW)


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def fetch_ig_new_followers(start: date, end: date) -> dict[str, int]:
    """Return {yyyy-mm-dd: new_followers_count} from IG insights.
    IG API limits to last 30 days excluding today, so dates outside that window return 0.
    """
    today = date.today()
    earliest = today - timedelta(days=30)
    yesterday = today - timedelta(days=1)
    effective_start = max(start, earliest)
    effective_end = min(end, yesterday)
    if effective_start > effective_end:
        return {}

    out: dict[str, int] = {}
    data = meta_get(f"{IG_USER_ID}/insights", {
        "metric": "follower_count",
        "period": "day",
        "since": effective_start.isoformat(),
        "until": effective_end.isoformat(),
    })
    for item in data.get("data", []):
        if item.get("name") != "follower_count":
            continue
        for v in item.get("values", []):
            ts = v.get("end_time", "")[:10]
            if ts:
                out[ts] = int(v.get("value", 0) or 0)
    return out


def fetch_ig_total_followers() -> int:
    data = meta_get(IG_USER_ID, {"fields": "followers_count"})
    return int(data.get("followers_count", 0) or 0)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- Row builders aligned to sheet headers ----------

def row_follow_campaign(day: str, r: dict, new_followers: int, ig_total: int) -> list:
    """Meta_Ads_Raw (15 cols): Date|Spend|Imp|Clicks|CPM|CPC|CTR|Reach|Followers|PV|Results|Cost/Result|Cost/Follower|Last Updated|IG Total"""
    spend = float(r.get("spend", 0) or 0)
    profile_visits = action_value(r, ACT_LINK_CLICK)
    cost_pv = cost_per_action(r, ACT_LINK_CLICK)
    cost_per_follower = round(spend / new_followers, 2) if new_followers > 0 else ""
    return [
        day,
        spend,
        int(r.get("impressions", 0) or 0),
        int(r.get("clicks", 0) or 0),
        float(r.get("cpm", 0) or 0),
        float(r.get("cpc", 0) or 0),
        float(r.get("ctr", 0) or 0),
        int(r.get("reach", 0) or 0),
        new_followers,
        profile_visits,
        profile_visits,  # Results = link_click pour campagne OUTCOME_TRAFFIC
        cost_pv,  # Cost/Result
        cost_per_follower,
        now_iso(),
        ig_total,
    ]


def row_vsl_campaign(day: str, r: dict) -> list:
    """Meta_Ads_Raw_VSL (13 cols): Date|Spend|Imp|Reach|Freq|CTR|LinkClicks|CPC|LPV|LPV Rate|Opt-ins|CPL|Last Updated"""
    spend = float(r.get("spend", 0) or 0)
    link_clicks = action_value(r, ACT_LINK_CLICK)
    lpv = action_value(r, ACT_LPV)
    leads = action_value(r, ACT_LEAD)
    lpv_rate = (lpv / link_clicks * 100) if link_clicks else 0
    cpl = (spend / leads) if leads else 0
    return [
        day,
        spend,
        int(r.get("impressions", 0) or 0),
        int(r.get("reach", 0) or 0),
        float(r.get("frequency", 0) or 0),
        float(r.get("ctr", 0) or 0),
        link_clicks,
        float(r.get("cpc", 0) or 0),
        lpv,
        round(lpv_rate, 2),
        leads,
        round(cpl, 2),
        now_iso(),
    ]


def row_adset(day: str, fallback_name: str, r: dict) -> list:
    """AdSet_Raw (19 cols): Date|AdSet|ID|Spend|Imp|Clicks|CPM|CPC|CTR|Reach|PV|Cost/PV|VideoViews|Engagements|Saves|Likes|ThruPlay|Freq|LastUpdated"""
    return [
        day,
        r.get("adset_name") or fallback_name,
        r.get("adset_id", ""),
        float(r.get("spend", 0) or 0),
        int(r.get("impressions", 0) or 0),
        int(r.get("clicks", 0) or 0),
        float(r.get("cpm", 0) or 0),
        float(r.get("cpc", 0) or 0),
        float(r.get("ctr", 0) or 0),
        int(r.get("reach", 0) or 0),
        action_value(r, ACT_LINK_CLICK),
        cost_per_action(r, ACT_LINK_CLICK),
        action_value(r, ACT_VIDEO_VIEW),
        action_value(r, ACT_POST_ENGAGEMENT),
        action_value(r, ACT_POST_SAVE),
        action_value(r, ACT_POST_REACTION),
        thruplay(r),
        float(r.get("frequency", 0) or 0),
        now_iso(),
    ]


def row_creative(day: str, r: dict) -> list:
    """Creative_Raw (20 cols): Date|AdName|AdID|AdSet|Spend|Imp|Clicks|CPM|CPC|CTR|Reach|PV|Cost/PV|VideoViews|Engagements|Saves|Likes|ThruPlay|Freq|LastUpdated"""
    return [
        day,
        r.get("ad_name", ""),
        r.get("ad_id", ""),
        r.get("adset_name", ""),
        float(r.get("spend", 0) or 0),
        int(r.get("impressions", 0) or 0),
        int(r.get("clicks", 0) or 0),
        float(r.get("cpm", 0) or 0),
        float(r.get("cpc", 0) or 0),
        float(r.get("ctr", 0) or 0),
        int(r.get("reach", 0) or 0),
        action_value(r, ACT_LINK_CLICK),
        cost_per_action(r, ACT_LINK_CLICK),
        action_value(r, ACT_VIDEO_VIEW),
        action_value(r, ACT_POST_ENGAGEMENT),
        action_value(r, ACT_POST_SAVE),
        action_value(r, ACT_POST_REACTION),
        thruplay(r),
        float(r.get("frequency", 0) or 0),
        now_iso(),
    ]


# ---------- Sheet I/O ----------

def append_rows(sheets, tab: str, rows: list[list]) -> int:
    if not rows:
        return 0
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


def existing_days(sheets, tab: str) -> set[str]:
    resp = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{tab}!A2:A"
    ).execute()
    return {str(v[0]) for v in resp.get("values", []) if v}


# ---------- Main ----------

def run(start: date, end: date, force: bool = False) -> None:
    sheets = get_sheets_service()

    # IG follower data (fetched once for the whole range)
    try:
        ig_new = fetch_ig_new_followers(start, end)
        ig_total = fetch_ig_total_followers()
    except RuntimeError as err:
        print(f"IG insights error: {err} — using 0")
        ig_new, ig_total = {}, 0

    follow_done = set() if force else existing_days(sheets, "Meta_Ads_Raw")
    vsl_done = set() if force else existing_days(sheets, "Meta_Ads_Raw_VSL")
    adset_done = set() if force else existing_days(sheets, "AdSet_Raw")
    creative_done = set() if force else existing_days(sheets, "Creative_Raw")

    follow_rows, vsl_rows, adset_rows, creative_rows = [], [], [], []

    for d in daterange(start, end):
        day = d.isoformat()
        print(f"→ {day}")

        if day not in follow_done:
            for r in insights(CAMPAIGN_FOLLOW, day, "campaign", FIELDS_CAMPAIGN):
                if float(r.get("spend", 0) or 0) > 0:
                    follow_rows.append(row_follow_campaign(day, r, ig_new.get(day, 0), ig_total))

        if day not in vsl_done:
            for r in insights(CAMPAIGN_VSL, day, "campaign", FIELDS_CAMPAIGN):
                if float(r.get("spend", 0) or 0) > 0:
                    vsl_rows.append(row_vsl_campaign(day, r))

        if day not in adset_done:
            for label, aid in ADSETS.items():
                for r in insights(aid, day, "adset", FIELDS_ADSET):
                    if float(r.get("spend", 0) or 0) > 0:
                        adset_rows.append(row_adset(day, label, r))

        if day not in creative_done:
            for cid in (CAMPAIGN_VSL, CAMPAIGN_FOLLOW):
                for r in insights(cid, day, "ad", FIELDS_AD):
                    if float(r.get("spend", 0) or 0) > 0:
                        creative_rows.append(row_creative(day, r))

    n1 = append_rows(sheets, "Meta_Ads_Raw", follow_rows)
    n2 = append_rows(sheets, "Meta_Ads_Raw_VSL", vsl_rows)
    n3 = append_rows(sheets, "AdSet_Raw", adset_rows)
    n4 = append_rows(sheets, "Creative_Raw", creative_rows)
    print(f"✅ Follow +{n1} | VSL +{n2} | AdSet +{n3} | Creative +{n4}")


if __name__ == "__main__":
    import argparse
    from dateutil.parser import parse as parse_date

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2026-03-05")
    ap.add_argument("--to", dest="end", default=date.today().isoformat())
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    run(parse_date(args.start).date(), parse_date(args.end).date(), force=args.force)
