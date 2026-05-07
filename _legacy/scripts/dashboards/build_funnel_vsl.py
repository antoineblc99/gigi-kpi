"""Dashboard Funnel VSL — funnel Ads → LP → Opt-in → VSL → Survey → Call → Vente."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
TAB = "DashBoard_Funnel_VSL_v2"
DFV = "Data_Funnel_VSL"


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

    def sumifs(col: str) -> str:
        return f"=IFERROR(SUMIFS('{DFV}'!{col}:{col},'{DFV}'!A:A,\">=\"&$B$3),0)"

    rows = [
        ["DASHBOARD FUNNEL VSL", "", "", "", "", ""],
        ["Période (jours)", 30, "", "Aujourd'hui", "=TEXT(TODAY(),\"yyyy-mm-dd\")", ""],
        ["Début période", "=TODAY()-B2", "", "", "", ""],
        [""] * 6,
        # KPI row 1
        ["Spend (€)", "LPV", "Opt-ins", "Surveys", "Qualifiés", ""],
        [sumifs("B"), sumifs("G"), sumifs("H"), sumifs("J"), sumifs("L"), ""],
        [""] * 6,
        # KPI row 2
        ["Calls Bookés", "Calls Reçus", "Ventes", "Cash Collecté (€)", "ROAS", ""],
        [sumifs("N"), sumifs("P"), sumifs("R"), sumifs("U"), f"=IFERROR(D9/A6,0)", ""],
        [""] * 6,
        [""] * 6,
        # Funnel
        ["FUNNEL VSL (étape par étape)", "", "", "", "", ""],
        [""] * 6,
        ["Étape", "Volume", "Taux de passage", "Coût unitaire (€)", "Benchmark", ""],
        ["Impressions", sumifs("C"), "", "=IFERROR($A$6/B15*1000,0)", "CPM", ""],
        ["Link Clicks", sumifs("D"), "=IFERROR(B16/B15*100,0)", "=IFERROR($A$6/B16,0)",
            "=VLOOKUP(\"CTR (%)\",Benchmarks!A:B,2,FALSE)&\"% CTR\"", ""],
        ["LPV", sumifs("G"), "=IFERROR(B17/B16*100,0)", "=IFERROR($A$6/B17,0)",
            "=VLOOKUP(\"LPV Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"", ""],
        ["Opt-ins", sumifs("H"), "=IFERROR(B18/B17*100,0)", "=IFERROR($A$6/B18,0)",
            "=VLOOKUP(\"Opt-in Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"", ""],
        ["Surveys", sumifs("J"), "=IFERROR(B19/B18*100,0)", "=IFERROR($A$6/B19,0)", "—", ""],
        ["Qualifiés", sumifs("L"), "=IFERROR(B20/B19*100,0)", "=IFERROR($A$6/B20,0)",
            "=VLOOKUP(\"Qualif Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"", ""],
        ["Calls Bookés", sumifs("N"), "=IFERROR(B21/B20*100,0)", "=IFERROR($A$6/B21,0)", "—", ""],
        ["Calls Reçus", sumifs("P"), "=IFERROR(B22/B21*100,0)", "=IFERROR($A$6/B22,0)",
            "=VLOOKUP(\"Show Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"", ""],
        ["Ventes", sumifs("R"), "=IFERROR(B23/B22*100,0)", "=IFERROR($A$6/B23,0)",
            "=VLOOKUP(\"Close Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"", ""],
        [""] * 6,
        [""] * 6,
        # VTurb section
        ["VSL PERFORMANCE (vTurb)", "", "", "", "", ""],
        [""] * 6,
        ["Métrique", "Valeur", "Benchmark", "", "", ""],
        ["Play Rate (%)",
            "=IFERROR(SUMIFS('VTurb_Raw'!E:E,'VTurb_Raw'!A:A,\">=\"&$B$3)/COUNTIFS('VTurb_Raw'!A:A,\">=\"&$B$3),0)",
            "=VLOOKUP(\"Video Play Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"", "", "", ""],
        ["Avg Watch Time (s)",
            "=IFERROR(SUMPRODUCT('VTurb_Raw'!F:F,(('VTurb_Raw'!A:A>=$B$3)*1))/SUMIFS('VTurb_Raw'!C:C,'VTurb_Raw'!A:A,\">=\"&$B$3),0)",
            "—", "", "", ""],
        ["Completion Rate (%)",
            "=IFERROR(SUMPRODUCT('VTurb_Raw'!G:G,(('VTurb_Raw'!A:A>=$B$3)*1))/COUNTIFS('VTurb_Raw'!A:A,\">=\"&$B$3),0)",
            "=VLOOKUP(\"VSL Completion (%)\",Benchmarks!A:B,2,FALSE)&\"%\"", "", "", ""],
        ["CTA Click Rate (%)",
            "=IFERROR(SUMPRODUCT('VTurb_Raw'!I:I,(('VTurb_Raw'!A:A>=$B$3)*1))/COUNTIFS('VTurb_Raw'!A:A,\">=\"&$B$3),0)",
            "—", "", "", ""],
    ]

    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()

    # Formatting
    reqs = [
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                                   "startColumnIndex": 0, "endColumnIndex": 6}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 6},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.50, "green": 0.20, "blue": 0.55},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 46}, "fields": "pixelSize",
        }},
        # Dropdown
        {"setDataValidation": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": x} for x in ["7", "14", "30", "60", "90", "9999"]
            ]}, "strict": True, "showCustomUi": True},
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # KPI labels (rows 5, 8)
        *[{"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }} for r in (4, 7)],
        # KPI values
        *[{"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)",
        }} for r in (5, 8)],
        *[{"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": r, "endIndex": r + 1},
            "properties": {"pixelSize": 48}, "fields": "pixelSize",
        }} for r in (5, 8)],
        # A6 €, D9 €, E9 x
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 8, "endRowIndex": 9, "startColumnIndex": 3, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 8, "endRowIndex": 9, "startColumnIndex": 4, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00\"x\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},

        # Funnel section header (row 12)
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 11, "endRowIndex": 12,
                                   "startColumnIndex": 0, "endColumnIndex": 5}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 11, "endRowIndex": 12, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.50, "green": 0.20, "blue": 0.55},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # Funnel table header (row 14)
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 13, "endRowIndex": 14, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.90, "green": 0.90, "blue": 0.90},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": 13, "endRowIndex": 24, "startColumnIndex": 0, "endColumnIndex": 5},
            "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
            "left": {"style": "SOLID"}, "right": {"style": "SOLID"},
            "innerHorizontal": {"style": "SOLID"}, "innerVertical": {"style": "SOLID"},
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 14, "endRowIndex": 24, "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 14, "endRowIndex": 24, "startColumnIndex": 3, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},

        # VTurb section header (row 27)
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 26, "endRowIndex": 27,
                                   "startColumnIndex": 0, "endColumnIndex": 5}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 26, "endRowIndex": 27, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.50, "green": 0.20, "blue": 0.55},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 28, "endRowIndex": 29, "startColumnIndex": 0, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.90, "green": 0.90, "blue": 0.90},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": 28, "endRowIndex": 33, "startColumnIndex": 0, "endColumnIndex": 3},
            "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
            "left": {"style": "SOLID"}, "right": {"style": "SOLID"},
            "innerHorizontal": {"style": "SOLID"}, "innerVertical": {"style": "SOLID"},
        }},

        # Column widths
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 220}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 6},
            "properties": {"pixelSize": 150}, "fields": "pixelSize",
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
