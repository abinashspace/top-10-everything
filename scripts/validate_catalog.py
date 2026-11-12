"""Validate the generated JSON catalog for internal consistency.

Checks performed:
    * every JSON file parses
    * category and topic IDs are unique and well formed
    * every topic points at an existing category and ranking method
    * every referenced source exists in the source directory
    * supported topics always have at least one primary source
    * declared counts match the actual records
    * update frequencies and statuses use the allowed vocabularies
    * source usage lists reference real topics
    * no duplicate topic names inside a category

Usage:
    python scripts/validate_catalog.py

Exits with status 1 if any error is found. Warnings do not fail the build.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUBJECTIVITY = {"objective", "subjective", "mixed", "proxy"}
STATUSES = {"researched", "researched_proxy", "partial", "unsupported"}
AVAILABILITY = {"strong", "moderate", "limited", "none"}
FREQUENCIES = {"event", "daily", "weekly", "monthly", "quarterly", "yearly"}

errors: list[str] = []
warnings: list[str] = []


def load(relative: str) -> dict:
    path = ROOT / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing file: {relative}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {relative}: {exc}")
    return {}


def check_schemas() -> list[str]:
    """Optionally validate the artifacts against schema/*.json.

    jsonschema is not a required dependency; without it the build still works
    and the check is reported as skipped.
    """
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        print("INFO  jsonschema not installed; skipping JSON Schema validation")
        return []

    registry = Registry()
    for path in sorted((ROOT / "schema").glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        registry = registry.with_resource(uri=schema["$id"], resource=resource)

    messages: list[str] = []

    def validate(schema_name: str, record: dict, where: str) -> None:
        schema = json.loads((ROOT / schema_name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, registry=registry)
        for error in validator.iter_errors(record):
            messages.append(f"schema {schema_name}: {where}: {error.message}")

    topic_schema = "schema/topic.schema.json"
    for path in sorted((ROOT / "topics").glob("*.json")):
        if path.name == "index.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate("schema/category.schema.json", payload, path.name)
        for topic in payload.get("topics", []):
            validate(topic_schema, topic, topic["id"])

    directory = json.loads((ROOT / "sources/source-directory.json").read_text(encoding="utf-8"))
    for source in directory.get("sources", []):
        validate("schema/source.schema.json", source, source["id"])

    methods = json.loads((ROOT / "ranking-methods/methods.json").read_text(encoding="utf-8"))
    for method in methods.get("methods", []):
        validate("schema/ranking-method.schema.json", method, method["id"])

    return messages


def main() -> int:
    index = load("topics/index.json")
    directory = load("sources/source-directory.json")
    methods_payload = load("ranking-methods/methods.json")

    source_ids = {s["id"] for s in directory.get("sources", [])}
    method_ids = {m["id"] for m in methods_payload.get("methods", [])}
    category_ids = {c["id"] for c in index.get("categories", [])}

    if not source_ids:
        errors.append("source directory contains no sources")
    if not method_ids:
        errors.append("method library contains no methods")

    seen_topic_ids: set[str] = set()
    seen_names: dict[str, set[str]] = {}
    status_counts: Counter[str] = Counter()
    availability_counts: Counter[str] = Counter()
    topic_ids: set[str] = set()
    total_topics = 0
    total_subcategories = 0

    for entry in index.get("categories", []):
        category_id = entry["id"]
        payload = load(entry["file"])
        if not payload:
            continue
        category = payload.get("category", {})
        topics = payload.get("topics", [])

        if category.get("id") != category_id:
            errors.append(f"{entry['file']}: category id {category.get('id')!r} != {category_id!r}")
        if category.get("topic_count") != len(topics):
            errors.append(
                f"{entry['file']}: declared topic_count {category.get('topic_count')} != {len(topics)}"
            )

        declared_subcategories = sum(len(t.get("subcategories", [])) for t in topics)
        if category.get("subcategory_count") != declared_subcategories:
            errors.append(
                f"{entry['file']}: declared subcategory_count "
                f"{category.get('subcategory_count')} != {declared_subcategories}"
            )

        names = seen_names.setdefault(category_id, set())
        for topic in topics:
            total_topics += 1
            total_subcategories += topic.get("subcategory_count", 0)
            tid = topic.get("id", "")
            topic_ids.add(tid)

            if tid in seen_topic_ids:
                errors.append(f"duplicate topic id: {tid}")
            seen_topic_ids.add(tid)

            expected_prefix = f"{category_id}."
            if not tid.startswith(expected_prefix):
                errors.append(f"topic {tid!r} does not belong to category {category_id!r}")

            slug = tid[len(expected_prefix):] if tid.startswith(expected_prefix) else tid
            if slug != slug.lower() or " " in slug or "_" in slug:
                errors.append(f"topic id {tid!r} is not a clean lowercase slug")

            if topic.get("parent_id") != category_id:
                errors.append(f"{tid}: parent_id {topic.get('parent_id')!r} != {category_id!r}")

            if topic.get("name") in names:
                errors.append(f"{category_id}: duplicate topic name {topic.get('name')!r}")
            names.add(topic.get("name"))

            if not topic.get("subcategories"):
                errors.append(f"{tid}: no subcategories")
            if len(topic.get("subcategories", [])) != topic.get("subcategory_count"):
                errors.append(f"{tid}: subcategory_count does not match subcategories list")

            status = topic.get("research_status")
            if status not in STATUSES:
                errors.append(f"{tid}: invalid research_status {status!r}")
            status_counts[status] += 1

            availability = topic.get("data_availability")
            if availability not in AVAILABILITY:
                errors.append(f"{tid}: invalid data_availability {availability!r}")
            availability_counts[availability] += 1

            if topic.get("update_frequency") not in FREQUENCIES:
                errors.append(f"{tid}: invalid update_frequency {topic.get('update_frequency')!r}")

            method = topic.get("ranking_method", {})
            if method.get("id") not in method_ids:
                errors.append(f"{tid}: unknown ranking method {method.get('id')!r}")
            if method.get("subjectivity") not in SUBJECTIVITY:
                errors.append(f"{tid}: invalid subjectivity {method.get('subjectivity')!r}")
            if not method.get("question"):
                errors.append(f"{tid}: ranking question is empty")

            sources = topic.get("sources", {})
            primary = [s["id"] for s in sources.get("primary", [])]
            backup = [s["id"] for s in sources.get("backup", [])]
            for sid in primary + backup:
                if sid not in source_ids:
                    errors.append(f"{tid}: unknown source {sid!r}")

            if sources.get("primary_count") != len(primary):
                errors.append(f"{tid}: primary_count mismatch")
            if sources.get("backup_count") != len(backup):
                errors.append(f"{tid}: backup_count mismatch")
            if len(set(primary)) != len(primary):
                errors.append(f"{tid}: duplicate entries in primary sources")

            if status != "unsupported" and not primary:
                errors.append(f"{tid}: supported topic has no primary source")
            if status != "unsupported" and not (set(primary) | set(backup)):
                errors.append(f"{tid}: supported topic has no sources at all")
            if status == "unsupported" and availability != "none":
                errors.append(f"{tid}: unsupported topic must have availability 'none'")
            if status == "unsupported" and method.get("id") != "human_review":
                warnings.append(f"{tid}: unsupported topic does not use the human_review method")

            if topic.get("licensing_risk") not in {"low", "medium", "high", "unknown"}:
                errors.append(f"{tid}: invalid licensing_risk {topic.get('licensing_risk')!r}")

            if status == "researched" and availability == "limited":
                warnings.append(f"{tid}: marked researched but data availability is limited")
            if status == "partial" and availability == "strong":
                warnings.append(f"{tid}: marked partial although availability is strong")

    if index.get("total_topics") != total_topics:
        errors.append(f"index.total_topics {index.get('total_topics')} != {total_topics}")
    if index.get("total_subcategories") != total_subcategories:
        errors.append(
            f"index.total_subcategories {index.get('total_subcategories')} != {total_subcategories}"
        )
    if index.get("total_categories") != len(index.get("categories", [])):
        errors.append("index.total_categories does not match the category list")
    if index.get("total_categories") != len(category_ids):
        errors.append("index contains duplicate category ids")

    if index.get("research_status_counts") != dict(status_counts):
        errors.append(
            f"index.research_status_counts {index.get('research_status_counts')} != {dict(status_counts)}"
        )
    if index.get("data_availability_counts") != dict(availability_counts):
        errors.append(
            "index.data_availability_counts does not match the topic records"
        )

    for source in directory.get("sources", []):
        sid = source["id"]
        usage = source.get("usage", {})
        for tid in usage.get("primary_for_topics", []) + usage.get("backup_for_topics", []):
            if tid not in topic_ids:
                errors.append(f"source {sid}: usage references unknown topic {tid!r}")
        if usage.get("primary_for_count") != len(usage.get("primary_for_topics", [])):
            errors.append(f"source {sid}: primary_for_count mismatch")
        if usage.get("backup_for_count") != len(usage.get("backup_for_topics", [])):
            errors.append(f"source {sid}: backup_for_count mismatch")
        if not source.get("official_url"):
            errors.append(f"source {sid}: missing official_url")
        if not source.get("license", {}).get("commercial_use"):
            errors.append(f"source {sid}: missing commercial_use")
        if source.get("verification", {}).get("result") is None:
            warnings.append(f"source {sid}: never verified")
        if (
            not usage.get("primary_for_count")
            and not usage.get("backup_for_count")
            and not source.get("reference_only")
        ):
            warnings.append(f"source {sid}: not referenced by any topic")

    if directory.get("source_count") != len(directory.get("sources", [])):
        errors.append("source_directory.source_count does not match the source list")
    if methods_payload.get("method_count") != len(methods_payload.get("methods", [])):
        errors.append("methods.method_count does not match the method list")

    used_methods = {m["id"] for m in methods_payload.get("methods", []) if m.get("usage_count")}
    for mid in sorted(method_ids - used_methods):
        warnings.append(f"method {mid}: not used by any topic")

    schema_messages = check_schemas()
    warnings.extend(schema_messages)

    for message in warnings:
        print(f"WARN  {message}")
    for message in errors:
        print(f"ERROR {message}")

    print(
        f"\nChecked {total_topics} topics in {len(category_ids)} categories, "
        f"{len(source_ids)} sources and {len(method_ids)} methods."
    )
    print(f"Errors: {len(errors)}  Warnings: {len(warnings)}")
    if errors:
        return 1
    print("Catalog is internally consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
