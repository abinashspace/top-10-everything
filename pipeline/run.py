"""Run the ingestion proof of concept.

Usage:
    python pipeline/run.py --all
    python pipeline/run.py --all --offline
    python pipeline/run.py --topic science.exoplanets --refresh
    python pipeline/run.py --list
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):  # allow `python pipeline/run.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pipeline.rankings import (  # noqa: E402
        SPECS,
        build_ranking,
        load_sources,
        load_topics,
        write_index,
        write_ranking,
    )
else:
    from .rankings import (  # noqa: F401
        SPECS,
        build_ranking,
        load_sources,
        load_topics,
        write_index,
        write_ranking,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build worked top-10 rankings from catalogued sources.")
    parser.add_argument("--all", action="store_true", help="build every configured ranking")
    parser.add_argument("--topic", action="append", default=[], help="topic id (repeatable)")
    parser.add_argument("--list", action="store_true", help="list configured topics")
    parser.add_argument("--offline", action="store_true", help="use the cache only; fail if empty")
    parser.add_argument("--refresh", action="store_true", help="ignore fresh cache entries")
    parser.add_argument("--top", type=int, default=10, help="items per ranking (default 10)")
    args = parser.parse_args(argv)

    if args.list:
        for topic_id, adapter in sorted(SPECS.items()):
            print(f"{topic_id:45} {adapter}")
        return 0

    if not args.all and not args.topic:
        parser.error("choose --all, --topic ID, or --list")
    if args.top < 1:
        parser.error("--top must be >= 1")

    topics = load_topics()
    sources = load_sources()
    topic_ids = sorted(SPECS) if args.all else args.topic

    payloads = []
    failures = 0
    for topic_id in topic_ids:
        try:
            payload = build_ranking(
                topic_id,
                topics=topics,
                sources=sources,
                offline=args.offline,
                refresh=args.refresh,
                top_n=args.top,
            )
        except Exception as exc:  # noqa: BLE001 - report per-topic failure, keep going
            failures += 1
            print(f"FAIL  {topic_id}: {type(exc).__name__}: {exc}")
            if "--debug" in sys.argv:
                traceback.print_exc()
            continue
        path = write_ranking(payload)
        payloads.append(payload)
        leader = payload["ranking"][0]
        print(
            f"OK    {topic_id:45} {len(payload['ranking']):2d} items, "
            f"leader={leader['name']} ({leader['value']})"
        )
        print(f"      -> {path.relative_to(path.parent.parent)}")

    index_path = write_index()
    if index_path:
        print(f"Wrote {index_path.relative_to(index_path.parent.parent)}")
    if failures:
        print(f"{failures} ranking(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
