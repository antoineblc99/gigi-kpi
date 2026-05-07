"""pull_stripe.py — Stripe charges/payments → fact_payment.

Backfills the last N days (default 90). Idempotent on stripe_payment_id.
Maps customer.email → dim_lead via lower(email).

Usage:
  python -m pipelines.pull_stripe [--days 90]

Env:
  STRIPE_SECRET_KEY (sk_live_… or sk_test_…)  ← required, else exits 0 with a log line.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from pipelines.lib.db import sb, upsert

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")


def _to_iso(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _lookup_lead_id(email: str | None) -> str | None:
    if not email:
        return None
    res = sb().table("dim_lead").select("lead_id").ilike("email", email).limit(1).execute()
    if res.data:
        return res.data[0]["lead_id"]
    return None


def _payment_method(charge) -> str | None:
    pmd = charge.get("payment_method_details") or {}
    return pmd.get("type")


def _amount_eur(charge) -> float:
    # Stripe amounts are in the smallest currency unit (cents). For EUR/USD this is /100.
    cur = (charge.get("currency") or "eur").lower()
    minor = charge.get("amount") or 0
    if cur in ("jpy", "krw"):  # zero-decimal
        return float(minor)
    return round(minor / 100, 2)


def _refunded_eur(charge) -> float:
    cur = (charge.get("currency") or "eur").lower()
    minor = charge.get("amount_refunded") or 0
    if cur in ("jpy", "krw"):
        return float(minor)
    return round(minor / 100, 2)


def fetch_charges(since_ts: int):
    import stripe
    rows: list[dict] = []
    starting_after = None
    while True:
        kwargs = {"limit": 100, "created": {"gte": since_ts}, "expand": ["data.customer"]}
        if starting_after:
            kwargs["starting_after"] = starting_after
        page = stripe.Charge.list(**kwargs)
        for ch in page.auto_paging_iter() if not starting_after else page.data:
            yield ch
        if not page.has_more:
            break
        starting_after = page.data[-1].id
        time.sleep(0.05)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    args = p.parse_args()

    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        print("[stripe] STRIPE_SECRET_KEY not set in .env.local — skipping. "
              "Add `STRIPE_SECRET_KEY=sk_live_…` to enable.", file=sys.stderr)
        return 0

    import stripe
    stripe.api_key = key

    since = datetime.now(tz=timezone.utc) - timedelta(days=args.days)
    since_ts = int(since.timestamp())
    print(f"[stripe] backfilling charges since {since.date().isoformat()} ({args.days}d)")

    rows: list[dict] = []
    seen_emails: set[str] = set()
    for ch in fetch_charges(since_ts):
        ch_d = ch.to_dict() if hasattr(ch, "to_dict") else dict(ch)
        cust = ch_d.get("customer") or {}
        email = (cust.get("email") if isinstance(cust, dict) else None) \
                or ch_d.get("billing_details", {}).get("email") \
                or ch_d.get("receipt_email")
        email = email.lower().strip() if email else None
        if email and email not in seen_emails:
            seen_emails.add(email)
        lead_id = _lookup_lead_id(email)
        rows.append({
            "payment_id":        ch_d["id"],          # PK in fact_payment
            "stripe_payment_id": ch_d["id"],
            "lead_id":           lead_id,
            "customer_email":    email,
            "amount":            _amount_eur(ch_d),
            "currency":          (ch_d.get("currency") or "eur").lower(),
            "status":            ch_d.get("status"),
            "payment_method":    _payment_method(ch_d),
            "description":       ch_d.get("description"),
            "paid_at":           _to_iso(ch_d.get("created")),
            "refunded_amount":   _refunded_eur(ch_d),
            "metadata":          ch_d.get("metadata") or {},
            "source":            "stripe",
        })

    if not rows:
        print("[stripe] 0 charges in window")
        return 0

    # dedupe by payment_id (PK)
    rows = list({r["payment_id"]: r for r in rows}.values())
    n = upsert("fact_payment", rows, on_conflict="payment_id")
    matched = sum(1 for r in rows if r["lead_id"])
    print(f"[stripe] upserted {n} charges into fact_payment "
          f"({matched} matched to dim_lead by email, {len(seen_emails)} unique emails)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
