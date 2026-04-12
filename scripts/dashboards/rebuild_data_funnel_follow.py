"""Rebuild Data_Funnel_Follow from Meta_Ads_Raw + manual DashBoard_Funnel_Follow historical data."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
EPOCH = datetime(1899, 12, 30)

TAB = "Data_Funnel_Follow"


def to_iso(v):
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        return (EPOCH + timedelta(days=float(v))).date().isoformat()
    return str(v)


def main():
    s = get_sheets_service()

    # 1. Read Meta_Ads_Raw (Follow campaign)
    r = s.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="Meta_Ads_Raw!A2:O",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    meta_by_date = {}
    for row in r.get("values", []):
        while len(row) < 15:
            row.append("")
        iso = to_iso(row[0])
        if iso:
            meta_by_date[iso] = row

    # 2. Manual historical data — March block (V7:AD37)
    # Cols: V=Date, W=Spend, X=NewFol, Y=Conv, Z=Liens, AA=AppelsResrv, AB=AppelsRecus, AC=Ventes, AD=CA
    manual_by_date = {}

    r = s.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="DashBoard_Funnel_Follow!V7:AD37",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    for row in r.get("values", []):
        if not row or not row[0]:
            continue
        iso = to_iso(row[0])
        vals = row + [""] * (9 - len(row))
        manual_by_date[iso] = {
            "conversations": vals[3] or 0,
            "liens_envoyes": vals[4] or 0,
            "appels_reserves": vals[5] or 0,
            "appels_recus": vals[6] or 0,
            "ventes": vals[7] or 0,
            "ca": vals[8] or 0,
        }

    # 2b. Manual historical data — April block (AG7:AO37)
    # Cols: AG=Date, AH=Spend, AI=NewFol, AJ=Conv, AK=Liens, AL=Bookés, AM=Reçus, AN=Ventes, AO=Cash
    r = s.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="DashBoard_Funnel_Follow!AG7:AO37",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    for row in r.get("values", []):
        if not row or not row[0]:
            continue
        iso = to_iso(row[0])
        vals = row + [""] * (9 - len(row))
        # Merge: keep non-empty values (April block has same columns as March)
        existing = manual_by_date.get(iso, {})
        manual_by_date[iso] = {
            "conversations": vals[3] if vals[3] not in ("", None) else existing.get("conversations", 0),
            "liens_envoyes": vals[4] if vals[4] not in ("", None) else existing.get("liens_envoyes", 0),
            "appels_reserves": vals[5] if vals[5] not in ("", None) else existing.get("appels_reserves", 0),
            "appels_recus": vals[6] if vals[6] not in ("", None) else existing.get("appels_recus", 0),
            "ventes": vals[7] if vals[7] not in ("", None) else existing.get("ventes", 0),
            "ca": vals[8] if vals[8] not in ("", None) else existing.get("ca", 0),
        }

    # 3. Build rebuilt rows for every date that has either meta or manual data
    all_dates = sorted(set(list(meta_by_date.keys()) + list(manual_by_date.keys())))

    rebuilt = []
    for iso in all_dates:
        m = meta_by_date.get(iso)
        mn = manual_by_date.get(iso, {})

        # Skip rows that have neither meta data nor any manual data
        has_meta = m is not None and any(str(x).strip() and str(x).strip() != "0" for x in m[1:])
        has_manual = any((mn.get(k) or 0) for k in ("conversations", "liens_envoyes", "appels_reserves", "appels_recus", "ventes", "ca"))
        if not has_meta and not has_manual:
            continue

        spend = float(m[1]) if m and m[1] not in ("", None) else 0
        impressions = int(m[2]) if m and m[2] not in ("", None) else 0
        clicks = int(m[3]) if m and m[3] not in ("", None) else 0
        cpm = float(m[4]) if m and m[4] not in ("", None) else 0
        cpc = float(m[5]) if m and m[5] not in ("", None) else 0
        ctr = float(m[6]) if m and m[6] not in ("", None) else 0
        reach = int(m[7]) if m and m[7] not in ("", None) else 0
        new_fol = int(m[8]) if m and m[8] not in ("", None) else 0
        pv = int(m[9]) if m and m[9] not in ("", None) else 0
        cost_pv = float(m[11]) if m and m[11] not in ("", None) else 0
        cost_fol = float(m[12]) if m and m[12] not in ("", None) else (round(spend / new_fol, 2) if new_fol > 0 else "")

        dms = mn.get("conversations", 0) or 0
        liens = mn.get("liens_envoyes", 0) or 0
        calls_booked = mn.get("appels_reserves", 0) or 0
        calls_recus = mn.get("appels_recus", 0) or 0
        ventes = mn.get("ventes", 0) or 0
        ca = mn.get("ca", 0) or 0

        taux_lien = round(liens / dms * 100, 2) if dms > 0 else ""
        taux_booking = round(calls_booked / liens * 100, 2) if liens > 0 else ""
        taux_show = round(calls_recus / calls_booked * 100, 2) if calls_booked > 0 else ""
        taux_closing = round(ventes / calls_recus * 100, 2) if calls_recus > 0 else ""
        cout_call = round(spend / calls_recus, 2) if calls_recus > 0 else ""
        cout_vente = round(spend / ventes, 2) if ventes > 0 else ""
        roas = round(ca / spend, 2) if spend > 0 else ""

        rebuilt.append([
            iso,            # 1 Date
            spend,          # 2 Ad Spend
            impressions,    # 3 Impressions
            clicks,         # 4 Clicks
            ctr,            # 5 CTR
            cpc,            # 6 CPC
            reach,          # 7 Reach
            pv,             # 8 Profile Visits
            cost_pv,        # 9 Coût/PV
            new_fol,        # 10 New Followers
            cost_fol,       # 11 Coût/Follower
            dms,            # 12 DMs envoyés
            liens,          # 13 Liens envoyés
            taux_lien,      # 14 Taux Lien (%)
            calls_booked,   # 15 Calls Bookés
            taux_booking,   # 16 Taux Booking (%)
            calls_recus,    # 17 Calls Reçus
            taux_show,      # 18 Taux Show (%)
            ventes,         # 19 Ventes
            taux_closing,   # 20 Taux Closing (%)
            ca,             # 21 Cash Contracté
            ca,             # 22 Cash Collecté (same for historical manual entries)
            cout_call,      # 23 Coût/Call
            cout_vente,     # 24 Coût/Vente
            roas,           # 25 ROAS
        ])

    # 4. Clear + write
    s.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range=f"{TAB}!A2:Z").execute()
    clean_str = [[str(c) if c != "" and c is not None else "" for c in row] for row in rebuilt]
    if clean_str:
        s.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=f"{TAB}!A2",
            valueInputOption="USER_ENTERED", body={"values": clean_str},
        ).execute()

    # 5. Ensure col A is ISO date format
    meta_sheets = s.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sid = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta_sheets["sheets"]}[TAB]
    s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [{
        "repeatCell": {
            "range": {"sheetId": sid, "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }]}).execute()

    total_ventes = sum(r[18] or 0 for r in rebuilt if isinstance(r[18], (int, float)))
    total_ca = sum(r[20] or 0 for r in rebuilt if isinstance(r[20], (int, float)))
    total_spend = sum(r[1] or 0 for r in rebuilt if isinstance(r[1], (int, float)))
    print(f"✅ {TAB}: {len(rebuilt)} rows")
    print(f"   Total Spend: {total_spend:.2f}€ | Ventes: {total_ventes} | CA: {total_ca:.2f}€")


if __name__ == "__main__":
    main()
