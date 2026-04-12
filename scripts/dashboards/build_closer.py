"""Dashboard Closer — ranking per-closer perf."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
TAB = "DashBoard_Closer_v2"
# KPI Closer_Léa columns:
# A=Nom B=Planifiés C=Reçus D=FollowUp E=Acomptes F=Ventes G=CashContract H=CashCollect
# S=SubmittedAt V=Mois W=Year


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

    KC = "'KPI Closer_Léa'"

    rows = [
        ["DASHBOARD CLOSER", "", "", "", "", "", "", ""],
        ["Période (jours)", 30, "", "Début période", "=TODAY()-B2", "", "", ""],
        [""] * 8,
        # Aggregate totals KPI
        ["Total Reçus", "Total Ventes", "Total Cash Collecté (€)", "Close Rate global", "", "", "", ""],
        [
            f"=IFERROR(SUMIFS({KC}!C:C,{KC}!S:S,\">=\"&$E$2),0)",
            f"=IFERROR(SUMIFS({KC}!F:F,{KC}!S:S,\">=\"&$E$2),0)",
            f"=IFERROR(SUMIFS({KC}!H:H,{KC}!S:S,\">=\"&$E$2),0)",
            "=IFERROR(B5/A5*100,0)",
            "", "", "", "",
        ],
        [""] * 8,
        [""] * 8,
        ["RANKING PAR CLOSER", "", "", "", "", "", "", ""],
        [""] * 8,
    ]

    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()

    # QUERY aggregating per closer (over filtered date range)
    query = (
        f"=QUERY({KC}!A:S, "
        "\"SELECT A, COUNT(A), SUM(C), SUM(D), SUM(E), SUM(F), SUM(G), SUM(H) \"&"
        "\"WHERE S >= date '\"&TEXT($E$2,\"yyyy-mm-dd\")&\"' AND A IS NOT NULL \"&"
        "\"GROUP BY A ORDER BY SUM(H) DESC \"&"
        "\"LABEL A 'Closer', COUNT(A) 'Jours', SUM(C) 'Calls Reçus', \"&"
        "\"SUM(D) 'Follow-ups', SUM(E) 'Acomptes', SUM(F) 'Ventes', \"&"
        "\"SUM(G) 'Cash Contracté', SUM(H) 'Cash Collecté'\", 1)"
    )
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A10",
        valueInputOption="USER_ENTERED", body={"values": [[query]]},
    ).execute()

    # Compute close rate + avg deal in adjacent columns (after query)
    derived = [
        ["", "", "", "", "", "", "", "Close Rate"],
        [""] * 8,
    ]
    # place derived header at row 10, col I
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!I10",
        valueInputOption="USER_ENTERED", body={"values": [["Close Rate", "Avg Deal (€)"]]},
    ).execute()

    # Fill formulas for rows 11-20 (up to 10 closers)
    formula_rows = []
    for i in range(11, 21):
        formula_rows.append([
            f"=IFERROR(F{i}/C{i}*100,0)",     # Close Rate = Ventes / Reçus
            f"=IFERROR(H{i}/F{i},0)",         # Avg Deal = Cash Collecté / Ventes
        ])
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!I11:J20",
        valueInputOption="USER_ENTERED", body={"values": formula_rows},
    ).execute()

    # Formatting
    reqs = [
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                                   "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.60, "green": 0.30, "blue": 0.15},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 46}, "fields": "pixelSize",
        }},
        # Dropdown B2
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

        # KPI labels row 4
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # KPI values row 5
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
        # Cash Collecté € format
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 3, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},

        # Ranking section header (row 8)
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8,
                                   "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 0, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.60, "green": 0.30, "blue": 0.15},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # QUERY header row (10) will be auto-populated, format as bold + bg
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 9, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.90, "green": 0.90, "blue": 0.90},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # Cash cols (G, H) as €
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 6, "endColumnIndex": 8},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # I (Close Rate) as %
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 8, "endColumnIndex": 9},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # J (Avg Deal) as €
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 10, "endRowIndex": 30, "startColumnIndex": 9, "endColumnIndex": 10},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},

        # Column widths
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 180}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 10},
            "properties": {"pixelSize": 130}, "fields": "pixelSize",
        }},

        # Borders
        {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": 9, "endRowIndex": 21, "startColumnIndex": 0, "endColumnIndex": 10},
            "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
            "left": {"style": "SOLID"}, "right": {"style": "SOLID"},
            "innerHorizontal": {"style": "SOLID"}, "innerVertical": {"style": "SOLID"},
        }},

        # Freeze top 3
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
