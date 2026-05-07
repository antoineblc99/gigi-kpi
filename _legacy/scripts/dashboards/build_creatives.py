"""Dashboard Creatives — ranking créas par ROAS / hook rate / Cost/result."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
TAB = "DashBoard_Creatives_v2"
# Creative_Raw:
# A=Date B=AdName C=AdID D=AdSet E=Spend F=Imp G=Clicks H=CPM I=CPC J=CTR
# K=Reach L=PV M=CostPV N=VideoViews O=Engagements P=Saves Q=Likes R=ThruPlay S=Freq T=LastUpdated


def ensure_sheet(s, title):
    meta = s.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sid_map = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}
    if title in sid_map:
        return sid_map[title]
    resp = s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={
        "requests": [{"addSheet": {"properties": {"title": title}}}]
    }).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def build(s):
    sid = ensure_sheet(s, TAB)
    s.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1:Z200").execute()

    CR = "'Creative_Raw'"

    rows = [
        ["DASHBOARD CREATIVES", "", "", "", "", "", "", "", ""],
        ["Période (jours)", 30, "", "Début période", "=TODAY()-B2", "", "", "", ""],
        [""] * 9,
        # Summary
        ["Total Spend (€)", "Total Créas Actives", "CTR Moyen", "", "", "", "", "", ""],
        [
            f"=IFERROR(SUMIFS({CR}!E:E,{CR}!A:A,\">=\"&$E$2),0)",
            f"=IFERROR(COUNTUNIQUE(IFS({CR}!A:A>=$E$2,{CR}!B:B)),0)",
            f"=IFERROR(AVERAGEIFS({CR}!J:J,{CR}!A:A,\">=\"&$E$2),0)",
            "", "", "", "", "", "",
        ],
        [""] * 9,
        [""] * 9,
        ["TOP CRÉATIVES PAR SPEND (période sélectionnée)", "", "", "", "", "", "", "", ""],
        [""] * 9,
    ]

    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()

    # Main QUERY: group by ad_name, show spend + perf metrics, sort by spend desc
    query = (
        f"=QUERY({CR}!A:T, "
        "\"SELECT B, D, SUM(E), SUM(F), SUM(G), AVG(J), AVG(I), SUM(L), AVG(M), SUM(N), SUM(R), AVG(S) \"&"
        "\"WHERE A >= date '\"&TEXT($E$2,\"yyyy-mm-dd\")&\"' AND B IS NOT NULL AND E > 0 \"&"
        "\"GROUP BY B, D ORDER BY SUM(E) DESC LIMIT 20 \"&"
        "\"LABEL B 'Ad Name', D 'Ad Set', SUM(E) 'Spend', SUM(F) 'Imp', \"&"
        "\"SUM(G) 'Clicks', AVG(J) 'CTR', AVG(I) 'CPC', SUM(L) 'PV', AVG(M) 'Cost/PV', \"&"
        "\"SUM(N) 'VideoViews', SUM(R) 'ThruPlay', AVG(S) 'Freq'\", 1)"
    )
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A10",
        valueInputOption="USER_ENTERED", body={"values": [[query]]},
    ).execute()

    # Derived Hold Rate column (M = ThruPlay / VideoViews)
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!M10",
        valueInputOption="USER_ENTERED", body={"values": [["Hold Rate (%)"]]},
    ).execute()
    hold_rows = [[f"=IFERROR(K{i}/J{i}*100,0)"] for i in range(11, 31)]
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!M11:M30",
        valueInputOption="USER_ENTERED", body={"values": hold_rows},
    ).execute()

    reqs = [
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                                   "startColumnIndex": 0, "endColumnIndex": 13}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 13},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.15, "green": 0.45, "blue": 0.70},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 46}, "fields": "pixelSize",
        }},
        {"setDataValidation": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": x} for x in ["7", "14", "30", "60", "90", "9999"]
            ]}, "strict": True, "showCustomUi": True},
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 4, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # KPI labels (row 4)
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # KPI values (row 5)
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 0, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 4, "endIndex": 5},
            "properties": {"pixelSize": 48}, "fields": "pixelSize",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # Top creatives section header (row 8)
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8,
                                   "startColumnIndex": 0, "endColumnIndex": 13}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 0, "endColumnIndex": 13},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.15, "green": 0.45, "blue": 0.70},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # Query header row 10
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 9, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 13},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.90, "green": 0.90, "blue": 0.90},
                "textFormat": {"bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # Column widths
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 200}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 150}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 13},
            "properties": {"pixelSize": 90}, "fields": "pixelSize",
        }},
        # Number formats for query data
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 5, "endColumnIndex": 6},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 6, "endColumnIndex": 7},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 8, "endColumnIndex": 9},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 12, "endColumnIndex": 13},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": 9, "endRowIndex": 31, "startColumnIndex": 0, "endColumnIndex": 13},
            "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
            "left": {"style": "SOLID"}, "right": {"style": "SOLID"},
            "innerHorizontal": {"style": "SOLID"}, "innerVertical": {"style": "SOLID"},
        }},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 3}},
            "fields": "gridProperties.frozenRowCount",
        }},
    ]
    s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": reqs}).execute()
    print(f"✅ {TAB} built")


if __name__ == "__main__":
    s = get_sheets_service()
    build(s)
