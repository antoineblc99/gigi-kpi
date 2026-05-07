"""Dashboard Setter — perf par setter (funnel Follow DM)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
TAB = "DashBoard_Setter_v2"
# KPI Setter Insta_Léa:
# A=Nom B=ConvInbound C=ConvOutbound D=FollowUp E=PropositionsAppels F=AppelsReserves G=Heures H=Debrief I=SubmittedAt


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

    KS = "'KPI Setter Insta_Léa'"

    rows = [
        ["DASHBOARD SETTER", "", "", "", "", "", "", ""],
        ["Période (jours)", 30, "", "Début période", "=TODAY()-B2", "", "", ""],
        [""] * 8,
        ["Total Conversations", "Total Follow-ups", "Total Appels Bookés", "Heures Travaillées", "", "", "", ""],
        [
            f"=IFERROR(SUMIFS({KS}!B:B,{KS}!I:I,\">=\"&$E$2)+SUMIFS({KS}!C:C,{KS}!I:I,\">=\"&$E$2),0)",
            f"=IFERROR(SUMIFS({KS}!D:D,{KS}!I:I,\">=\"&$E$2),0)",
            f"=IFERROR(SUMIFS({KS}!F:F,{KS}!I:I,\">=\"&$E$2),0)",
            f"=IFERROR(SUMIFS({KS}!G:G,{KS}!I:I,\">=\"&$E$2),0)",
            "", "", "", "",
        ],
        [""] * 8,
        [""] * 8,
        ["RANKING PAR SETTER", "", "", "", "", "", "", ""],
        [""] * 8,
    ]

    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()

    query = (
        f"=QUERY({KS}!A:I, "
        "\"SELECT A, COUNT(A), SUM(B), SUM(C), SUM(D), SUM(E), SUM(F), SUM(G) \"&"
        "\"WHERE I >= date '\"&TEXT($E$2,\"yyyy-mm-dd\")&\"' AND A IS NOT NULL \"&"
        "\"GROUP BY A ORDER BY SUM(F) DESC \"&"
        "\"LABEL A 'Setter', COUNT(A) 'Jours', SUM(B) 'Conv In', \"&"
        "\"SUM(C) 'Conv Out', SUM(D) 'Follow-ups', SUM(E) 'Propositions', \"&"
        "\"SUM(F) 'Appels Bookés', SUM(G) 'Heures'\", 1)"
    )
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A10",
        valueInputOption="USER_ENTERED", body={"values": [[query]]},
    ).execute()

    # Derived: Taux Prop→Call & Calls/heure
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!I10:J10",
        valueInputOption="USER_ENTERED", body={"values": [["Prop→Call (%)", "Calls/h"]]},
    ).execute()
    formula_rows = [[f"=IFERROR(G{i}/F{i}*100,0)", f"=IFERROR(G{i}/H{i},0)"] for i in range(11, 21)]
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!I11:J20",
        valueInputOption="USER_ENTERED", body={"values": formula_rows},
    ).execute()

    reqs = [
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                                   "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.15, "green": 0.55, "blue": 0.35},
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
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 0, "endColumnIndex": 4},
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
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8,
                                   "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 0, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.15, "green": 0.55, "blue": 0.35},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 9, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.90, "green": 0.90, "blue": 0.90},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 8, "endColumnIndex": 9},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 9, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 180}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 10},
            "properties": {"pixelSize": 120}, "fields": "pixelSize",
        }},
        {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": 9, "endRowIndex": 21, "startColumnIndex": 0, "endColumnIndex": 10},
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
