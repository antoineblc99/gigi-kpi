"""Rebuild Data_Funnel_VSL from Meta_Ads_Raw_VSL + GHL_Optins_Raw + GHL_Surveys_Raw + GHL_Calls_Raw."""
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
EPOCH = datetime(1899, 12, 30)

OPTIN_FORM_SOURCE = "Form Léa Optin"


def to_iso(v):
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        return (EPOCH + timedelta(days=float(v))).date().isoformat()
    # handle ISO datetime strings like 2026-04-11T12:34:56
    s = str(v)
    return s[:10] if len(s) >= 10 else s


def main():
    s = get_sheets_service()

    # 1. Meta_Ads_Raw_VSL → by date
    # cols: A=Date B=Spend C=Impr D=Reach E=Freq F=CTR G=LinkClicks H=CPC I=LPV J=LPVRate K=Optins/Leads L=CPL M=LastUpdated
    r = s.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="Meta_Ads_Raw_VSL!A2:M",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    meta = {}
    for row in r.get("values", []):
        while len(row) < 13:
            row.append("")
        iso = to_iso(row[0])
        if iso:
            meta[iso] = row

    # 2. GHL_Optins_Raw → count per date (source = Form Léa Optin)
    # cols: A=Date B=Source C=Prenom D=Email E=Phone F-J=UTMs K=SubmittedAt
    r = s.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="GHL_Optins_Raw!A2:K",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    optins = Counter()
    for row in r.get("values", []):
        while len(row) < 11:
            row.append("")
        iso = to_iso(row[0])
        source = str(row[1])
        if iso and source == OPTIN_FORM_SOURCE:
            optins[iso] += 1

    # 3. GHL_Surveys_Raw → count surveys + qualifiés per date
    # cols: A=Date B=Email C-G=answers H=Qualifié I=SubmittedAt
    r = s.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="GHL_Surveys_Raw!A2:I",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    surveys_total = Counter()
    surveys_qualif = Counter()
    for row in r.get("values", []):
        while len(row) < 9:
            row.append("")
        iso = to_iso(row[0])
        qualif = str(row[7]).strip().lower()
        if iso:
            surveys_total[iso] += 1
            if qualif == "oui":
                surveys_qualif[iso] += 1

    # 4. GHL_Calls_Raw → VSL calendar only, by day + status
    # cols: A=Date B=Calendar C=Contact D=Email E=Status F=AssignedUser G=Source H=CreatedAt
    r = s.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="GHL_Calls_Raw!A2:H",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
    ).execute()
    calls_booked = Counter()
    calls_showed = Counter()
    for row in r.get("values", []):
        while len(row) < 8:
            row.append("")
        iso = to_iso(row[0])
        cal = str(row[1])
        status = str(row[4]).lower()
        if iso and cal == "VSL":
            if status not in ("cancelled", "deleted"):
                calls_booked[iso] += 1
            if status == "showed":
                calls_showed[iso] += 1

    # 5. Build daily rows
    all_dates = sorted(set(list(meta.keys()) + list(optins.keys()) + list(surveys_total.keys()) + list(calls_booked.keys())))

    rebuilt = []
    for iso in all_dates:
        m = meta.get(iso, [""] * 13)
        spend = float(m[1]) if m[1] not in ("", None) else 0
        impressions = int(m[2]) if m[2] not in ("", None) else 0
        reach = int(m[3]) if m[3] not in ("", None) else 0
        ctr = float(m[5]) if m[5] not in ("", None) else 0
        link_clicks = int(m[6]) if m[6] not in ("", None) else 0
        cpc = float(m[7]) if m[7] not in ("", None) else 0
        lpv = int(m[8]) if m[8] not in ("", None) else 0
        meta_leads = int(m[10]) if m[10] not in ("", None) else 0

        opt_ghl = optins.get(iso, 0)
        opt_count = max(opt_ghl, meta_leads)  # use max as best estimate

        svy = surveys_total.get(iso, 0)
        qualif = surveys_qualif.get(iso, 0)
        booked = calls_booked.get(iso, 0)
        showed = calls_showed.get(iso, 0) or booked  # fallback: assume all = showed until dispo status

        ventes = 0
        cash_contract = 0
        cash_collect = 0

        taux_optin = round(opt_count / lpv * 100, 2) if lpv > 0 else ""
        taux_survey = round(svy / opt_count * 100, 2) if opt_count > 0 else ""
        taux_qualif = round(qualif / svy * 100, 2) if svy > 0 else ""
        taux_booking = round(booked / qualif * 100, 2) if qualif > 0 else ""
        taux_show = round(showed / booked * 100, 2) if booked > 0 else ""
        taux_closing = round(ventes / showed * 100, 2) if showed > 0 else ""
        cost_optin = round(spend / opt_count, 2) if opt_count > 0 else ""
        cost_call = round(spend / showed, 2) if showed > 0 else ""
        cost_vente = round(spend / ventes, 2) if ventes > 0 else ""
        roas = round(cash_collect / spend, 2) if spend > 0 else ""

        rebuilt.append([
            iso,            # A
            spend,          # B Ad Spend
            impressions,    # C Impressions
            link_clicks,    # D Link Clicks
            ctr,            # E CTR
            cpc,            # F CPC
            lpv,            # G LPV
            opt_count,      # H Opt-ins
            taux_optin,     # I Taux Opt-in
            svy,            # J Surveys
            taux_survey,    # K Taux Survey
            qualif,         # L Qualifiés
            taux_qualif,    # M Taux Qualif
            booked,         # N Calls Bookés
            taux_booking,   # O Taux Booking
            showed,         # P Calls Reçus
            taux_show,      # Q Taux Show
            ventes,         # R Ventes
            taux_closing,   # S Taux Closing
            cash_contract,  # T Cash Contracté
            cash_collect,   # U Cash Collecté
            cost_optin,     # V Coût/Opt-in
            cost_call,      # W Coût/Call
            cost_vente,     # X Coût/Vente
            roas,           # Y ROAS
        ])

    s.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range="Data_Funnel_VSL!A2:Z").execute()
    clean_str = [[str(c) if c != "" and c is not None else "" for c in row] for row in rebuilt]
    if clean_str:
        s.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range="Data_Funnel_VSL!A2",
            valueInputOption="USER_ENTERED", body={"values": clean_str},
        ).execute()

    # Format col A as ISO date
    meta_sh = s.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sid = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta_sh["sheets"]}["Data_Funnel_VSL"]
    s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [{
        "repeatCell": {
            "range": {"sheetId": sid, "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }]}).execute()

    total_spend = sum(r[1] for r in rebuilt if isinstance(r[1], (int, float)))
    total_opts = sum(r[7] for r in rebuilt if isinstance(r[7], (int, float)))
    total_calls = sum(r[15] for r in rebuilt if isinstance(r[15], (int, float)))
    print(f"✅ Data_Funnel_VSL: {len(rebuilt)} rows")
    print(f"   Spend: {total_spend:.2f}€ | Opt-ins: {total_opts} | Calls shown: {total_calls}")


if __name__ == "__main__":
    main()
