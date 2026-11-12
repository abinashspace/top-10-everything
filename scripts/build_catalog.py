"""Build the JSON catalog from the curated Python definitions.

Usage:
    python scripts/build_catalog.py

Optional inputs:
    sources/verification-results.json  (produced by scripts/verify_sources.py)

The generated JSON files are the public artifact. The Python files are the
editable source of truth.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from method_catalog import METHODS, METHOD_INDEX  # noqa: E402
from source_catalog import SOURCES  # noqa: E402
from topic_catalog import BUNDLES, CATEGORIES, EXTRA_BACKUP  # noqa: E402

SCHEMA_VERSION = "1.0.0"
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

AVAILABILITY_SCORE = {"strong": 3, "moderate": 2, "limited": 1, "none": 0}
FREQUENCY_ORDER = ["event", "daily", "weekly", "monthly", "quarterly", "yearly"]


def load_verification() -> dict:
    path = ROOT / "sources" / "verification-results.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("results", data)


VERIFICATION = load_verification()
SOURCE_BY_ID = {s["id"]: s for s in SOURCES}


def mode_risk(modes: list[str]) -> str:
    if not modes:
        return "unknown"
    if "prohibited" in modes:
        return "high"
    if any(m in {"unclear", "varies", "allowed_with_conditions"} for m in modes):
        return "medium"
    return "low"


def source_risk(primary: list[str], backup: list[str]) -> str:
    """Primary data dominates the risk; a restricted backup only raises it to medium."""
    rank = {"low": 0, "medium": 1, "high": 2, "unknown": -1}
    primary_modes = [SOURCE_BY_ID[s]["license"]["commercial_use"] for s in primary if s in SOURCE_BY_ID]
    backup_modes = [SOURCE_BY_ID[s]["license"]["commercial_use"] for s in backup if s in SOURCE_BY_ID]
    primary_risk = mode_risk(primary_modes)
    backup_risk = mode_risk(backup_modes)
    if backup_risk == "high":
        backup_risk = "medium"
    if rank[primary_risk] < 0:
        return backup_risk
    return primary_risk if rank[primary_risk] >= rank[backup_risk] else backup_risk


def source_ref(source_id: str) -> dict:
    s = SOURCE_BY_ID[source_id]
    return {
        "id": source_id,
        "name": s["name"],
        "access_model": s["access"]["model"],
        "commercial_use": s["license"]["commercial_use"],
        "attribution_required": s["license"]["attribution_required"],
    }


def resolved_sources(category_id: str, topic: dict) -> tuple[list[str], list[str]]:
    bundle_primary, bundle_backup = BUNDLES[topic["bundle"]]
    primary = list(dict.fromkeys(topic["primary"] or bundle_primary))
    backup = list(dict.fromkeys(topic["backup"] or bundle_backup))
    backup += EXTRA_BACKUP.get(f"{category_id}.{topic['slug']}", [])
    backup = [b for b in dict.fromkeys(backup) if b not in primary]
    return primary, backup


def make_topic(category: dict, topic: dict, topic_index: dict) -> dict:
    topic_id = f"{category['id']}.{topic['slug']}"
    primary, backup = resolved_sources(category["id"], topic)
    method = METHOD_INDEX[topic["method"]]
    status = topic["status"] or {
        "strong": "researched", "moderate": "researched",
        "limited": "partial", "none": "unsupported",
    }[topic["availability"]]
    question = topic["question"] or f"Top 10 {topic['name'].lower()} ranked by {topic['metric']}."
    all_sources = primary + backup
    return {
        "id": topic_id,
        "name": topic["name"],
        "parent_id": category["id"],
        "parent_name": category["name"],
        "path": [category["name"], topic["name"]],
        "level": 2,
        "subcategories": topic["subcategories"],
        "subcategory_count": len(topic["subcategories"]),
        "geographic_coverage": topic["geo"],
        "sources": {
            "primary": [source_ref(s) for s in primary],
            "backup": [source_ref(s) for s in backup],
            "primary_count": len(primary),
            "backup_count": len(backup),
            "independent_source_coverage": len(set(all_sources)) >= 2,
        },
        "ranking_method": {
            "id": method["id"],
            "name": method["name"],
            "question": question,
            "metric": topic["metric"],
            "basis": method["basis"],
            "subjectivity": method["subjectivity"],
            "human_verification_required": method["human_verification_required"],
        },
        "update_frequency": topic["frequency"],
        "data_availability": topic["availability"],
        "research_status": status,
        "licensing_risk": source_risk(primary, backup),
        "notes": topic["caveats"],
        "schema_version": SCHEMA_VERSION,
    }


def topic_name_map() -> dict:
    return {f"{c['id']}.{t['slug']}": f"{c['name']} / {t['name']}" for c in CATEGORIES for t in c["topics"]}


def build_topics() -> tuple[list[dict], dict]:
    all_topics = []
    category_files = []
    for category in CATEGORIES:
        topics = [make_topic(category, topic, {}) for topic in category["topics"]]
        all_topics.extend(topics)
        counts = Counter(t["research_status"] for t in topics)
        availability = Counter(t["data_availability"] for t in topics)
        category_record = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": NOW,
            "category": {
                "id": category["id"],
                "name": category["name"],
                "description": category["description"],
                "topic_count": len(topics),
                "subcategory_count": sum(len(t["subcategories"]) for t in topics),
                "research_status_counts": dict(counts),
                "data_availability_counts": dict(availability),
            },
            "topics": topics,
        }
        category_files.append(category_record)
    return category_files, all_topics


def enrich_sources(all_topics: list[dict]) -> list[dict]:
    primary_for = defaultdict(list)
    backup_for = defaultdict(list)
    for t in all_topics:
        for s in t["sources"]["primary"]:
            primary_for[s["id"]].append(t["id"])
        for s in t["sources"]["backup"]:
            backup_for[s["id"]].append(t["id"])

    enriched = []
    for s in SOURCES:
        s = json.loads(json.dumps(s))  # defensive copy
        test_url = s.pop("test_url", None)
        v = VERIFICATION.get(s["id"])
        if v:
            s["operational"] = v.get("result") in {"ok", "auth_required", "forbidden", "rate_limited"}
            s["verification"] = {
                "last_checked": v.get("checked_at"),
                "method": v.get("method", "live_http_get"),
                "test_scope": ("website_or_docs" if test_url in {s["official_url"], s.get("api_docs_url")} else "endpoint"),
                "http_status": v.get("http_status"),
                "result": v.get("result"),
                "final_url": v.get("final_url"),
                "elapsed_ms": v.get("elapsed_ms"),
                "notes": v.get("notes", ""),
            }
        s["verification"]["test_url"] = test_url
        s["usage"] = {
            "primary_for_topics": primary_for.get(s["id"], []),
            "backup_for_topics": backup_for.get(s["id"], []),
            "primary_for_count": len(primary_for.get(s["id"], [])),
            "backup_for_count": len(backup_for.get(s["id"], [])),
        }
        s["reference_only"] = s.get("reference_only", False)
        enriched.append(s)
    return enriched


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build() -> None:
    category_files, all_topics = build_topics()

    for record in category_files:
        write_json(ROOT / "topics" / f"{record['category']['id']}.json", record)

    status_counts = Counter(t["research_status"] for t in all_topics)
    availability_counts = Counter(t["data_availability"] for t in all_topics)
    frequency_counts = Counter(t["update_frequency"] for t in all_topics)
    license_risk_counts = Counter(t["licensing_risk"] for t in all_topics)
    method_counts = Counter(t["ranking_method"]["id"] for t in all_topics)

    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "total_categories": len(category_files),
        "total_topics": len(all_topics),
        "total_subcategories": sum(t["subcategory_count"] for t in all_topics),
        "research_status_counts": dict(status_counts),
        "data_availability_counts": dict(availability_counts),
        "licensing_risk_counts": dict(license_risk_counts),
        "update_frequency_counts": dict(frequency_counts),
        "method_counts": dict(method_counts),
        "categories": [
            {
                "id": r["category"]["id"],
                "name": r["category"]["name"],
                "file": f"topics/{r['category']['id']}.json",
                "topic_count": r["category"]["topic_count"],
                "subcategory_count": r["category"]["subcategory_count"],
                "research_status_counts": r["category"]["research_status_counts"],
                "data_availability_counts": r["category"]["data_availability_counts"],
            }
            for r in category_files
        ],
    }
    write_json(ROOT / "topics" / "index.json", index)

    sources = enrich_sources(all_topics)
    source_status_counts = Counter(s["verification"]["result"] for s in sources)
    access_counts = Counter(s["access"]["model"] for s in sources)
    commercial_counts = Counter(s["license"]["commercial_use"] for s in sources)
    source_directory = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "description": "Verified and curated free/restricted data sources for Top 10 Everything.",
        "source_count": len(sources),
        "access_model_counts": dict(access_counts),
        "commercial_use_counts": dict(commercial_counts),
        "verification_result_counts": dict(source_status_counts),
        "sources": sorted(sources, key=lambda x: x["id"]),
    }
    write_json(ROOT / "sources" / "source-directory.json", source_directory)

    status = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "method": "Representative unauthenticated HTTP GET with a descriptive User-Agent and a 25s timeout. A 401/403 means the endpoint responded but requires credentials or blocked the request; it does not prove the API is offline. For some providers the test URL is the official website or documentation page, so the check proves provider reachability rather than endpoint correctness.",
        "summary": {
            "checked": sum(1 for s in sources if s["verification"]["result"] != "not_checked"),
            "not_checked": sum(1 for s in sources if s["verification"]["result"] == "not_checked"),
            "by_result": dict(source_status_counts),
        },
        "checks": [
            {
                "source_id": s["id"],
                "name": s["name"],
                "official_url": s["official_url"],
                "test_url": s["verification"].get("test_url"),
                "http_status": s["verification"]["http_status"],
                "result": s["verification"]["result"],
                "operational": s["operational"],
                "last_checked": s["verification"]["last_checked"],
                "notes": s["verification"]["notes"],
            }
            for s in sources
        ],
    }
    write_json(ROOT / "sources" / "source-status.json", status)

    license_groups = defaultdict(list)
    for s in sources:
        lic = s["license"]
        key = lic["name"] or "Not verified / varies by dataset"
        license_groups[key].append({
            "source_id": s["id"],
            "name": s["name"],
            "commercial_use": lic["commercial_use"],
            "attribution_required": lic["attribution_required"],
            "share_alike": lic["share_alike"],
            "url": lic["url"],
        })
    licensing = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "warning": "This is a research aid, not legal advice. Licences change and dataset-level terms can differ from the provider-level licence. Re-check before commercial publication.",
        "commercial_use_summary": dict(commercial_counts),
        "license_groups": [
            {"license": name, "source_count": len(items), "sources": items}
            for name, items in sorted(license_groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
        "high_risk_sources": [
            {
                "id": s["id"], "name": s["name"],
                "reason": s["license"]["commercial_use"],
                "caveats": s["caveats"],
            }
            for s in sources
            if s["license"]["commercial_use"] in {"prohibited", "unclear", "varies"}
        ],
    }
    write_json(ROOT / "sources" / "licensing.json", licensing)

    method_usage = defaultdict(list)
    for t in all_topics:
        method_usage[t["ranking_method"]["id"]].append(t["id"])
    methods_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "method_count": len(METHODS),
        "methods": [
            {**m, "usage_count": len(method_usage.get(m["id"], [])),
             "example_topic_ids": method_usage.get(m["id"], [])[:8]}
            for m in METHODS
        ],
    }
    write_json(ROOT / "ranking-methods" / "methods.json", methods_payload)

    assignments = []
    for category in CATEGORIES:
        cat_topics = [t for t in all_topics if t["parent_id"] == category["id"]]
        cat_method_counts = Counter(t["ranking_method"]["id"] for t in cat_topics)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": NOW,
            "category": category["id"],
            "category_name": category["name"],
            "topic_count": len(cat_topics),
            "method_counts": dict(cat_method_counts),
            "assignments": [
                {
                    "topic_id": t["id"],
                    "topic_name": t["name"],
                    "method_id": t["ranking_method"]["id"],
                    "method_name": t["ranking_method"]["name"],
                    "metric": t["ranking_method"]["metric"],
                    "question": t["ranking_method"]["question"],
                    "basis": t["ranking_method"]["basis"],
                    "subjectivity": t["ranking_method"]["subjectivity"],
                    "human_verification_required": t["ranking_method"]["human_verification_required"],
                    "data_availability": t["data_availability"],
                    "update_frequency": t["update_frequency"],
                    "primary_sources": [s["id"] for s in t["sources"]["primary"]],
                    "backup_sources": [s["id"] for s in t["sources"]["backup"]],
                }
                for t in cat_topics
            ],
        }
        assignments.append(payload)
        write_json(ROOT / "ranking-methods" / f"{category['id']}.json", payload)

    write_json(ROOT / "ranking-methods" / "assignments.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "topic_count": len(assignments),
        "categories": assignments,
    })

    progress = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "summary": index,
        "source_summary": {
            "total_sources": len(sources),
            "access_models": dict(access_counts),
            "commercial_use": dict(commercial_counts),
            "verification": dict(source_status_counts),
            "verified_operational": sum(1 for s in sources if s["operational"] is True),
        },
        "coverage_by_category": [
            {
                "category": r["category"]["id"],
                "name": r["category"]["name"],
                "topics": r["category"]["topic_count"],
                "status": r["category"]["research_status_counts"],
                "availability": r["category"]["data_availability_counts"],
            }
            for r in category_files
        ],
        "next_priorities": [
            "Verify every source's licence at dataset level before commercial use, especially WHO GHO, GBIF, OpenAQ, IUCN and Open-Meteo.",
            "Replace attention proxies for consumer hardware with licensed sales data or explicitly label rankings as popularity proxies.",
            "Add open sources for patents (PatentsView/EPO), paleobiology, NCBI genomes, UniProt/PDB and national statistics portals.",
            "Expand country-specific rankings for India, Brazil, Nigeria, Indonesia and other large markets currently underrepresented.",
            "Build an ingestion proof of concept for the strongest 25 topics (World Bank, OpenAlex, USGS, GBIF, OpenAlex, TMDB, MusicBrainz, Open Food Facts).",
            "Add a licence review workflow with a named reviewer and dated evidence for every restricted source.",
        ],
    }
    write_json(ROOT / "reports" / "research-progress.json", progress)

    unsupported = [t for t in all_topics if t["research_status"] == "unsupported"]
    write_json(ROOT / "reports" / "unsupported-topics.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "count": len(unsupported),
        "explanation": "These topics are valid product ideas but cannot be supported responsibly with the free data identified so far. They need human review, a licensed dataset, or a different ranking question.",
        "topics": [
            {
                "topic_id": t["id"],
                "topic_name": t["name"],
                "category": t["parent_name"],
                "reason": t["ranking_method"]["metric"],
                "notes": t["notes"],
                "recommended_path": "Commission a documented human-review process or license an authoritative ranking dataset. Do not publish an automated ranking from incomplete data.",
                "last_reviewed": NOW[:10],
            }
            for t in unsupported
        ],
    })

    gaps = [t for t in all_topics if t["research_status"] in {"partial", "researched_proxy"}]
    write_json(ROOT / "reports" / "coverage-gaps.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "count": len(gaps),
        "explanation": "Topics in this list have workable sources, but the ranking is either incomplete or based on a proxy. Treat them as candidates for deeper source work, not as finished products.",
        "by_category": dict(Counter(t["parent_id"] for t in gaps)),
        "topics": [
            {
                "topic_id": t["id"],
                "topic_name": t["name"],
                "category": t["parent_name"],
                "data_availability": t["data_availability"],
                "research_status": t["research_status"],
                "method": t["ranking_method"]["id"],
                "metric": t["ranking_method"]["metric"],
                "licensing_risk": t["licensing_risk"],
            }
            for t in gaps
        ],
    })

    unused = [
        {
            "source_id": s["id"],
            "name": s["name"],
            "access_model": s["access"]["model"],
            "commercial_use": s["license"]["commercial_use"],
            "data_types": s["data_types"],
        }
        for s in sources
        if not s["usage"]["primary_for_count"] and not s["usage"]["backup_for_count"]
    ]
    write_json(ROOT / "reports" / "unused-sources.json", {
        "schema_version": SCHEMA_VERSION,
        "generated_at": NOW,
        "count": len(unused),
        "explanation": "Catalogued sources that no topic currently references. They are kept because they are useful alternates for future topics or replacements for restricted sources. Map them to a topic (as primary or backup) or remove them.",
        "sources": unused,
    })

    print(f"Built {len(category_files)} category files, {len(all_topics)} topics and {len(sources)} sources.")
    print(f"Status: {dict(status_counts)}")
    print(f"Availability: {dict(availability_counts)}")


if __name__ == "__main__":
    build()
