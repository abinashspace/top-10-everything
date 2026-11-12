"""Polite HTTP fetching with an on-disk cache.

Every request carries a descriptive User-Agent, a timeout and a size cap. The
cache exists so that a ranking can be rebuilt without re-hitting providers, and
so tests and CI can run offline.

This module intentionally uses only the standard library.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "pipeline" / ".cache"

USER_AGENT = (
    "Top10EverythingResearchBot/0.1 "
    "(catalog ingestion proof of concept; +https://github.com/top10everything)"
)
TIMEOUT = 60
MAX_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_AGE_HOURS = 12


class FetchError(RuntimeError):
    """Raised when a URL cannot be retrieved and no usable cache exists."""


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.json"


def _read_cache(url: str) -> dict | None:
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_cache(url: str, body: str, status: int, headers: dict[str, str]) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "url": url,
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": status,
        "headers": headers,
        "body": body,
    }
    _cache_path(url).write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    return entry


def _fresh(entry: dict, max_age_hours: float) -> bool:
    try:
        retrieved = datetime.fromisoformat(entry["retrieved_at"])
    except (KeyError, ValueError):
        return False
    return datetime.now(timezone.utc) - retrieved < timedelta(hours=max_age_hours)


def fetch_text(
    url: str,
    *,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    refresh: bool = False,
    offline: bool = False,
    accept: str = "application/json,text/csv,text/plain;q=0.9,*/*;q=0.5",
    retries: int = 2,
) -> tuple[str, dict]:
    """Return (body, metadata).

    metadata carries retrieved_at, status and whether the body came from cache.
    """
    cached = _read_cache(url)
    if cached and not refresh and _fresh(cached, max_age_hours):
        return cached["body"], {
            "retrieved_at": cached["retrieved_at"],
            "status": cached.get("status"),
            "from_cache": True,
            "url": url,
        }
    if offline:
        if cached:
            return cached["body"], {
                "retrieved_at": cached["retrieved_at"],
                "status": cached.get("status"),
                "from_cache": True,
                "url": url,
            }
        raise FetchError(f"offline and no cache entry for {url}")

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
            method="GET",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                status = response.status
                raw = response.read(MAX_BYTES)
                charset = response.headers.get_content_charset() or "utf-8"
                body = raw.decode(charset, "replace")
                headers = {
                    "content_type": response.headers.get("Content-Type", ""),
                    "last_modified": response.headers.get("Last-Modified", ""),
                    "elapsed_ms": str(int((time.monotonic() - started) * 1000)),
                }
                entry = _write_cache(url, body, status, headers)
                return body, {
                    "retrieved_at": entry["retrieved_at"],
                    "status": status,
                    "from_cache": False,
                    "url": url,
                }
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 4xx other than 429 will not improve on retry.
            if 400 <= exc.code < 500 and exc.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    if cached:
        return cached["body"], {
            "retrieved_at": cached["retrieved_at"],
            "status": cached.get("status"),
            "from_cache": True,
            "url": url,
            "stale": True,
            "error": f"{type(last_error).__name__}: {last_error}"[:300],
        }
    raise FetchError(f"{url}: {type(last_error).__name__}: {last_error}") from last_error
