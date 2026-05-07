"""Dashboard Funnel Follow — funnel IG → DMs → Calls → Ventes (détaillé)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
TAB = "DashBoard_Funnel_Follow_v2"  # new tab, keep old one for reference


def ensure_sheet(s, title: str) -> int:
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

    # References: Data_Funnel_Follow columns
    # A=Date B=Spend C=Impr D=Clicks E=CTR F=CPC G=Reach H=PV I=C/PV J=NewFol K=C/Fol
    # L=DMs M=Liens N=TxLien O=Bookés P=TxBook Q=Reçus R=TxShow S=Ventes T=TxClose
    # U=CashContract V=CashCollect W=CoutCall X=CoutVente Y=ROAS
    DFF = "Data_Funnel_Follow"

    def sumifs(col: str) -> str:
        return f"=IFERROR(SUMIFS('{DFF}'!{col}:{col},'{DFF}'!A:A,\">=\"&$B$3),0)"

    rows = [
        ["DASHBOARD FUNNEL FOLLOW", "", "", "", "", ""],
        ["Période (jours)", 30, "", "Aujourd'hui", "=TEXT(TODAY(),\"yyyy-mm-dd\")", ""],
        ["Début période", "=TODAY()-B2", "", "", "", ""],
        [""] * 6,

        # KPI row 1: Spend | Profile Visits | New Followers | DMs | Liens
        ["Spend (€)", "Profile Visits", "New Followers", "DMs envoyés", "Liens envoyés", ""],
        [sumifs("B"), sumifs("H"), sumifs("J"), sumifs("L"), sumifs("M"), ""],
        [""] * 6,

        # KPI row 2: Calls Bookés | Calls Reçus | Ventes | Cash Collecté | ROAS
        ["Calls Bookés", "Calls Reçus", "Ventes", "Cash Collecté (€)", "ROAS", ""],
        [sumifs("O"), sumifs("Q"), sumifs("S"), sumifs("V"), f"=IFERROR(D9/A6,0)", ""],
        [""] * 6,
        [""] * 6,

        # Funnel stages header
        ["FUNNEL (étape par étape)", "", "", "", "", ""],
        [""] * 6,
        ["Étape", "Volume", "Taux de passage", "Coût unitaire (€)", "Benchmark Target", ""],

        # Rows 14-20: funnel stages
        # Row 15: Impressions
        ["Impressions",
            sumifs("C"),
            "",
            "=IFERROR($A$6/B15*1000,0)",
            "CPM",
            ""],
        # Row 16: Profile Visits
        ["Profile Visits (PV)",
            sumifs("H"),
            "=IFERROR(B16/B15*100,0)",
            "=IFERROR($A$6/B16,0)",
            "=VLOOKUP(\"Cost/PV (€)\",Benchmarks!A:B,2,FALSE)",
            ""],
        # Row 17: New Followers
        ["New Followers",
            sumifs("J"),
            "=IFERROR(B17/B16*100,0)",
            "=IFERROR($A$6/B17,0)",
            "=VLOOKUP(\"Cost/Follower (€)\",Benchmarks!A:B,2,FALSE)",
            ""],
        # Row 18: DMs
        ["DMs (Conversations)",
            sumifs("L"),
            "=IFERROR(B18/B17*100,0)",
            "=IFERROR($A$6/B18,0)",
            "—",
            ""],
        # Row 19: Liens
        ["Liens envoyés",
            sumifs("M"),
            "=IFERROR(B19/B18*100,0)",
            "=IFERROR($A$6/B19,0)",
            "—",
            ""],
        # Row 20: Bookés
        ["Calls Bookés",
            sumifs("O"),
            "=IFERROR(B20/B19*100,0)",
            "=IFERROR($A$6/B20,0)",
            "—",
            ""],
        # Row 21: Reçus
        ["Calls Reçus (Show)",
            sumifs("Q"),
            "=IFERROR(B21/B20*100,0)",
            "=IFERROR($A$6/B21,0)",
            "=VLOOKUP(\"Show Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"",
            ""],
        # Row 22: Ventes
        ["Ventes",
            sumifs("S"),
            "=IFERROR(B22/B21*100,0)",
            "=IFERROR($A$6/B22,0)",
            "=VLOOKUP(\"Close Rate (%)\",Benchmarks!A:B,2,FALSE)&\"%\"",
            ""],
        [""] * 6,
        [""] * 6,

        # AdSet performance
        ["PERFORMANCE PAR ADSET (spend > 0)", "", "", "", "", ""],
        [""] * 6,
        ["Ad Set", "Spend (€)", "Impressions", "CTR (%)", "Profile Visits", "Cost/PV (€)"],
    ]

    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()

    # AdSet QUERY — dynamic
    # AdSet_Raw cols: A=Date B=AdSetName C=AdSetID D=Spend E=Imp F=Clicks G=CPM H=CPC I=CTR J=Reach K=PV L=C/PV
    adset_query_formula = (
        "=QUERY('AdSet_Raw'!A:R, "
        "\"SELECT B, SUM(D), SUM(E), AVG(I), SUM(K), AVG(L) \"&"
        "\"WHERE A >= date '\"&TEXT($B$3,\"yyyy-mm-dd\")&\"' \"&"
        "\"GROUP BY B ORDER BY SUM(D) DESC LABEL SUM(D) 'Spend', SUM(E) 'Impressions', \"&"
        "\"AVG(I) 'CTR', SUM(K) 'PV', AVG(L) 'Cost/PV'\", 1)"
    )
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A28",
        valueInputOption="USER_ENTERED", body={"values": [[adset_query_formula]]},
    ).execute()

    # Formatting
    requests = [
        # Title
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                                   "startColumnIndex": 0, "endColumnIndex": 6}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 6},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.15, "green": 0.40, "blue": 0.55},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 46}, "fields": "pixelSize",
        }},
        # Date filter: B2 dropdown
        {"setDataValidation": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": s} for s in ["7", "14", "30", "60", "90", "9999"]
            ]}, "strict": True, "showCustomUi": True},
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},

        # KPI label rows (5, 8): gray bg bold
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},

        # KPI value rows (6, 9): big bold
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 8, "endRowIndex": 9, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 5, "endIndex": 6},
            "properties": {"pixelSize": 48}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 8, "endIndex": 9},
            "properties": {"pixelSize": 48}, "fields": "pixelSize",
        }},

        # KPI value formats
        # A6 €, B6 int, C6 int, D6 int, E6 int
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # A9 int, B9 int, C9 int, D9 €, E9 ROAS (x)
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
                "backgroundColor": {"red": 0.15, "green": 0.40, "blue": 0.55},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},

        # Funnel table header (row 13)
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 13, "endRowIndex": 14, "startColumnIndex": 0, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.90, "green": 0.90, "blue": 0.90},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # Funnel table borders + cell format
        {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": 13, "endRowIndex": 22, "startColumnIndex": 0, "endColumnIndex": 5},
            "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
            "left": {"style": "SOLID"}, "right": {"style": "SOLID"},
            "innerHorizontal": {"style": "SOLID"}, "innerVertical": {"style": "SOLID"},
        }},
        # Funnel col B = integer, col C = percent, col D = €
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 14, "endRowIndex": 22, "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 14, "endRowIndex": 22, "startColumnIndex": 3, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # Column widths
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 230}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 6},
            "properties": {"pixelSize": 160}, "fields": "pixelSize",
        }},

        # AdSet section header (row 25)
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 24, "endRowIndex": 25,
                                   "startColumnIndex": 0, "endColumnIndex": 6}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 24, "endRowIndex": 25, "startColumnIndex": 0, "endColumnIndex": 6},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.15, "green": 0.40, "blue": 0.55},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},

        # Freeze top 3 rows
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 3}},
            "fields": "gridProperties.frozenRowCount",
        }},
    ]
    s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()
    print(f"✅ {TAB} built")


if __name__ == "__main__":
    s = get_sheets_service()
    build(s)
