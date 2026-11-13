"""Ranking specifications and the ranking builder.

A spec binds a catalog topic to a real adapter. The catalog remains the source
of truth for the question, metric and method; this module only decides which
dataset answers it and how the output is shaped.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adapters import ADAPTERS
from .methods import METHOD_LIMITATIONS, select_top

ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = ROOT / "topics"
SOURCES_FILE = ROOT / "sources" / "source-directory.json"
OUT_DIR = ROOT / "rankings"
SCHEMA_VERSION = "1.0.0"

REFRESH_DAYS = {
    "event": 30,
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "yearly": 365,
}

# topic_id -> adapter key. Every entry was chosen because the provider is
# key-free (or has a documented free tier) and the dataset answers the exact
# question in the catalog.
SPECS: dict[str, str] = {
    "arts-literature.books": "openlibrary_fiction",
    "business-finance.cryptocurrencies": "coingecko_market_cap",
    "business-finance.economies": "worldbank_gdp",
    "education.education-systems": "owid_education_spending",
    "education.literacy-rates": "worldbank_literacy",
    "education.research-institutions": "openalex_institutions",
    "entertainment.radio-stations": "radio_browser",
    "environment-nature.air-quality": "owid_pm25",
    "environment-nature.carbon-emitters": "owid_co2",
    "environment-nature.forests": "owid_forest_share",
    "environment-nature.renewable-energy": "owid_renewable_share",
    "health-lifestyle.health-systems": "worldbank_health_expenditure",
    "health-lifestyle.longevity": "worldbank_life_expectancy",
    "health-lifestyle.public-health": "owid_water_access",
    "science.asteroids": "jpl_asteroids",
    "science.earthquake-monitoring": "usgs_earthquakes",
    "science.exoplanets": "nasa_exoplanets",
    "science.research-papers": "openalex_papers",
    "science.scientific-journals": "openalex_journals",
    "society-politics.aging": "worldbank_age_65_share",
    "society-politics.democracies": "owid_democracy",
    "society-politics.development": "owid_hdi",
    "society-politics.immigration": "worldbank_net_migration",
    "society-politics.inequality": "worldbank_gini",
    "society-politics.poverty": "worldbank_poverty",
    "society-politics.youth": "worldbank_youth_share",
    "sports.chess": "lichess_classical",
    "sports.formula-1": "jolpica_f1",
    "travel.countries": "worldbank_population",
}


def load_topics() -> dict[str, dict]:
    topics: dict[str, dict] = {}
    for path in sorted(TOPICS_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for topic in payload.get("topics", []):
            topics[topic["id"]] = topic
    return topics


def load_sources() -> dict[str, dict]:
    payload = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return {source["id"]: source for source in payload.get("sources", [])}


def source_block(source_ids: list[str], sources: dict[str, dict]) -> list[dict]:
    block = []
    for source_id in source_ids:
        source = sources.get(source_id)
        if not source:
            block.append({"id": source_id, "name": None, "known": False})
            continue
        block.append(
            {
                "id": source_id,
                "name": source["name"],
                "official_url": source["official_url"],
                "api_docs_url": source.get("api_docs_url"),
                "commercial_use": source["license"]["commercial_use"],
                "attribution_required": source["license"]["attribution_required"],
                "verification_result": source.get("verification", {}).get("result"),
                "last_checked": source.get("verification", {}).get("last_checked"),
            }
        )
    return block


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_ranking(
    topic_id: str,
    *,
    topics: dict[str, dict],
    sources: dict[str, dict],
    offline: bool = False,
    refresh: bool = False,
    top_n: int = 10,
    now: str | None = None,
) -> dict:
    if topic_id not in SPECS:
        raise KeyError(f"no ingestion spec for topic {topic_id!r}")
    if topic_id not in topics:
        raise KeyError(f"topic {topic_id!r} is not in the catalog")

    topic = topics[topic_id]
    adapter = ADAPTERS[SPECS[topic_id]]
    dataset = adapter(offline=offline, refresh=refresh)

    ranked, missing, diagnostics = select_top(dataset.records, top_n=top_n)
    if not ranked:
        raise ValueError(f"{topic_id}: adapter returned no rankable values")

    catalog_method = topic["ranking_method"]["id"]
    generated_at = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    caveats = dedupe(
        list(topic.get("notes", []))
        + METHOD_LIMITATIONS.get(catalog_method, [])
        + list(dataset.notes)
    )

    rows = []
    for entry in ranked:
        record = entry.record
        row = {
            "rank": entry.rank,
            "entity_id": record.get("id"),
            "name": record.get("name"),
            "value": record.get("value"),
            "unit": record.get("unit") or dataset.unit,
        }
        if record.get("period"):
            row["period"] = record["period"]
        extra = {k: v for k, v in (record.get("extra") or {}).items() if v is not None}
        if extra:
            row["extra"] = extra
        rows.append(row)

    frequency = topic.get("update_frequency", "yearly")
    refresh_after = (
        datetime.fromisoformat(generated_at) + timedelta(days=REFRESH_DAYS.get(frequency, 365))
    ).date().isoformat()

    return {
        "schema_version": SCHEMA_VERSION,
        "topic_id": topic_id,
        "topic_name": topic["name"],
        "category": topic["parent_id"],
        "question": topic["ranking_method"]["question"],
        "metric": topic["ranking_method"]["metric"],
        "method": {
            "id": catalog_method,
            "name": topic["ranking_method"]["name"],
            "subjectivity": topic["ranking_method"]["subjectivity"],
            "matches_catalog_method": True,
        },
        "measure": {
            "label": dataset.measure or topic["ranking_method"]["metric"],
            "unit": dataset.unit,
            "provider_last_updated": dataset.provider_updated,
        },
        "generated_at": generated_at,
        "refresh_after": refresh_after,
        "snapshot": {
            "retrieved_at": dataset.retrieved_at,
            "reference_period": rows[0].get("period") if rows else None,
            "records_considered": diagnostics["records_in"],
            "records_ranked": diagnostics["records_ranked"],
            "records_missing_value": diagnostics["records_missing_value"],
            "tied_at_cut": diagnostics["tied_at_cut"],
            **dataset.snapshot,
        },
        "sources": source_block(dataset.source_ids, sources),
        "ranking": rows,
        "caveats": caveats,
        "licensing_risk": topic.get("licensing_risk"),
        "data_availability": topic.get("data_availability"),
        "research_status": topic.get("research_status"),
    }


def write_ranking(payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{payload['topic_id']}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_index() -> Path | None:
    """Rebuild rankings/index.json from every ranking file on disk.

    Scanning the directory (rather than only the current run) keeps the index
    correct after a single-topic rebuild.
    """
    files = sorted(path for path in OUT_DIR.glob("*.json") if path.name != "index.json")
    if not files:
        return None
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": max((p["generated_at"] for p in payloads), default=None),
        "count": len(payloads),
        "description": "Worked rankings produced by pipeline/run.py from the catalogued sources and methods.",
        "rankings": [
            {
                "topic_id": p["topic_id"],
                "topic_name": p["topic_name"],
                "category": p["category"],
                "method": p["method"]["id"],
                "file": f"rankings/{p['topic_id']}.json",
                "generated_at": p["generated_at"],
                "refresh_after": p["refresh_after"],
                "leader": p["ranking"][0]["name"] if p["ranking"] else None,
                "item_count": len(p["ranking"]),
                "records_considered": p["snapshot"]["records_considered"],
            }
            for p in sorted(payloads, key=lambda x: x["topic_id"])
        ],
    }
    path = OUT_DIR / "index.json"
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
