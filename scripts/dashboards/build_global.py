"""Dashboard Global — P&L + split VSL vs Follow côte à côte."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"


BENCHMARKS = [
    # Métrique                     Target  Excellent  Unit  Applies to
    ["CPL (€)",                    5,      2,         "€",  "VSL"],
    ["CPC (€)",                    0.10,   0.05,      "€",  "Both"],
    ["CTR (%)",                    2,      5,         "%",  "Both"],
    ["Cost/PV (€)",                0.10,   0.05,      "€",  "Follow"],
    ["Cost/Follower (€)",          1.00,   0.50,      "€",  "Follow"],
    ["LPV Rate (%)",               70,     85,        "%",  "VSL"],
    ["Opt-in Rate (%)",            30,     50,        "%",  "VSL"],
    ["Qualif Rate (%)",            40,     60,        "%",  "VSL"],
    ["Show Rate (%)",              70,     85,        "%",  "Both"],
    ["Close Rate (%)",             20,     30,        "%",  "Both"],
    ["ROAS",                       3,      5,         "x",  "Both"],
    ["Cost/Sale (% offer)",        20,     10,        "%",  "Both"],
    ["Video Play Rate (%)",        85,     95,        "%",  "VSL"],
    ["VSL Completion (%)",         15,     30,        "%",  "VSL"],
]


def ensure_sheet(s, title: str, headers: list[str] | None = None) -> int:
    meta = s.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sid_map = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}
    if title in sid_map:
        return sid_map[title]
    resp = s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={
        "requests": [{"addSheet": {"properties": {"title": title}}}]
    }).execute()
    sid = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    if headers:
        s.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=f"{title}!A1",
            valueInputOption="RAW", body={"values": [headers]},
        ).execute()
    return sid


def build_benchmarks(s):
    sid = ensure_sheet(s, "Benchmarks", ["Métrique", "Target", "Excellent", "Unité", "Applies to"])
    # Clear + write
    s.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range="Benchmarks!A2:Z").execute()
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range="Benchmarks!A2",
        valueInputOption="USER_ENTERED", body={"values": BENCHMARKS},
    ).execute()
    # Format: bold header, freeze, col widths
    s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            }},
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }},
    ]}).execute()
    print(f"✅ Benchmarks: {len(BENCHMARKS)} entries")


OFFER_PRICE = 2000  # EUR (used for Cost/Sale % of offer)

# Dashboard layout constants
DASH_TAB = "Dashboard Global"


def col_letter(idx: int) -> str:
    s = ""
    n = idx + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def build_dashboard_global(s):
    sid = ensure_sheet(s, DASH_TAB)
    # Wipe everything
    s.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range=f"{DASH_TAB}!A1:Z100").execute()

    # ---------- CONTENT ----------
    rows = [
        # Row 1: Title
        ["DASHBOARD GLOBAL", "", "", "", "", "", "", ""],
        # Row 2: date filter
        ["Période (jours)", 30, "", "Aujourd'hui", f"=TEXT(TODAY(),\"yyyy-mm-dd\")", "", "", ""],
        ["Début période", f"=TODAY()-B2", "", "Prix offre (€)", OFFER_PRICE, "", "", ""],
        [""] * 8,
        # KPI row 1 labels
        ["Spend Total (€)", "Cash Collecté (€)", "ROAS", "CAC (€)", "", "", "", ""],
        # KPI row 1 values (use RAW sheets directly as source of truth)
        [
            "=SUMIFS('Meta_Ads_Raw_VSL'!B:B,'Meta_Ads_Raw_VSL'!A:A,\">=\"&$B$3) + SUMIFS('Meta_Ads_Raw'!B:B,'Meta_Ads_Raw'!A:A,\">=\"&$B$3)",
            "=SUMIFS('Data_Closing'!J:J,'Data_Closing'!A:A,\">=\"&$B$3)",
            "=IFERROR(B6/A6, 0)",
            "=IFERROR(A6/SUMIFS('Data_Closing'!H:H,'Data_Closing'!A:A,\">=\"&$B$3), 0)",
            "", "", "", "",
        ],
        [""] * 8,
        # KPI row 2 labels
        ["Ventes", "Calls Reçus", "Show Rate (%)", "Close Rate (%)", "", "", "", ""],
        # KPI row 2 values
        [
            "=SUMIFS('Data_Closing'!H:H,'Data_Closing'!A:A,\">=\"&$B$3)",
            "=SUMIFS('Data_Closing'!E:E,'Data_Closing'!A:A,\">=\"&$B$3)",
            "=IFERROR(SUMIFS('Data_Closing'!E:E,'Data_Closing'!A:A,\">=\"&$B$3)/SUMIFS('Data_Closing'!D:D,'Data_Closing'!A:A,\">=\"&$B$3)*100, 0)",
            "=IFERROR(A9/B9*100, 0)",
            "", "", "", "",
        ],
        [""] * 8,
        [""] * 8,
        # Comparison table header
        ["COMPARAISON VSL vs FOLLOW", "", "", "", "", "", "", ""],
        [""] * 8,
        ["", "VSL", "Follow", "Total", "", "", "", ""],
        ["Spend (€)",
            "=SUMIFS('Meta_Ads_Raw_VSL'!B:B,'Meta_Ads_Raw_VSL'!A:A,\">=\"&$B$3)",
            "=SUMIFS('Meta_Ads_Raw'!B:B,'Meta_Ads_Raw'!A:A,\">=\"&$B$3)",
            "=B15+C15", "", "", "", ""],
        ["Impressions",
            "=SUMIFS('Meta_Ads_Raw_VSL'!C:C,'Meta_Ads_Raw_VSL'!A:A,\">=\"&$B$3)",
            "=SUMIFS('Meta_Ads_Raw'!C:C,'Meta_Ads_Raw'!A:A,\">=\"&$B$3)",
            "=B16+C16", "", "", "", ""],
        ["Calls Bookés",
            "=SUMIFS('Data_Closing'!D:D,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"VSL\")",
            "=SUMIFS('Data_Closing'!D:D,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"Follow\")",
            "=B17+C17", "", "", "", ""],
        ["Calls Reçus",
            "=SUMIFS('Data_Closing'!E:E,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"VSL\")",
            "=SUMIFS('Data_Closing'!E:E,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"Follow\")",
            "=B18+C18", "", "", "", ""],
        ["Ventes",
            "=SUMIFS('Data_Closing'!H:H,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"VSL\")",
            "=SUMIFS('Data_Closing'!H:H,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"Follow\")",
            "=B19+C19", "", "", "", ""],
        ["Cash Collecté (€)",
            "=SUMIFS('Data_Closing'!J:J,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"VSL\")",
            "=SUMIFS('Data_Closing'!J:J,'Data_Closing'!A:A,\">=\"&$B$3,'Data_Closing'!C:C,\"Follow\")",
            "=B20+C20", "", "", "", ""],
        ["ROAS",
            "=IFERROR(B20/B15, 0)", "=IFERROR(C20/C15, 0)", "=IFERROR(D20/D15, 0)",
            "", "", "", ""],
        ["CAC (€)",
            "=IFERROR(B15/B19, 0)", "=IFERROR(C15/C19, 0)", "=IFERROR(D15/D19, 0)",
            "", "", "", ""],
        ["Close Rate (%)",
            "=IFERROR(B19/B18*100, 0)", "=IFERROR(C19/C18*100, 0)", "=IFERROR(D19/D18*100, 0)",
            "", "", "", ""],
    ]

    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"{DASH_TAB}!A1",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()

    # ---------- FORMATTING ----------
    requests = [
        # Title row
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                                   "startColumnIndex": 0, "endColumnIndex": 8},
                        "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 8},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.20, "green": 0.25, "blue": 0.35},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1},
                               "bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }},
        # Row height for title
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 48}, "fields": "pixelSize",
        }},
        # KPI labels rows (5, 8): gray background, bold
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5,
                      "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 7, "endRowIndex": 8,
                      "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # KPI values rows (6, 9): big bold
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6,
                      "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 20},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 8, "endRowIndex": 9,
                      "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 20},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)",
        }},
        # KPI value row heights
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 5, "endIndex": 6},
            "properties": {"pixelSize": 54}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 8, "endIndex": 9},
            "properties": {"pixelSize": 54}, "fields": "pixelSize",
        }},
        # Number formats for KPI values (row 6 and 9)
        # A6: spend (€), B6: cash (€), C6: ROAS (x), D6: CAC (€)
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6,
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00\"x\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 5, "endRowIndex": 6,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # Row 9 number formats: A9 int, B9 int, C9 %, D9 %
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 8, "endRowIndex": 9,
                      "startColumnIndex": 2, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # Comparison section header (row 12)
        {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": 11, "endRowIndex": 12,
                                   "startColumnIndex": 0, "endColumnIndex": 4},
                        "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 11, "endRowIndex": 12,
                      "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.20, "green": 0.25, "blue": 0.35},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1},
                               "bold": True, "fontSize": 14},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # Comparison table header (row 14)
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 13, "endRowIndex": 14,
                      "startColumnIndex": 0, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.90, "green": 0.90, "blue": 0.90},
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        # Comparison table body borders
        {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": 13, "endRowIndex": 23,
                      "startColumnIndex": 0, "endColumnIndex": 4},
            "top": {"style": "SOLID"}, "bottom": {"style": "SOLID"},
            "left": {"style": "SOLID"}, "right": {"style": "SOLID"},
            "innerHorizontal": {"style": "SOLID"}, "innerVertical": {"style": "SOLID"},
        }},
        # Column widths
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 4},
            "properties": {"pixelSize": 180}, "fields": "pixelSize",
        }},
        # Freeze top 3 rows
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 3}},
            "fields": "gridProperties.frozenRowCount",
        }},
        # B2 data validation dropdown (timeframe)
        {"setDataValidation": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {
                "condition": {"type": "ONE_OF_LIST", "values": [
                    {"userEnteredValue": "7"},
                    {"userEnteredValue": "14"},
                    {"userEnteredValue": "30"},
                    {"userEnteredValue": "60"},
                    {"userEnteredValue": "90"},
                    {"userEnteredValue": "9999"},  # Lifetime
                ]},
                "strict": True, "showCustomUi": True,
            },
        }},
        # Format column B for dates: B3 is a formula returning a date
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": 3,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # Comparison body number formats
        # Row 15 (Spend), 20 (Cash Collecté), 22 (CAC) = € | Row 21 (ROAS) = x | Row 23 (Close %) = %
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 14, "endRowIndex": 15,
                      "startColumnIndex": 1, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 19, "endRowIndex": 20,
                      "startColumnIndex": 1, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 20, "endRowIndex": 21,
                      "startColumnIndex": 1, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00\"x\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 21, "endRowIndex": 22,
                      "startColumnIndex": 1, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0\\ €"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 22, "endRowIndex": 23,
                      "startColumnIndex": 1, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
    ]
    s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()
    _apply_conditional_formats(s, sid)
    print(f"✅ Dashboard Global built ({DASH_TAB})")


def _cf_rule(sid, start_row, end_row, start_col, end_col, formula, bg):
    return {"addConditionalFormatRule": {"rule": {
        "ranges": [{"sheetId": sid, "startRowIndex": start_row, "endRowIndex": end_row,
                    "startColumnIndex": start_col, "endColumnIndex": end_col}],
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]},
            "format": {"backgroundColor": bg, "textFormat": {"bold": True}},
        },
    }, "index": 0}}


def _apply_conditional_formats(s, sid):
    """Color KPI cells + comparison cells based on benchmarks."""
    GREEN = {"red": 0.75, "green": 0.92, "blue": 0.75}
    ORANGE = {"red": 1.0, "green": 0.87, "blue": 0.70}
    RED = {"red": 0.96, "green": 0.78, "blue": 0.78}

    reqs = []
    # ROAS cell C6 (row 5, col 2)
    reqs += [
        _cf_rule(sid, 5, 6, 2, 3, "=$C$6>=5", GREEN),
        _cf_rule(sid, 5, 6, 2, 3, "=AND($C$6>=3,$C$6<5)", ORANGE),
        _cf_rule(sid, 5, 6, 2, 3, "=AND($C$6>0,$C$6<3)", RED),
    ]
    # CAC D6: reasonable benchmark = < 10% of offer (200€) green, <20% (400€) orange, >20% red
    reqs += [
        _cf_rule(sid, 5, 6, 3, 4, "=AND($D$6>0,$D$6<=200)", GREEN),
        _cf_rule(sid, 5, 6, 3, 4, "=AND($D$6>200,$D$6<=400)", ORANGE),
        _cf_rule(sid, 5, 6, 3, 4, "=$D$6>400", RED),
    ]
    # Show Rate C9
    reqs += [
        _cf_rule(sid, 8, 9, 2, 3, "=$C$9>=85", GREEN),
        _cf_rule(sid, 8, 9, 2, 3, "=AND($C$9>=70,$C$9<85)", ORANGE),
        _cf_rule(sid, 8, 9, 2, 3, "=AND($C$9>0,$C$9<70)", RED),
    ]
    # Close Rate D9
    reqs += [
        _cf_rule(sid, 8, 9, 3, 4, "=$D$9>=30", GREEN),
        _cf_rule(sid, 8, 9, 3, 4, "=AND($D$9>=20,$D$9<30)", ORANGE),
        _cf_rule(sid, 8, 9, 3, 4, "=AND($D$9>0,$D$9<20)", RED),
    ]

    # Comparison table: ROAS row 21 (col B=VSL, C=Follow)
    for col in (1, 2):  # B, C
        reqs += [
            _cf_rule(sid, 20, 21, col, col+1, f"=INDIRECT(\"R21C{col+1}\",FALSE)>=5", GREEN),
            _cf_rule(sid, 20, 21, col, col+1, f"=AND(INDIRECT(\"R21C{col+1}\",FALSE)>=3,INDIRECT(\"R21C{col+1}\",FALSE)<5)", ORANGE),
            _cf_rule(sid, 20, 21, col, col+1, f"=AND(INDIRECT(\"R21C{col+1}\",FALSE)>0,INDIRECT(\"R21C{col+1}\",FALSE)<3)", RED),
        ]

    s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": reqs}).execute()


if __name__ == "__main__":
    s = get_sheets_service()
    build_benchmarks(s)
    build_dashboard_global(s)
