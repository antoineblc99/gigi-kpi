"""pull_meta.py — Meta Ads → Supabase (gigi-data-os).

Pull complet :
  - Campaigns → dim_campaign
  - AdSets    → dim_adset
  - Ads       → dim_ad
  - Creatives → dim_creative
  - Insights par ad par jour (default 90j) → fact_ad_daily

Usage:
  python pipelines/pull_meta.py --days 7 --dry-run
  python pipelines/pull_meta.py --days 90
  python pipelines/pull_meta.py --since 2026-04-01

Idempotent : upsert (PK = id pour dims, (ad_id, date) pour fact).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# Permettre exécution depuis n'importe où
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.meta_client import MetaClient, action_value  # noqa: E402
from lib.db import upsert as sb_upsert  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")


# ─── Action types Meta ────────────────────────────────────────────────────
ACT_LINK_CLICK = "link_click"
ACT_LPV = "landing_page_view"
ACT_VIDEO_VIEW = "video_view"
ACT_POST_ENGAGEMENT = "post_engagement"
ACT_LEAD = "offsite_complete_registration_add_meta_leads"
ACT_COMPLETE_REG = "complete_registration"


# ─── Helpers ──────────────────────────────────────────────────────────────
def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()
    except Exception:
        return None


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ─── Pulls ────────────────────────────────────────────────────────────────
def pull_campaigns(meta: MetaClient, account_id: str) -> list[dict]:
    """→ dim_campaign(campaign_id, name, objective, status)"""
    rows = []
    fields = "id,name,objective,status,effective_status"
    for c in meta.paginate(f"{account_id}/campaigns", {"fields": fields}):
        rows.append({
            "campaign_id": c["id"],
            "name": c.get("name", ""),
            "objective": c.get("objective"),
            "status": c.get("effective_status") or c.get("status"),
        })
    return rows


def pull_adsets(meta: MetaClient, account_id: str) -> list[dict]:
    """→ dim_adset(adset_id, campaign_id, name, status)"""
    rows = []
    fields = "id,name,campaign_id,status,effective_status"
    for a in meta.paginate(f"{account_id}/adsets", {"fields": fields}):
        rows.append({
            "adset_id": a["id"],
            "campaign_id": a.get("campaign_id"),
            "name": a.get("name", ""),
            "status": a.get("effective_status") or a.get("status"),
        })
    return rows


def pull_ads(meta: MetaClient, account_id: str) -> tuple[list[dict], dict[str, str]]:
    """→ dim_ad(ad_id, name, campaign_id, adset_id, hook_text, format, duration_sec, thumbnail_url, created_at)
    Retourne aussi mapping ad_id → creative_id pour la suite.
    """
    rows = []
    ad_to_creative: dict[str, str] = {}
    fields = "id,name,adset_id,campaign_id,creative,status,effective_status,created_time"
    for a in meta.paginate(f"{account_id}/ads", {"fields": fields}):
        cid = (a.get("creative") or {}).get("id")
        if cid:
            ad_to_creative[a["id"]] = cid
        rows.append({
            "ad_id": a["id"],
            "name": a.get("name", ""),
            "campaign_id": a.get("campaign_id"),
            "adset_id": a.get("adset_id"),
            "hook_text": None,        # complété après pull_creatives
            "format": None,
            "duration_sec": None,
            "thumbnail_url": None,
            "created_at": parse_dt(a.get("created_time")),
        })
    return rows, ad_to_creative


def pull_creatives(meta: MetaClient, creative_ids: list[str]) -> list[dict]:
    """→ dim_creative(creative_id, video_id, hook_transcript, body_text, cta)"""
    rows = []
    fields = ("id,name,title,body,call_to_action_type,video_id,image_hash,"
              "thumbnail_url,object_story_spec")
    for cid in creative_ids:
        try:
            c = meta.get(cid, {"fields": fields})
        except Exception as e:
            print(f"  ⚠️  creative {cid}: {e}")
            continue
        oss = c.get("object_story_spec") or {}
        body = (c.get("body")
                or (oss.get("video_data") or {}).get("message")
                or (oss.get("link_data") or {}).get("message")
                or "")
        cta = (c.get("call_to_action_type")
               or ((oss.get("video_data") or {}).get("call_to_action") or {}).get("type")
               or ((oss.get("link_data") or {}).get("call_to_action") or {}).get("type"))
        hook = body.strip().split("\n", 1)[0][:280] if body else None
        rows.append({
            "creative_id": c["id"],
            "video_id": c.get("video_id") or (oss.get("video_data") or {}).get("video_id"),
            "hook_transcript": hook,
            "body_text": body,
            "cta": cta,
            # extras gardés pour enrich dim_ad
            "_thumbnail_url": c.get("thumbnail_url"),
        })
    return rows


def pull_insights(meta: MetaClient, account_id: str, since: date, until: date,
                  event_optin: str, event_call_booked: str,
                  event_complete_reg: str, event_lead: str) -> list[dict]:
    """Insights par ad par jour. Un appel par jour pour bornes nettes + idempotence."""
    rows = []
    fields = ("ad_id,ad_name,adset_id,campaign_id,date_start,"
              "spend,impressions,clicks,ctr,cpc,cpm,reach,frequency,"
              "actions,cost_per_action_type")

    for d in daterange(since, until):
        day = d.isoformat()
        params = {
            "level": "ad",
            "fields": fields,
            "time_range": f'{{"since":"{day}","until":"{day}"}}',
            "time_increment": 1,
            "limit": 500,
            "filtering": '[]',
        }
        try:
            for r in meta.paginate(f"{account_id}/insights", params):
                spend = to_float(r.get("spend"))
                if spend == 0 and not r.get("actions"):
                    # skip rows totalement vides
                    continue
                actions = r.get("actions") or []
                cpa = r.get("cost_per_action_type") or []
                lpv = to_int(action_value(r, "actions", ACT_LPV))
                # followers_ig: Meta /insights API does NOT expose IG follower count nor
                # profile_visit_view at the actions level (only available in Ads Manager UI
                # via a separate breakdown). For Follow funnel macro tracking, use LPV as
                # weak proxy or pull Instagram Graph API followers_count delta separately.
                # TODO: integrate IG Graph /me/business_discovery for daily follower delta.
                followers_ig = to_int(action_value(r, "actions", "profile_visit_view"))
                # VSL custom Pixel events come back as offsite_conversion.custom.{id}.
                # IDs configured in .env.local META_EVENT_VSL_OPTIN / META_EVENT_VSL_CALL_BOOKED.
                vsl_optin = to_int(action_value(r, "actions", event_optin))
                vsl_call_booked = to_int(action_value(r, "actions", event_call_booked))
                # results = volume de l'event "principal" de la campagne (objective-driven).
                # Heuristique : VSL_OptIn > leads > link_clicks
                leads = to_int(action_value(r, "actions", event_lead) or action_value(r, "actions", ACT_LEAD))
                link_clicks = to_int(action_value(r, "actions", ACT_LINK_CLICK))
                results = vsl_optin or leads or link_clicks
                cost_per_result = round(spend / results, 4) if results else None
                rows.append({
                    "ad_id": r["ad_id"],
                    "date": r.get("date_start", day),
                    "spend": spend,
                    "impressions": to_int(r.get("impressions")),
                    "clicks": to_int(r.get("clicks")),
                    "lpv": lpv,
                    "results": results,
                    "cost_per_result": cost_per_result,
                    "ctr": to_float(r.get("ctr")),
                    "cpc": to_float(r.get("cpc")),
                    "cpm": to_float(r.get("cpm")),
                    "reach": to_int(r.get("reach")),
                    "followers_ig": followers_ig,
                    "vsl_optin": vsl_optin,
                    "vsl_call_booked": vsl_call_booked,
                })
        except Exception as e:
            print(f"  ⚠️  insights {day}: {e}")
            continue
    return rows


# ─── Main ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Pull Meta Ads → Supabase")
    ap.add_argument("--days", type=int, default=90, help="Backfill N derniers jours (défaut 90)")
    ap.add_argument("--since", help="Date de début YYYY-MM-DD (override --days)")
    ap.add_argument("--until", help="Date de fin YYYY-MM-DD (défaut hier)")
    ap.add_argument("--dry-run", action="store_true", help="Pas d'écriture Supabase")
    ap.add_argument("--account-id", default=os.environ.get("META_AD_ACCOUNT_ID", "act_517774784676541"))
    args = ap.parse_args()

    until = date.fromisoformat(args.until) if args.until else date.today() - timedelta(days=0)
    since = date.fromisoformat(args.since) if args.since else until - timedelta(days=args.days - 1)

    event_optin = os.environ.get("META_EVENT_VSL_OPTIN", "VSL_OptIn")
    event_call_booked = os.environ.get("META_EVENT_VSL_CALL_BOOKED", "VSL_Call_Booked")
    event_lead = os.environ.get("META_EVENT_LEAD", ACT_LEAD)
    event_complete_reg = os.environ.get("META_EVENT_COMPLETE_REGISTRATION", ACT_COMPLETE_REG)

    print(f"━━━ pull_meta.py ━━━ account {args.account_id} ━━━ {since} → {until} ━━━")
    if args.dry_run:
        print("⚠️  DRY-RUN — aucune écriture Supabase")

    t0 = time.time()
    meta = MetaClient()

    # 1. Campaigns
    print("→ Campaigns…")
    campaigns = pull_campaigns(meta, args.account_id)
    print(f"  {len(campaigns)} campaigns")

    # 2. AdSets
    print("→ AdSets…")
    adsets = pull_adsets(meta, args.account_id)
    print(f"  {len(adsets)} adsets")

    # 3. Ads
    print("→ Ads…")
    ads, ad_to_creative = pull_ads(meta, args.account_id)
    creative_ids = sorted(set(ad_to_creative.values()))
    print(f"  {len(ads)} ads, {len(creative_ids)} unique creatives")

    # 4. Creatives
    print("→ Creatives…")
    creatives = pull_creatives(meta, creative_ids)
    print(f"  {len(creatives)} creatives détaillées")

    # Enrichit dim_ad avec hook_text + thumbnail_url depuis creatives
    cmap = {c["creative_id"]: c for c in creatives}
    for a in ads:
        cid = ad_to_creative.get(a["ad_id"])
        c = cmap.get(cid) if cid else None
        if c:
            a["hook_text"] = c.get("hook_transcript")
            a["thumbnail_url"] = c.get("_thumbnail_url")
    # nettoie le champ interne avant upsert
    creatives_clean = [{k: v for k, v in c.items() if not k.startswith("_")} for c in creatives]

    # 5. Insights
    print(f"→ Insights ({(until - since).days + 1} jours)…")
    insights = pull_insights(meta, args.account_id, since, until,
                              event_optin, event_call_booked,
                              event_complete_reg, event_lead)
    print(f"  {len(insights)} rows fact_ad_daily")

    # 6. Upsert
    if args.dry_run:
        print("\n📊 résumé dry-run :")
        print(f"   dim_campaign  : {len(campaigns)}")
        print(f"   dim_adset     : {len(adsets)}")
        print(f"   dim_ad        : {len(ads)}")
        print(f"   dim_creative  : {len(creatives_clean)}")
        print(f"   fact_ad_daily : {len(insights)}")
        if insights:
            print(f"   sample insight: {insights[0]}")
        elapsed = time.time() - t0
        print(f"⏱  {elapsed:.1f}s")
        return

    n1 = sb_upsert("dim_campaign", campaigns, on_conflict="campaign_id")
    n2 = sb_upsert("dim_adset", adsets, on_conflict="adset_id")
    n3 = sb_upsert("dim_creative", creatives_clean, on_conflict="creative_id")
    n4 = sb_upsert("dim_ad", ads, on_conflict="ad_id")
    n5 = sb_upsert("fact_ad_daily", insights, on_conflict="ad_id,date")

    elapsed = time.time() - t0
    print("\n✅ écrits :")
    print(f"   dim_campaign  : {n1}")
    print(f"   dim_adset     : {n2}")
    print(f"   dim_creative  : {n3}")
    print(f"   dim_ad        : {n4}")
    print(f"   fact_ad_daily : {n5}")
    print(f"⏱  {elapsed:.1f}s")


if __name__ == "__main__":
    main()
