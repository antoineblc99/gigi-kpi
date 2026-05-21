"""Supabase REST helpers for gigi-data-os pipelines."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

from .retry import retry_call

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")

_client: Client | None = None


def sb() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_PROJECT_URL") or os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def upsert(table: str, rows: list[dict], on_conflict: str | None = None) -> int:
    if not rows:
        return 0

    def _do() -> None:
        q = sb().table(table).upsert(rows, on_conflict=on_conflict) if on_conflict else sb().table(table).upsert(rows)
        q.execute()

    retry_call(_do, label=f"upsert {table}")
    return len(rows)


def insert_ignore_dupes(table: str, rows: list[dict], on_conflict: str) -> int:
    if not rows:
        return 0
    retry_call(
        lambda: sb().table(table).upsert(rows, on_conflict=on_conflict, ignore_duplicates=True).execute(),
        label=f"insert {table}",
    )
    return len(rows)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
