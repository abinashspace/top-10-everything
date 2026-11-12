"""Validate the worked rankings against the catalog and their own rules.

Usage:
    python scripts/validate_rankings.py

Checks:
    * every rankings/*.json parses and has the required provenance fields
    * the topic exists in the catalog and the method matches the catalog method
    * every referenced source exists in the source directory
    * ranks are strictly increasing, values are non-increasing, entity ids unique
    * item counts are plausible for a "top 10" product
    * caveats are present and the snapshot records when data was retrieved
    * rankings/index.json agrees with the files on disk

Exit code 1 on error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANKINGS = ROOT / "rankings"

REQUIRED = {
    "schema_version",
    "topic_id",
    "topic_name",
    "category",
    "question",
    "method",
    "measure",
    "generated_at",
    "refresh_after",
    "snapshot",
    "sources",
    "ranking",
    "caveats",
}

errors: list[str] = []
warnings: list[str] = []


def load_catalog() -> tuple[dict[str, dict], set[str]]:
    topics: dict[str, dict] = {}
    for path in sorted((ROOT / "topics").glob("*.json")):
        if path.name == "index.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for topic in payload.get("topics", []):
            topics[topic["id"]] = topic
    sources = json.loads((ROOT / "sources" / "source-directory.json").read_text(encoding="utf-8"))
    return topics, {s["id"] for s in sources.get("sources", [])}


def main() -> int:
    if not RANKINGS.exists():
        print("No rankings directory; run python pipeline/run.py --all first.")
        return 0
    files = sorted(path for path in RANKINGS.glob("*.json") if path.name != "index.json")
    if not files:
        print("No ranking files found.")
        return 0

    topics, source_ids = load_catalog()
    seen_topics: set[str] = set()

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        label = path.name
        missing = REQUIRED - payload.keys()
        if missing:
            errors.append(f"{label}: missing fields {sorted(missing)}")
            continue

        topic_id = payload["topic_id"]
        if path.stem != topic_id:
            errors.append(f"{label}: filename does not match topic_id {topic_id!r}")
        if topic_id in seen_topics:
            errors.append(f"{label}: duplicate ranking for {topic_id}")
        seen_topics.add(topic_id)

        topic = topics.get(topic_id)
        if not topic:
            errors.append(f"{label}: topic {topic_id!r} is not in the catalog")
            continue

        if payload["method"]["id"] != topic["ranking_method"]["id"]:
            errors.append(
                f"{label}: method {payload['method']['id']!r} != catalog method "
                f"{topic['ranking_method']['id']!r}"
            )
        if payload["method"].get("matches_catalog_method") is not True:
            errors.append(f"{label}: method.matches_catalog_method is not true")

        if not payload["caveats"]:
            errors.append(f"{label}: no caveats; a ranking without limits is not publishable")
        if not payload["question"].strip():
            errors.append(f"{label}: empty question")

        snapshot = payload["snapshot"]
        if not snapshot.get("retrieved_at"):
            errors.append(f"{label}: snapshot.retrieved_at is missing")
        if snapshot.get("records_considered", 0) < len(payload["ranking"]):
            errors.append(f"{label}: records_considered is smaller than the emitted ranking")

        sources = payload["sources"]
        if not sources:
            errors.append(f"{label}: no sources recorded")
        for source in sources:
            if source.get("id") not in source_ids:
                errors.append(f"{label}: unknown source {source.get('id')!r}")

        rows = payload["ranking"]
        if not rows:
            errors.append(f"{label}: empty ranking")
        if len(rows) > 10:
            warnings.append(f"{label}: {len(rows)} items; the product is normally a top 10")
        ranks = [row.get("rank") for row in rows]
        if ranks != sorted(ranks):
            errors.append(f"{label}: ranks are not non-decreasing: {ranks}")
        if ranks and ranks[0] != 1:
            errors.append(f"{label}: ranking does not start at rank 1: {ranks}")
        for previous, current in zip(rows, rows[1:]):
            same_rank = previous.get("rank") == current.get("rank")
            same_value = previous.get("value") == current.get("value")
            if same_rank and not same_value:
                errors.append(
                    f"{label}: tied rank {previous.get('rank')} has different values "
                    f"({previous.get('value')} vs {current.get('value')})"
                )
            if not same_rank and same_value:
                warnings.append(
                    f"{label}: equal values at ranks {previous.get('rank')} and {current.get('rank')}"
                )
        ids = [row.get("entity_id") for row in rows]
        if len(set(ids)) != len(ids):
            errors.append(f"{label}: duplicate entity ids")
        values = [row.get("value") for row in rows]
        if any(not isinstance(value, (int, float)) for value in values):
            errors.append(f"{label}: non-numeric value present")
        else:
            if any(values[i] < values[i + 1] for i in range(len(values) - 1)):
                errors.append(f"{label}: values are not sorted descending")
        for row in rows:
            if not row.get("name"):
                errors.append(f"{label}: rank {row.get('rank')} has no name")
            if not row.get("unit"):
                errors.append(f"{label}: rank {row.get('rank')} has no unit")

    index_path = RANKINGS / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        listed = {entry["topic_id"] for entry in index.get("rankings", [])}
        if listed != seen_topics:
            errors.append(
                f"index.json topics do not match the files on disk "
                f"(missing: {sorted(seen_topics - listed)}, extra: {sorted(listed - seen_topics)})"
            )
        if index.get("count") != len(seen_topics):
            errors.append(f"index.count {index.get('count')} != {len(seen_topics)}")
    else:
        errors.append("rankings/index.json is missing")

    for message in warnings:
        print(f"WARN  {message}")
    for message in errors:
        print(f"ERROR {message}")
    print(f"\nChecked {len(files)} ranking(s). Errors: {len(errors)}  Warnings: {len(warnings)}")
    if errors:
        return 1
    print("Rankings are internally consistent with the catalog.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
