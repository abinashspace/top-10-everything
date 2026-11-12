"""Check whether catalogued sources respond to a representative request.

This is a reachability check, not a licence verification. It intentionally
makes one small unauthenticated request per source and never downloads bulk
files. Run it after changing the source catalogue, then rebuild the JSON.

Usage:
    python scripts/verify_sources.py
"""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILE = ROOT / "sources" / "source-directory.json"
OUT_FILE = ROOT / "sources" / "verification-results.json"

UA = "Top10EverythingResearchBot/0.1 (catalogue verification; +https://github.com/top10everything)"
TIMEOUT = 25
MAX_BYTES = 64 * 1024


def check(source: dict) -> dict:
    url = source.get("verification", {}).get("test_url") or source.get("official_url")
    started = time.monotonic()
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    base = {
        "source_id": source["id"],
        "name": source["name"],
        "test_url": url,
        "checked_at": checked_at,
        "method": "live_http_get",
        "http_status": None,
        "result": "not_checked",
        "final_url": None,
        "elapsed_ms": None,
        "notes": "",
    }
    if not url:
        base["result"] = "no_test_url"
        return base

    requires_auth = source.get("access", {}).get("authentication", "none") not in {"none", None}
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/html,application/xml;q=0.9,*/*;q=0.5",
            "Range": f"bytes=0-{MAX_BYTES - 1}",
        },
        method="GET",
    )
    try:
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=context) as response:
            status = response.status
            base["http_status"] = status
            base["final_url"] = response.geturl()
            # Read at most MAX_BYTES so that a range-ignoring server cannot flood us.
            response.read(MAX_BYTES)
            if 200 <= status < 300:
                base["result"] = "ok"
            elif status == 429:
                base["result"] = "rate_limited"
            elif status in (401,):
                base["result"] = "auth_required"
            elif status == 400 and requires_auth:
                base["result"] = "auth_required"
                base["notes"] = "Endpoint responded; the test request lacked valid credentials."
            elif status in (403,):
                base["result"] = "forbidden"
            else:
                base["result"] = "http_error"
    except urllib.error.HTTPError as exc:
        base["http_status"] = exc.code
        base["final_url"] = exc.geturl()
        if exc.code == 401:
            base["result"] = "auth_required"
            base["notes"] = "Endpoint responded; credentials are required."
        elif exc.code == 400 and requires_auth:
            base["result"] = "auth_required"
            base["notes"] = "Endpoint responded; the test request lacked valid credentials."
        elif exc.code == 403:
            base["result"] = "forbidden"
            base["notes"] = "Endpoint responded but denied this unauthenticated request (auth, WAF or policy)."
        elif exc.code == 429:
            base["result"] = "rate_limited"
            base["notes"] = "Rate limited during the check."
        elif exc.code in (404, 410):
            base["result"] = "http_error"
            base["notes"] = f"HTTP {exc.code}; the documented test URL may have moved."
        else:
            base["result"] = "http_error"
            base["notes"] = f"HTTP {exc.code}: {exc.reason}"
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
        base["result"] = "network_error"
        base["notes"] = f"{type(exc).__name__}: {exc}"[:500]
    except Exception as exc:  # noqa: BLE001 - we want a record, not a crash
        base["result"] = "network_error"
        base["notes"] = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        base["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return base


def main() -> None:
    if not SOURCE_FILE.exists():
        raise SystemExit("Run python scripts/build_catalog.py first.")
    directory = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    sources = directory["sources"]
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(check, s): s["id"] for s in sources}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"{result['result']:16} {result['http_status']!s:>4}  {result['source_id']}", flush=True)
    results.sort(key=lambda x: x["source_id"])
    payload = {
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checker": "scripts/verify_sources.py",
        "warning": "Reachability only. Licences, quotas and endpoints can change; manual review is still required.",
        "count": len(results),
        "results": {r["source_id"]: r for r in results},
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = {}
    for r in results:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print(json.dumps(counts, indent=2))
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    sys.exit(main())
