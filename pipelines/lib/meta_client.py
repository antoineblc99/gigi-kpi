"""Wrapper minimal pour Meta Graph API (Ads).

- Pagination automatique
- Backoff exponentiel sur 429 / 5xx / rate limit codes Meta (4, 17, 32, 613)
- Retourne dict / list[dict] direct
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Iterator


META_RATE_LIMIT_SUBCODES = {4, 17, 32, 613}


class MetaError(RuntimeError):
    pass


class MetaClient:
    def __init__(self, token: str | None = None, version: str | None = None):
        self.token = token or os.environ["META_ACCESS_TOKEN"]
        self.version = version or os.environ.get("META_API_VERSION", "v21.0")
        self.base = f"https://graph.facebook.com/{self.version}"

    def _request(self, url: str, params: dict | None = None) -> dict:
        if params is None:
            params = {}
        params = {**params, "access_token": self.token}
        # On envoie via querystring (GET) pour rester simple.
        if "?" in url:
            full = url + "&" + urllib.parse.urlencode(params, doseq=True)
        else:
            full = url + "?" + urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request(full, method="GET")
        for attempt in range(8):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")
                try:
                    err = json.loads(body).get("error", {})
                except Exception:
                    err = {}
                code = err.get("code")
                # Rate limit / transient — backoff plus long pour code 17 (user req limit)
                if e.code in (429, 500, 502, 503, 504) or code in META_RATE_LIMIT_SUBCODES:
                    sleep = min(300, 5 * (2 ** attempt))
                    print(f"  ⏳ rate limit ({e.code} code={code}), sleep {sleep}s")
                    time.sleep(sleep)
                    continue
                raise MetaError(f"Meta {e.code} code={code}: {body[:300]}") from e
            except urllib.error.URLError as e:
                sleep = min(60, 2 ** attempt)
                print(f"  ⏳ URL error {e}, sleep {sleep}s")
                time.sleep(sleep)
                continue
        raise MetaError(f"Meta retries exhausted: {url}")

    def get(self, path: str, params: dict | None = None) -> dict:
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        return self._request(url, params)

    def paginate(self, path: str, params: dict | None = None) -> Iterator[dict]:
        params = dict(params or {})
        params.setdefault("limit", 200)
        data = self.get(path, params)
        while True:
            for row in data.get("data", []):
                yield row
            nxt = (data.get("paging") or {}).get("next")
            if not nxt:
                return
            data = self._request(nxt)


def action_value(row: dict, field: str, action_type: str) -> float:
    for a in row.get(field, []) or []:
        if a.get("action_type") == action_type:
            try:
                return float(a.get("value", 0))
            except (TypeError, ValueError):
                return 0.0
    return 0.0
