"""Pull GoHighLevel → Supabase (gigi-data-os).

Pulls contacts, opportunities, calendar events (3 calendars), and survey
submissions, computes universal lead_id, and upserts into:
  dim_lead, fact_contact, fact_call, fact_sale, fact_survey

Usage:
  python pipelines/pull_ghl.py --days 90
  python pipelines/pull_ghl.py --since 2026-02-01
  python pipelines/pull_ghl.py --days 90 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from dateutil.parser import parse as parse_date

# Path bootstrap so the script runs from anywhere
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from pipelines.lib.ghl_client import GHLClient  # noqa: E402
from pipelines.lib.leadid import compute_lead_id, normalize_email, normalize_phone  # noqa: E402


# ---------- env loader (.env.local) ----------

def load_env_local(path: Path = ROOT / ".env.local") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------- Supabase REST client ----------

class Supabase:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or os.environ["SUPABASE_PROJECT_URL"]).rstrip("/")
        self.key = key or os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> int:
        if not rows:
            return 0
        import requests
        # Chunk to keep payloads reasonable
        total = 0
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            r = requests.post(
                f"{self.url}/rest/v1/{table}?on_conflict={on_conflict}",
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                data=json.dumps(chunk, default=str),
                timeout=60,
            )
            if r.status_code not in (200, 201, 204):
                raise RuntimeError(f"Supabase upsert {table} → {r.status_code}: {r.text[:500]}")
            total += len(chunk)
        return total


# ---------- helpers ----------

CAL_VSL = os.environ.get("GHL_CAL_VSL", "8ECqPVcPGz81JGlzCmoG")
CAL_FOLLOW = os.environ.get("GHL_CAL_FOLLOW", "AQ8RmdYw7iyru79Axymf")
CAL_BIENVENUE = os.environ.get("GHL_CAL_BIENVENUE", "BCghpu5fgGfkROyaQge5")
CALENDARS = {"VSL": CAL_VSL, "Follow": CAL_FOLLOW, "Bienvenue": CAL_BIENVENUE}

SURVEY_VSL = os.environ.get("GHL_SURVEY_VSL", "QMdJpJZx7K7Tl1oWieVw")
SURVEY_FIELDS = {
    "statut_onglerie": "uWAx6YVe9C7PLmbua9UK",
    "quand_demarrer":  "xDZKCaL8xU8flukqPE2Y",
    "temps_dispo":     "CmbhN557vuouOm8YhgK1",
    "budget":          "tPfOEWPCDMZYCY9clgl9",
    "motivation":      "KYfJdtLGHCrqvRlNrRJt",
}


def to_iso(ts: Any) -> str | None:
    if ts is None or ts == "":
        return None
    try:
        if isinstance(ts, (int, float)):
            # Heuristic: ms vs s
            if ts > 1e12:
                return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        s = str(ts).strip()
        if not s:
            return None
        if s.isdigit():
            return to_iso(int(s))
        return parse_date(s).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def survey_answer(others: dict, field_id: str) -> str | None:
    val = others.get(field_id)
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v) or None
    if val in (None, ""):
        return None
    return str(val)


def parse_motivation(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    try:
        n = int(digits[:2])
        return max(0, min(10, n))
    except Exception:
        return None


def compute_qualif(statut: str | None, quand: str | None, budget: str | None,
                   motivation: str | None, temps: str | None) -> int:
    """Heuristic 0-10 score per spec."""
    s = (statut or "").lower()
    q = (quand or "").lower()
    b = (budget or "").lower()
    t = (temps or "").lower()
    score = 0

    if "tout de suite" in q or "immédiat" in q or "immediat" in q:
        score += 3
    elif "30" in q or "moins de 1 mois" in q or "<1 mois" in q or "1 mois" in q:
        score += 2
    elif "3 mois" in q or "3-6" in q:
        score += 1

    if "investir" in b or "plusieurs fois" in b or "oui" in b:
        score += 3
    if "non" in b and "pas" in b:
        score -= 3

    motiv_n = parse_motivation(motivation)
    if motiv_n is not None:
        if motiv_n >= 10:
            score += 2
        elif motiv_n >= 7:
            score += 1

    # Temps dispo: heuristic — look for hours per week
    digits = "".join(ch for ch in t if ch.isdigit())
    try:
        hours = int(digits[:2]) if digits else 0
    except Exception:
        hours = 0
    if hours > 5 or "plus" in t or "5h" in t or "10h" in t:
        score += 1

    return max(0, min(10, score))


def funnel_from_calendar(cal_label: str) -> str:
    return {"VSL": "VSL", "Follow": "Follow", "Bienvenue": "Bienvenue"}.get(cal_label, "Other")


def normalize_call_status(raw_status: str | None) -> str:
    s = (raw_status or "").lower()
    if not s:
        return "other"
    if s in ("showed", "completed"):
        return "showed"
    if s in ("noshow", "no-show", "no_show"):
        return "no_show"
    if s in ("cancelled", "canceled"):
        return "cancelled"
    if s in ("confirmed", "booked", "new"):
        return "confirmed"
    return s


def is_won_stage(stage_name: str | None, status: str | None) -> bool:
    s = (status or "").lower()
    n = (stage_name or "").lower()
    return s == "won" or "gagné" in n or "gagne" in n or n == "won"


# ---------- transformers ----------

def contact_to_rows(c: dict, leads_by_id: dict[str, dict]) -> tuple[dict, list[dict]]:
    email = normalize_email(c.get("email"))
    phone = c.get("phone")
    lead_id = compute_lead_id(email, phone)

    attrs_list = c.get("attributions") or []
    attrs = attrs_list[0] if attrs_list else (c.get("attributionSource") or {})
    if not isinstance(attrs, dict):
        attrs = {}

    custom_fields = {cf.get("id") or cf.get("key"): cf.get("value")
                     for cf in (c.get("customFields") or []) if isinstance(cf, dict)}

    contact_row = {
        "ghl_contact_id": c.get("id"),
        "lead_id": lead_id,
        "email": email or None,
        "phone": normalize_phone(phone) or None,
        "first_name": c.get("firstName"),
        "last_name": c.get("lastName"),
        "source": c.get("source"),
        "date_added": to_iso(c.get("dateAdded")),
        "utm_source": attrs.get("utmSource") or attrs.get("utm_source"),
        "utm_medium": attrs.get("utmMedium") or attrs.get("utm_medium"),
        "utm_campaign": attrs.get("utmCampaign") or attrs.get("utm_campaign"),
        "utm_content": attrs.get("utmContent") or attrs.get("utm_content"),
        "fbclid": attrs.get("fbclid") or attrs.get("fbc"),
        "tags": c.get("tags") or [],
        "raw": {"contact": c, "custom": custom_fields},
    }

    if lead_id:
        existing = leads_by_id.get(lead_id)
        date_added_iso = contact_row["date_added"]
        new_lead = {
            "lead_id": lead_id,
            "email": email or None,
            "phone": normalize_phone(phone) or None,
            "first_name": c.get("firstName"),
            "last_name": c.get("lastName"),
            "source": c.get("source"),
            "first_seen_at": date_added_iso,
            "last_seen_at": date_added_iso,
        }
        if existing:
            if date_added_iso and (not existing["first_seen_at"] or date_added_iso < existing["first_seen_at"]):
                existing["first_seen_at"] = date_added_iso
            if date_added_iso and (not existing["last_seen_at"] or date_added_iso > existing["last_seen_at"]):
                existing["last_seen_at"] = date_added_iso
            for k in ("email", "phone", "first_name", "last_name", "source"):
                if not existing.get(k) and new_lead.get(k):
                    existing[k] = new_lead[k]
        else:
            leads_by_id[lead_id] = new_lead

    return contact_row, []


def classify_funnel(source: str | None) -> str | None:
    """Map GHL opportunity.source → 'VSL' | 'Setting' | None.

    VSL funnel (lead → Landing → opt-in → VSL → survey → call):
      - 'Form Léa Optin', 'Form Léa', 'Form Lea' (form 1 sur landing)
      - 'Survey VSL Lea' (survey post-VSL)
      - 'VSL' (manuel)
      - 'Appel de découverte - Gigi Academy (VSL)' (booking calendar VSL)

    Setting funnel (DM IG → setteuse → call):
      - 'Setting' (manuel par setteuse)
      - 'Appel de découverte - Gigi Academy' (booking calendar Standard)
    """
    if not source:
        return None
    s = source.strip()
    s_low = s.lower()
    if (
        "vsl" in s_low  # catches "VSL", "Survey VSL", "(VSL)"
        or s in ("Form Léa Optin", "Form Léa", "Form Lea")
        or "form léa" in s_low
        or "form lea" in s_low
    ):
        return "VSL"
    if "setting" in s_low or s == "Appel de découverte - Gigi Academy":
        return "Setting"
    return None


def opportunity_to_row(o: dict, contact_index: dict[str, dict],
                        stage_name_by_id: dict[str, str] | None = None,
                        pipeline_name_by_id: dict[str, str] | None = None) -> dict:
    contact = o.get("contact") or {}
    contact_id = contact.get("id") or o.get("contactId")
    cached = contact_index.get(contact_id) if contact_id else None
    email = normalize_email(contact.get("email") or (cached or {}).get("email"))
    phone = contact.get("phone") or (cached or {}).get("phone")
    lead_id = compute_lead_id(email, phone)

    stage_id = o.get("pipelineStageId") or o.get("stageId")
    stage_name = (
        o.get("pipelineStageName")
        or o.get("stageName")
        or (stage_name_by_id or {}).get(stage_id)
    )
    status = o.get("status")
    won = is_won_stage(stage_name, status)
    contracted_at = to_iso(o.get("updatedAt") if won else None) if won else None

    # source funnel: derived from GHL native opportunity.source field.
    # Mapping validated with Antoine 2026-05-08 — see feedback_lea_source_funnel.md.
    source_funnel = classify_funnel(o.get("source"))

    return {
        "opportunity_id": o.get("id"),
        "lead_id": lead_id,
        "contact_id": contact_id,
        "contact_email": email or None,
        "pipeline_id": o.get("pipelineId"),
        "stage_id": o.get("pipelineStageId") or o.get("stageId"),
        "stage_name": stage_name,
        "status": status,
        "is_won": won,
        "monetary_value": o.get("monetaryValue"),
        "source_funnel": source_funnel,
        "closer_id": o.get("assignedTo"),
        "contracted_at": contracted_at,
        "created_at": to_iso(o.get("createdAt")),
        "updated_at": to_iso(o.get("updatedAt")),
        "raw": o,
    }


def event_to_row(ev: dict, calendar_label: str, calendar_id: str, contact_index: dict[str, dict]) -> dict:
    contact_id = ev.get("contactId")
    cached = contact_index.get(contact_id) if contact_id else None
    email = normalize_email((cached or {}).get("email"))
    phone = (cached or {}).get("phone")
    lead_id = compute_lead_id(email, phone) if (email or phone) else None

    raw_status = ev.get("appointmentStatus") or ev.get("status")
    return {
        "ghl_event_id": ev.get("id"),
        "lead_id": lead_id,
        "contact_id": contact_id,
        "contact_email": email or None,
        "calendar_id": calendar_id,
        "calendar_label": calendar_label,
        "title": ev.get("title"),
        "scheduled_at": to_iso(ev.get("startTime") or ev.get("dateAdded")),
        "status": normalize_call_status(raw_status),
        "raw_status": raw_status,
        "assigned_user_id": ev.get("assignedUserId"),
        "created_at": to_iso(ev.get("dateAdded")),
        "raw": ev,
    }


def submission_to_row(s: dict, contact_index: dict[str, dict]) -> dict:
    others = s.get("others") or {}
    contact_id = s.get("contactId") or others.get("contactId")
    cached = contact_index.get(contact_id) if contact_id else None
    email = normalize_email(s.get("email") or others.get("email") or (cached or {}).get("email"))
    phone = (cached or {}).get("phone")
    lead_id = compute_lead_id(email, phone)

    statut = survey_answer(others, SURVEY_FIELDS["statut_onglerie"])
    quand = survey_answer(others, SURVEY_FIELDS["quand_demarrer"])
    temps = survey_answer(others, SURVEY_FIELDS["temps_dispo"])
    budget = survey_answer(others, SURVEY_FIELDS["budget"])
    motiv = survey_answer(others, SURVEY_FIELDS["motivation"])
    score = compute_qualif(statut, quand, budget, motiv, temps)

    return {
        "submission_id": s.get("id"),
        "lead_id": lead_id,
        "contact_id": contact_id,
        "email": email or None,
        "survey_id": s.get("surveyId") or SURVEY_VSL,
        "submitted_at": to_iso(s.get("createdAt") or others.get("createdAt")),
        "statut_onglerie": statut,
        "quand_demarrer": quand,
        "budget": budget,
        "motivation": motiv,
        "temps_dispo": temps,
        "qualif_score": score,
        "disqualified": bool(others.get("disqualified")),
        "raw": s,
    }


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--since", type=str, default=None, help="YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env_local()

    if args.since:
        start_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    else:
        start_dt = datetime.now(timezone.utc) - timedelta(days=args.days)
    end_dt = datetime.now(timezone.utc) + timedelta(days=14)  # include upcoming bookings
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    print(f"➜ Pulling GHL since {start_dt.date()} (dry_run={args.dry_run})")

    ghl = GHLClient()
    sb = Supabase()

    # 1) Contacts
    contact_rows: list[dict] = []
    leads_by_id: dict[str, dict] = {}
    contact_index: dict[str, dict] = {}

    print("→ contacts/search")
    filters = [{"field": "dateAdded", "operator": "range",
                "value": {"gte": start_ms, "lte": end_ms}}]
    n_contacts = 0
    try:
        for c in ghl.search_contacts(filters=filters):
            contact_index[c.get("id")] = c
            row, _ = contact_to_rows(c, leads_by_id)
            contact_rows.append(row)
            n_contacts += 1
            if n_contacts % 200 == 0:
                print(f"  …{n_contacts} contacts")
    except RuntimeError as e:
        print(f"!! contacts search failed with date filter ({e}); falling back to full pull")
        contact_rows.clear()
        leads_by_id.clear()
        contact_index.clear()
        n_contacts = 0
        for c in ghl.search_contacts():
            contact_index[c.get("id")] = c
            row, _ = contact_to_rows(c, leads_by_id)
            contact_rows.append(row)
            n_contacts += 1
    print(f"  contacts pulled: {n_contacts}")

    # 2a) Pipelines — resolve stage_id → stage_name + pipeline_id → name
    print("→ opportunities/pipelines (resolve stage names)")
    stage_name_by_id: dict[str, str] = {}
    pipeline_name_by_id: dict[str, str] = {}
    try:
        for p in ghl.list_pipelines():
            pid = p.get("id")
            if pid:
                pipeline_name_by_id[pid] = p.get("name") or ""
            for s in p.get("stages") or []:
                sid = s.get("id")
                if sid:
                    stage_name_by_id[sid] = s.get("name") or ""
        print(f"  resolved {len(stage_name_by_id)} stages across {len(pipeline_name_by_id)} pipelines")
    except Exception as e:
        print(f"!! pipelines fetch failed ({e}) — stage_name will stay null")

    # 2b) Opportunities (no native date filter — pull all, transform)
    print("→ opportunities/search")
    opp_rows: list[dict] = []
    for o in ghl.search_opportunities():
        opp_rows.append(opportunity_to_row(o, contact_index, stage_name_by_id, pipeline_name_by_id))
    print(f"  opportunities pulled: {len(opp_rows)}")

    # 3) Calendar events (3 calendars)
    print("→ calendars/events")
    call_rows: list[dict] = []
    for label, cal_id in CALENDARS.items():
        try:
            events = ghl.calendar_events(cal_id, start_ms, end_ms)
        except RuntimeError as e:
            print(f"  ⚠ calendar {label} failed: {e}")
            continue
        for ev in events:
            if ev.get("deleted"):
                continue
            call_rows.append(event_to_row(ev, label, cal_id, contact_index))
        print(f"  {label}: {len(events)} events")

    # 4) Surveys
    print("→ surveys/submissions")
    survey_rows: list[dict] = []
    try:
        for s in ghl.survey_submissions(SURVEY_VSL):
            row = submission_to_row(s, contact_index)
            ts = row.get("submitted_at")
            if ts and ts < start_dt.isoformat():
                continue
            survey_rows.append(row)
    except RuntimeError as e:
        print(f"  ⚠ surveys failed: {e}")
    print(f"  survey submissions: {len(survey_rows)}")

    # ---- Push ----
    leads = list(leads_by_id.values())
    print(f"\nVolumes → dim_lead={len(leads)} fact_contact={len(contact_rows)} "
          f"fact_sale={len(opp_rows)} fact_call={len(call_rows)} fact_survey={len(survey_rows)}")

    if args.dry_run:
        print("(dry-run — skipping Supabase upserts)")
        return 0

    n = sb.upsert("dim_lead", leads, on_conflict="lead_id")
    print(f"  ✓ dim_lead +{n}")
    n = sb.upsert("fact_contact", contact_rows, on_conflict="ghl_contact_id")
    print(f"  ✓ fact_contact +{n}")
    n = sb.upsert("fact_sale", opp_rows, on_conflict="opportunity_id")
    print(f"  ✓ fact_sale +{n}")
    n = sb.upsert("fact_call", call_rows, on_conflict="ghl_event_id")
    print(f"  ✓ fact_call +{n}")
    n = sb.upsert("fact_survey", survey_rows, on_conflict="submission_id")
    print(f"  ✓ fact_survey +{n}")

    print("\n✅ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
