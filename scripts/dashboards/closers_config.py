"""Build Closers_Config tab — mapping GHL userId ↔ closer name."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
TAB = "Closers_Config"

# Fetched from GHL /users endpoint
CLOSERS = [
    # Name, GHL userId, email, active, role
    ["Anaïs Bruneel", "8MJYvMAYOFpD6l7hidBP", "anaisbnl7@gmail.com", True, "Closer"],
    ["Audrey Cuny", "x9HCDDvdqXyKVcnDmwKS", "audrey.gigiacademy@gmail.com", True, "Closer"],
    ["Mary Tregan", "ZZ3s2o6wtGk21mp61bBn", "pro.tregan.mary@gmail.com", True, "Closer"],
    ["Léa Dutertre", "1nccBeu2swH9l3vsbmQE", "contact@giginails.com", True, "Owner"],
    ["Laura Bourdoulous", "JWDTully7GuwL0U4sM4Q", "l.bourdou21@gmail.com", True, "Setter"],
    ["Laury Avril", "VWIwYs3WEwgc7L1zycX9", "laury.avril33@gmail.com", True, "Setter"],
]
HEADERS = ["Name", "GHL User ID", "Email", "Active", "Role"]


def ensure_sheet(s, title: str, headers: list[str]) -> int:
    meta = s.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sid_map = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}
    if title in sid_map:
        return sid_map[title]
    resp = s.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={
        "requests": [{"addSheet": {"properties": {"title": title}}}]
    }).execute()
    sid = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"{title}!A1",
        valueInputOption="RAW", body={"values": [headers]},
    ).execute()
    return sid


def main():
    s = get_sheets_service()
    sid = ensure_sheet(s, TAB, HEADERS)

    s.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range=f"{TAB}!A2:Z").execute()
    rows = [[c[0], c[1], c[2], "✅" if c[3] else "❌", c[4]] for c in CLOSERS]
    s.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"{TAB}!A2",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()

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
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 210}, "fields": "pixelSize",
        }},
    ]}).execute()
    print(f"✅ {TAB}: {len(CLOSERS)} entries")


if __name__ == "__main__":
    main()
