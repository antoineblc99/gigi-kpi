"""Minimal GoHighLevel API wrapper (LeadConnector v2)."""
import os
import time
from typing import Any, Iterator

import requests

GHL_BASE = "https://services.leadconnectorhq.com"


class GHLClient:
    def __init__(self, api_key: str | None = None, location_id: str | None = None, version: str = "2021-07-28"):
        self.api_key = api_key or os.environ["GHL_API_KEY"]
        self.location_id = location_id or os.environ["GHL_LOCATION_ID"]
        self.version = version

    def _headers(self, version: str | None = None, json_body: bool = False) -> dict:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Version": version or self.version,
            "Accept": "application/json",
        }
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body: dict | None = None, version: str | None = None) -> dict:
        url = f"{GHL_BASE}{path}"
        headers = self._headers(version=version, json_body=json_body is not None)
        for attempt in range(5):
            r = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 502, 503, 504):
                wait = 2 ** attempt
                time.sleep(wait)
                continue
            raise RuntimeError(f"GHL {method} {path} → {r.status_code}: {r.text[:500]}")
        raise RuntimeError(f"GHL {method} {path}: retries exhausted")

    # ---- Contacts ----
    def search_contacts(self, *, page_limit: int = 100, filters: list[dict] | None = None,
                        sort: list[dict] | None = None) -> Iterator[dict]:
        """POST /contacts/search with searchAfter pagination."""
        search_after: list[Any] | None = None
        body_sort = sort or [{"field": "dateAdded", "direction": "desc"}]
        while True:
            body: dict = {
                "locationId": self.location_id,
                "pageLimit": page_limit,
                "sort": body_sort,
            }
            if filters:
                body["filters"] = filters
            if search_after:
                body["searchAfter"] = search_after
            data = self._request("POST", "/contacts/search", json_body=body, version="2021-07-28")
            contacts = data.get("contacts", []) or []
            if not contacts:
                break
            for c in contacts:
                yield c
            if len(contacts) < page_limit:
                break
            last = contacts[-1]
            search_after = last.get("searchAfter") or [
                last.get("dateAdded"), last.get("id"),
            ]
            if not any(search_after):
                break

    # ---- Opportunities ----
    def search_opportunities(self, *, limit: int = 100) -> Iterator[dict]:
        """GET /opportunities/search with page pagination."""
        page = 1
        while True:
            data = self._request("GET", "/opportunities/search", params={
                "location_id": self.location_id,
                "limit": limit,
                "page": page,
            }, version="2021-07-28")
            opps = data.get("opportunities", []) or []
            if not opps:
                break
            for o in opps:
                yield o
            meta = data.get("meta") or {}
            next_page = meta.get("nextPage")
            if not next_page:
                if len(opps) < limit:
                    break
                page += 1
            else:
                page = int(next_page) if str(next_page).isdigit() else page + 1
            if page > 200:
                break

    def list_pipelines(self) -> list[dict]:
        data = self._request("GET", "/opportunities/pipelines", params={"locationId": self.location_id},
                             version="2021-07-28")
        return data.get("pipelines", []) or []

    # ---- Calendar events ----
    def calendar_events(self, calendar_id: str, start_ms: int, end_ms: int) -> list[dict]:
        data = self._request("GET", "/calendars/events", params={
            "locationId": self.location_id,
            "calendarId": calendar_id,
            "startTime": str(start_ms),
            "endTime": str(end_ms),
        }, version="2021-04-15")
        return data.get("events", []) or []

    # ---- Surveys ----
    def survey_submissions(self, survey_id: str, *, page_size: int = 100) -> Iterator[dict]:
        page = 1
        while True:
            data = self._request("GET", "/surveys/submissions", params={
                "locationId": self.location_id,
                "surveyId": survey_id,
                "limit": page_size,
                "page": page,
            }, version="2021-07-28")
            subs = data.get("submissions", []) or []
            if not subs:
                break
            for s in subs:
                yield s
            meta = data.get("meta") or {}
            next_page = meta.get("nextPage")
            if not next_page:
                break
            page = int(next_page) if str(next_page).isdigit() else page + 1
            if page > 200:
                break

    def get_contact(self, contact_id: str) -> dict:
        data = self._request("GET", f"/contacts/{contact_id}", version="2021-07-28")
        return data.get("contact", data)
