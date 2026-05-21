"""Retry helper pour les erreurs réseau transitoires sur les writes Supabase.

Les pulls quotidiens plantent régulièrement sur des timeouts / connexions
coupées (Supabase, DNS au démarrage). Ces erreurs sont transitoires : un
simple retry avec backoff les absorbe. Les erreurs HTTP 4xx/5xx ne sont PAS
retentées ici — elles sont gérées au niveau applicatif (vrai bug, pas réseau).
"""
from __future__ import annotations

import socket
import time
import urllib.error
from typing import Callable, TypeVar

T = TypeVar("T")

# Tuple d'exceptions transitoires, construit défensivement selon les libs présentes.
_TRANSIENT: tuple[type[BaseException], ...] = (
    socket.timeout,
    socket.gaierror,
    TimeoutError,
    ConnectionError,
    urllib.error.URLError,
)
try:  # supabase-py / postgrest passent par httpx
    import httpx
    _TRANSIENT += (httpx.TransportError,)  # ReadTimeout, ConnectError, RemoteProtocolError…
except ImportError:
    pass
try:  # pull_ghl utilise requests
    import requests
    _TRANSIENT += (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
except ImportError:
    pass


def retry_call(fn: Callable[..., T], *args, attempts: int = 4,
               base_delay: float = 2.0, label: str = "", **kwargs) -> T:
    """Exécute fn(*args, **kwargs), retry les erreurs réseau avec backoff exponentiel.

    attempts=4 → 1 essai + 3 retries (2s, 4s, 8s). Total ~14s d'attente max.
    """
    name = label or getattr(fn, "__name__", "call")
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except _TRANSIENT as e:
            last = e
            if attempt == attempts - 1:
                break
            wait = base_delay * (2 ** attempt)
            print(f"  ⚠ {name}: erreur réseau ({type(e).__name__}), "
                  f"retry {attempt + 1}/{attempts - 1} dans {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError(f"{name}: échec après {attempts} tentatives") from last
