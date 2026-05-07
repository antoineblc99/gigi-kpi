"""pull_whop.py — Whop payments CSV → fact_payment.

Reads the most recent Whop CSV export in ~/Downloads/ (or a path passed via --csv)
and upserts into fact_payment. Idempotent on payment_id (Whop's pay_xxx).

Whop CSV columns supported (current export format ~2026-05):
  ID, Paid at, Created at, Status, Description, Payment method, Payment method type,
  Email, Subtotal, Payment Amount, Tax amount, Refunded amount, Refunded at, Fee,
  Promo code, Billing reason, Payment Currency, Customer name, Product ID, ...

Maps customer email → dim_lead.lead_id via lower(email).

Usage:
  python -m pipelines.pull_whop                       # auto-find latest in ~/Downloads
  python -m pipelines.pull_whop --csv path/to/file.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from pipelines.lib.db import sb, upsert

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")

DOWNLOADS = Path.home() / "Downloads"
WHOP_PATTERNS = ["exprt_*.csv", "payments_*.csv", "text.csv"]


def find_latest_csv() -> Path | None:
    candidates: list[Path] = []
    for pat in WHOP_PATTERNS:
        candidates.extend(Path(p) for p in glob.glob(str(DOWNLOADS / pat)))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # Validate it's actually a Whop CSV (has 'Payment Amount' header)
    for c in candidates:
        try:
            with c.open("r", encoding="utf-8") as f:
                header = f.readline()
            if "Payment Amount" in header and "Paid at" in header:
                return c
        except Exception:
            continue
    return None


def parse_dt(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    s = value.strip()
    # Whop format: "2026-02-28 23:32:08 +0800"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s*([+-]\d{4})?$", s)
    if m:
        date_part, time_part, tz = m.groups()
        if tz:
            tz_iso = f"{tz[:3]}:{tz[3:]}"
        else:
            tz_iso = "+00:00"
        try:
            dt = datetime.fromisoformat(f"{date_part}T{time_part}{tz_iso}")
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    # Fallback: try direct fromisoformat
    try:
        dt = datetime.fromisoformat(s.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def to_float(v: str | None) -> float:
    if not v:
        return 0.0
    s = str(v).strip().replace(",", ".")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def lookup_lead_id_batch(emails: set[str]) -> dict[str, str]:
    """Resolve emails → lead_id in batches to avoid N+1."""
    if not emails:
        return {}
    out: dict[str, str] = {}
    emails_list = sorted({e for e in emails if e})
    # Supabase REST in() filter; chunk to keep URLs reasonable
    chunk = 100
    for i in range(0, len(emails_list), chunk):
        batch = emails_list[i : i + chunk]
        res = sb().table("dim_lead").select("lead_id,email").in_("email", batch).execute()
        for row in res.data or []:
            email = (row.get("email") or "").lower().strip()
            if email:
                out[email] = row["lead_id"]
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=str, default=None,
                   help="Path to Whop CSV (default: latest in ~/Downloads)")
    args = p.parse_args()

    csv_path = Path(args.csv) if args.csv else find_latest_csv()
    if not csv_path or not csv_path.exists():
        print("[whop] no Whop CSV found in ~/Downloads/ "
              "(looked for exprt_*.csv, payments_*.csv, text.csv). "
              "Export from Whop dashboard → Payments → Export → drop in ~/Downloads/.",
              file=sys.stderr)
        return 1

    print(f"[whop] reading {csv_path.name}")

    raw_rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            raw_rows.append(r)

    if not raw_rows:
        print("[whop] CSV empty")
        return 0

    emails = {(r.get("Email") or "").lower().strip() for r in raw_rows}
    emails = {e for e in emails if e}
    lead_lookup = lookup_lead_id_batch(emails)

    fact_rows: list[dict] = []
    for r in raw_rows:
        email = (r.get("Email") or "").lower().strip() or None
        amount = to_float(r.get("Payment Amount"))
        refunded = to_float(r.get("Refunded amount"))
        currency = (r.get("Payment Currency") or "eur").lower().strip()
        pid = (r.get("ID") or "").strip()
        if not pid:
            continue

        fact_rows.append({
            "payment_id":        pid,
            "stripe_payment_id": None,
            "lead_id":           lead_lookup.get(email) if email else None,
            "customer_email":    email,
            "amount":            amount,
            "currency":          currency,
            "status":            (r.get("Status") or "").strip().lower() or None,
            "payment_method":    (r.get("Payment method type") or "").strip() or None,
            "description":       (r.get("Description") or "").strip() or None,
            "paid_at":           parse_dt(r.get("Paid at")) or parse_dt(r.get("Created at")),
            "refunded_amount":   refunded,
            "metadata": {
                "fee":            to_float(r.get("Fee")),
                "subtotal":       to_float(r.get("Subtotal")),
                "tax_amount":     to_float(r.get("Tax amount")),
                "promo_code":     (r.get("Promo code") or "").strip() or None,
                "billing_reason": (r.get("Billing reason") or "").strip() or None,
                "customer_name":  (r.get("Customer name") or "").strip() or None,
                "card_brand":     (r.get("Card brand") or "").strip() or None,
                "last_4":         (r.get("Last 4") or "").strip() or None,
                "product_id":     (r.get("Product ID") or "").strip() or None,
                "billing_country": (r.get("Billing address country") or "").strip() or None,
                "receipt_number": (r.get("Receipt number") or "").strip() or None,
            },
            "source":            "whop",
        })

    # Dedupe by payment_id (PK)
    fact_rows = list({r["payment_id"]: r for r in fact_rows}.values())
    matched = sum(1 for r in fact_rows if r["lead_id"])
    n = upsert("fact_payment", fact_rows, on_conflict="payment_id")

    total_paid = sum(r["amount"] for r in fact_rows if r["status"] == "paid")
    total_refunded = sum(r["refunded_amount"] for r in fact_rows)

    print(f"[whop] upserted {n} payments into fact_payment "
          f"({matched} matched to dim_lead by email, {len(emails)} unique emails)")
    print(f"[whop] total paid: {total_paid:.2f} EUR · refunded: {total_refunded:.2f} EUR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
