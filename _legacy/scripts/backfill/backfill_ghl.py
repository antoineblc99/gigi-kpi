"""Backfill GHL → GHL_Calls_Raw, GHL_Optins_Raw."""
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

import requests

from auth import get_sheets_service

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
GHL_BASE = "https://services.leadconnectorhq.com"
LOCATION_ID = "TTzAZhJJwPHQobNiXjWJ"
CALENDARS = {
    "VSL": "8ECqPVcPGz81JGlzCmoG",
    "Follow": "AQ8RmdYw7iyru79Axymf",
    "Bienvenue": "BCghpu5fgGfkROyaQge5",
}
SURVEY_ID = "QMdJpJZx7K7Tl1oWieVw"  # post-VSL qualif
SURVEY_FIELDS = {
    "niveau": "uWAx6YVe9C7PLmbua9UK",
    "when": "xDZKCaL8xU8flukqPE2Y",
    "time": "CmbhN557vuouOm8YhgK1",
    "budget": "tPfOEWPCDMZYCY9clgl9",
    "motivation": "KYfJdtLGHCrqvRlNrRJt",
}
TIMEZONE = "Europe/Paris"


def ghl_api_key(sheets) -> str:
    """Prefer sheet value (GHL_Config!B2), fallback to env var."""
    try:
        r = sheets.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range="GHL_Config!B2"
        ).execute()
        val = r.get("values", [[]])[0][0] if r.get("values") else ""
        if val and val.startswith(("pit-", "eyJ")):
            return val
    except Exception:
        pass
    return os.environ["GHL_API_KEY"]


def _headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Version": "2021-04-15",
        "Accept": "application/json",
    }


def ghl_get(key: str, path: str, params: dict | None = None) -> dict:
    for attempt in range(3):
        r = requests.get(f"{GHL_BASE}{path}", headers=_headers(key), params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"GHL API {r.status_code} on {path}: {r.text[:400]}")
    raise RuntimeError(f"GHL retries exhausted on {path}")


def day_bounds_ms(day: date) -> tuple[int, int]:
    # Europe/Paris UTC+2 in summer, +1 in winter; the Apps Script used +02:00 fixed.
    # Use Python's UTC to be safe; a few hours skew is acceptable for daily granularity.
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1) - timedelta(milliseconds=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


# ---------- Calls (calendar events) ----------

def fetch_calendar_events(key: str, calendar_id: str, start_ms: int, end_ms: int) -> list[dict]:
    # GHL events endpoint uses version 2021-04-15 for locationId+calendarId+startTime+endTime
    data = ghl_get(key, "/calendars/events", {
        "locationId": LOCATION_ID,
        "calendarId": calendar_id,
        "startTime": str(start_ms),
        "endTime": str(end_ms),
    })
    return data.get("events", [])


def row_call(day_iso: str, calendar_label: str, ev: dict) -> list:
    created_by = ev.get("createdBy") or {}
    return [
        day_iso,
        calendar_label,
        ev.get("title", ""),
        "",  # email (requires contact lookup)
        ev.get("appointmentStatus", ""),
        ev.get("assignedUserId", ""),
        created_by.get("source", "") if isinstance(created_by, dict) else "",
        ev.get("dateAdded", ""),
    ]


# ---------- Opt-ins (contacts) ----------

def fetch_contacts_for_range(key: str, start_ms: int, end_ms: int) -> list[dict]:
    """Use contacts search endpoint with dateAdded range filter."""
    headers = {
        "Authorization": f"Bearer {key}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    all_contacts: list[dict] = []
    page = 1
    while True:
        body = {
            "locationId": LOCATION_ID,
            "filters": [{
                "field": "dateAdded",
                "operator": "range",
                "value": {"gte": start_ms, "lte": end_ms},
            }],
            "page": page,
            "pageLimit": 100,
        }
        r = requests.post(f"{GHL_BASE}/contacts/search", headers=headers, json=body, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"GHL contacts/search {r.status_code}: {r.text[:400]}")
        data = r.json()
        contacts = data.get("contacts", [])
        if not contacts:
            break
        all_contacts.extend(contacts)
        if len(contacts) < 100:
            break
        page += 1
        if page > 50:  # safety cap
            break
    return all_contacts


def row_optin(day_iso: str, c: dict) -> list:
    attrs = c.get("attributionSource") or c.get("attributions", [{}])[0] if c.get("attributions") else {}
    if not isinstance(attrs, dict):
        attrs = {}
    custom = {cf.get("id") or cf.get("key"): cf.get("value") for cf in (c.get("customFields") or [])}
    # We don't know exact UTM custom field IDs; try common keys
    return [
        day_iso,
        c.get("source", ""),
        c.get("firstName", ""),
        c.get("email", ""),
        c.get("phone", ""),
        attrs.get("utmSource", "") or attrs.get("utm_source", ""),
        attrs.get("utmMedium", "") or attrs.get("utm_medium", ""),
        attrs.get("utmCampaign", "") or attrs.get("utm_campaign", ""),
        attrs.get("utmContent", "") or attrs.get("utm_content", ""),
        attrs.get("fbclid", "") or attrs.get("fbc", ""),
        c.get("dateAdded", ""),
    ]


# ---------- Surveys ----------

def fetch_survey_submissions(key: str, start: date, end: date) -> list[dict]:
    """Fetch all submissions for the VSL qualif survey and filter client-side by date range."""
    headers = {
        "Authorization": f"Bearer {key}",
        "Version": "2021-07-28",
        "Accept": "application/json",
    }
    out: list[dict] = []
    page = 1
    start_ms, _ = day_bounds_ms(start)
    _, end_ms = day_bounds_ms(end)
    while True:
        r = requests.get(
            f"{GHL_BASE}/surveys/submissions",
            headers=headers,
            params={"locationId": LOCATION_ID, "surveyId": SURVEY_ID, "limit": 100, "page": page},
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"GHL surveys/submissions {r.status_code}: {r.text[:400]}")
        data = r.json()
        subs = data.get("submissions", [])
        if not subs:
            break
        out.extend(subs)
        meta = data.get("meta", {})
        if not meta.get("nextPage"):
            break
        page = meta["nextPage"]
        if page > 50:
            break
    # Client-side filter by date
    filtered = []
    for s in out:
        ts = s.get("createdAt") or s.get("others", {}).get("createdAt")
        if not ts:
            continue
        try:
            sub_ms = int(parse_date(ts).timestamp() * 1000)
        except Exception:
            continue
        if start_ms <= sub_ms <= end_ms:
            filtered.append(s)
    return filtered


def _survey_answer(others: dict, field_id: str) -> str:
    val = others.get(field_id)
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val) if val else ""


def row_survey(s: dict) -> list:
    others = s.get("others") or {}
    created = s.get("createdAt") or others.get("createdAt") or ""
    try:
        day_iso = parse_date(str(created)).date().isoformat()
    except Exception:
        day_iso = ""
    disqualified = bool(others.get("disqualified"))
    return [
        day_iso,
        s.get("email", "") or others.get("email", ""),
        _survey_answer(others, SURVEY_FIELDS["niveau"]),
        _survey_answer(others, SURVEY_FIELDS["when"]),
        _survey_answer(others, SURVEY_FIELDS["time"]),
        _survey_answer(others, SURVEY_FIELDS["budget"]),
        _survey_answer(others, SURVEY_FIELDS["motivation"]),
        "Non" if disqualified else "Oui",
        created,
    ]


# ---------- Sheet I/O ----------

def append_rows(sheets, tab: str, rows: list[list], value_input: str = "USER_ENTERED") -> int:
    if not rows:
        return 0
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!A1",
        valueInputOption=value_input,
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


def existing_days(sheets, tab: str) -> set[str]:
    resp = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{tab}!A2:A"
    ).execute()
    return {str(v[0]) for v in resp.get("values", []) if v}


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


from dateutil.parser import parse as parse_date  # noqa: E402 (used in survey fn)


# ---------- Main ----------

def run(start: date, end: date, force: bool = False) -> None:
    sheets = get_sheets_service()
    key = ghl_api_key(sheets)

    calls_done = set() if force else existing_days(sheets, "GHL_Calls_Raw")
    optins_done = set() if force else existing_days(sheets, "GHL_Optins_Raw")

    calls_rows: list[list] = []
    optins_rows: list[list] = []
    survey_rows: list[list] = []

    # Surveys: fetch once for the full range (small dataset, no need to iterate days)
    try:
        subs = fetch_survey_submissions(key, start, end)
        survey_rows = [row_survey(s) for s in subs]
    except RuntimeError as err:
        print(f"surveys error: {err}")

    for d in daterange(start, end):
        day_iso = d.isoformat()
        s_ms, e_ms = day_bounds_ms(d)
        print(f"→ {day_iso}")

        if day_iso not in calls_done:
            for label, cal_id in CALENDARS.items():
                try:
                    events = fetch_calendar_events(key, cal_id, s_ms, e_ms)
                except RuntimeError as err:
                    print(f"   calls[{label}] error: {err}")
                    continue
                for ev in events:
                    if not ev.get("deleted"):
                        calls_rows.append(row_call(day_iso, label, ev))

        if day_iso not in optins_done:
            try:
                contacts = fetch_contacts_for_range(key, s_ms, e_ms)
            except RuntimeError as err:
                print(f"   opt-ins error: {err}")
                continue
            for c in contacts:
                optins_rows.append(row_optin(day_iso, c))

    n1 = append_rows(sheets, "GHL_Calls_Raw", calls_rows)
    n2 = append_rows(sheets, "GHL_Optins_Raw", optins_rows)
    n3 = append_rows(sheets, "GHL_Surveys_Raw", survey_rows, value_input="RAW")
    print(f"✅ Calls +{n1} | Opt-ins +{n2} | Surveys +{n3}")


if __name__ == "__main__":
    import argparse
    from dateutil.parser import parse as parse_date

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2026-03-05")
    ap.add_argument("--to", dest="end", default=date.today().isoformat())
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    run(parse_date(args.start).date(), parse_date(args.end).date(), force=args.force)
