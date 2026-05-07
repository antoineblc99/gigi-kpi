"""
One-shot migration: normalize column A (Date) in Data_Funnel_VSL and Data_Funnel_Follow
from dd/MM or dd/MM/yyyy to ISO yyyy-MM-dd.

Why: DailyReport.gs used to write dd/MM, Python scripts write ISO. Dashboards choke on mix.
After this script + DailyReport.gs patch, all rows are ISO.

Idempotent: rows already in ISO are left untouched.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backfill"))
from auth import get_sheets_service  # noqa: E402

SHEET_ID = "1rYnX1EXbn1Ij3cDiYRgO4rq5j96W2ZA4uqtP66TSxFo"
TARGET_TABS = ["Data_Funnel_VSL", "Data_Funnel_Follow"]
DEFAULT_YEAR = 2026  # pour les dd/MM sans année


def to_iso(value: str) -> str | None:
    """Retourne yyyy-MM-dd ou None si pas convertible."""
    s = str(value).strip()
    if not s:
        return None
    # déjà ISO
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        pass
    # dd/MM/yyyy
    try:
        return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    # dd/MM (assume année courante)
    try:
        d = datetime.strptime(s, "%d/%m")
        return d.replace(year=DEFAULT_YEAR).strftime("%Y-%m-%d")
    except ValueError:
        pass
    return None


def migrate_tab(svc, tab: str) -> dict:
    rng = f"'{tab}'!A:A"
    resp = svc.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=rng).execute()
    values = resp.get("values", [])
    if not values:
        return {"tab": tab, "total": 0, "changed": 0, "skipped": 0, "errors": []}

    updates = []
    changed = skipped = 0
    errors = []
    for idx, row in enumerate(values[1:], start=2):  # skip header, 1-indexed sheet rows
        cell = row[0] if row else ""
        iso = to_iso(cell)
        if iso is None:
            if str(cell).strip():
                errors.append(f"row {idx}: '{cell}' non parsable")
            skipped += 1
            continue
        if str(cell).strip() == iso:
            skipped += 1
            continue
        updates.append({"range": f"'{tab}'!A{idx}", "values": [[iso]]})
        changed += 1

    if updates:
        body = {"valueInputOption": "USER_ENTERED", "data": updates}
        svc.spreadsheets().values().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()

    return {
        "tab": tab,
        "total": len(values) - 1,
        "changed": changed,
        "skipped": skipped,
        "errors": errors,
    }


def main():
    svc = get_sheets_service()
    print(f"=== Migration dates dd/MM → ISO — sheet {SHEET_ID} ===\n")
    for tab in TARGET_TABS:
        result = migrate_tab(svc, tab)
        print(f"[{result['tab']}] total={result['total']} changed={result['changed']} skipped={result['skipped']}")
        for err in result["errors"]:
            print(f"  ⚠ {err}")
    print("\n✓ Migration terminée.")


if __name__ == "__main__":
    main()
