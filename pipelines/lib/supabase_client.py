"""Supabase REST client — upsert helpers via PostgREST.

Lit .env.local automatiquement. Utilise SERVICE_ROLE_KEY pour bypass RLS.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable


def load_env(path: str | None = None) -> None:
    """Charge .env.local dans os.environ (sans écraser les vars existantes)."""
    if path is None:
        # remonte jusqu'à trouver .env.local
        cur = Path(__file__).resolve().parent
        for _ in range(5):
            cand = cur / ".env.local"
            if cand.exists():
                path = str(cand)
                break
            cur = cur.parent
    if not path or not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


class SupabaseClient:
    def __init__(self, url: str | None = None, key: str | None = None):
        load_env()
        self.url = (url or os.environ.get("SUPABASE_URL")
                    or os.environ.get("SUPABASE_PROJECT_URL", "")).rstrip("/")
        self.key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY")
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL / SERVICE_ROLE_KEY manquants dans .env.local")

    def _headers(self, prefer: str = "return=minimal,resolution=merge-duplicates") -> dict:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        }

    def upsert(self, table: str, rows: list[dict], on_conflict: str | None = None,
               batch: int = 500) -> int:
        if not rows:
            return 0
        total = 0
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            qs = f"?on_conflict={on_conflict}" if on_conflict else ""
            url = f"{self.url}/rest/v1/{table}{qs}"
            data = json.dumps(chunk, default=str).encode()
            req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        r.read()
                    total += len(chunk)
                    break
                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8", "ignore")
                    if attempt == 2 or e.code < 500:
                        raise RuntimeError(f"Supabase upsert {table} HTTP {e.code}: {body}") from e
                    time.sleep(2 ** attempt)
        return total

    def query(self, sql: str) -> list[dict]:
        """Exécute un SELECT via la Management API (nécessite SUPABASE_ACCESS_TOKEN)."""
        token = os.environ.get("SUPABASE_ACCESS_TOKEN")
        pid = os.environ.get("SUPABASE_PROJECT_ID")
        if not token or not pid:
            raise RuntimeError("SUPABASE_ACCESS_TOKEN / SUPABASE_PROJECT_ID requis")
        url = f"https://api.supabase.com/v1/projects/{pid}/database/query"
        data = json.dumps({"query": sql}).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
