"""Dataset adapters: fetch a real dataset, emit comparable records.

Each adapter returns a Dataset whose records share one numeric `value`, one
`unit` and one `period`. Parsers are pure functions over response text so they
can be tested offline against small fixtures.

Nothing here invents data. Where a provider returns nothing usable, the adapter
raises and the ranking is skipped rather than filled with a guess.
"""

from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import dataclass, field
from urllib.parse import quote

from .fetch import FetchError, fetch_text

WB = "https://api.worldbank.org/v2"
OWID = "https://ourworldindata.org/grapher"
NASA_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
JPL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
OPENALEX = "https://api.openalex.org"
COINGECKO = "https://api.coingecko.com/api/v3"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
RADIO = "https://de1.api.radio-browser.info/json/stations/topclick"


@dataclass
class Dataset:
    records: list[dict]
    source_ids: list[str]
    urls: list[str]
    notes: list[str] = field(default_factory=list)
    retrieved_at: str | None = None
    snapshot: dict = field(default_factory=dict)
    unit: str = ""
    measure: str = ""
    provider_updated: str | None = None


def _fetch(url: str, *, offline: bool, refresh: bool) -> tuple[str, dict]:
    return fetch_text(url, offline=offline, refresh=refresh, max_age_hours=12)


# --------------------------------------------------------------------- parser


def parse_worldbank_countries(text: str) -> set[str]:
    """Return ISO3 codes for real countries (aggregates have no region)."""
    payload = json.loads(text)
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    valid: set[str] = set()
    for row in rows:
        iso3 = row.get("id")
        region = (row.get("region") or {}).get("value", "")
        if iso3 and len(iso3) == 3 and region and region != "Aggregates":
            valid.add(iso3)
    return valid


def worldbank_last_updated(text: str) -> str | None:
    payload = json.loads(text)
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0].get("lastupdated")
    return None


def parse_worldbank_indicator(text: str, valid_iso3: set[str]) -> list[dict]:
    payload = json.loads(text)
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    records = []
    for row in rows:
        iso3 = row.get("countryiso3code") or ""
        value = row.get("value")
        if iso3 not in valid_iso3 or value is None:
            continue
        records.append(
            {
                "id": iso3,
                "name": (row.get("country") or {}).get("value", iso3),
                "value": value,
                "unit": row.get("unit") or "",
                "period": row.get("date", ""),
                "extra": {"indicator": (row.get("indicator") or {}).get("id", "")},
            }
        )
    return records


def parse_owid_csv(text: str, value_column: str) -> tuple[list[dict], int]:
    """Return (records for the latest usable year, that year)."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or value_column not in reader.fieldnames:
        raise ValueError(f"OWID csv missing column {value_column!r}")
    rows = []
    for row in reader:
        code = (row.get("code") or "").strip()
        if len(code) != 3 or not code.isalpha() or not code.isupper():
            continue  # drop aggregates and regions
        try:
            year = int(row["year"])
            value = float(row[value_column])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"id": code, "name": row["entity"], "year": year, "value": value})
    if not rows:
        return [], 0
    years = sorted({r["year"] for r in rows}, reverse=True)
    reference_year = 0
    for year in years:
        if sum(1 for r in rows if r["year"] == year) >= 50:
            reference_year = year
            break
    if not reference_year:
        reference_year = years[0]
    records = []
    for row in rows:
        if row["year"] != reference_year:
            continue
        records.append(
            {
                "id": row["id"],
                "name": row["name"],
                "value": row["value"],
                "unit": "",
                "period": str(row["year"]),
                "extra": {},
            }
        )
    return records, reference_year


def parse_exoplanets(text: str) -> list[dict]:
    rows = json.loads(text)
    records = []
    for row in rows:
        mass = row.get("pl_bmasse")
        if mass is None:
            continue
        name = row.get("pl_name") or ""
        records.append(
            {
                "id": name,
                "name": name,
                "value": mass,
                "unit": "Earth masses",
                "period": str(row.get("disc_year") or ""),
                "extra": {
                    "radius_earth": row.get("pl_rade"),
                    "discovery_year": row.get("disc_year"),
                },
            }
        )
    return records


def parse_asteroids(text: str, allowed_classes: set[str] | None = None) -> list[dict]:
    payload = json.loads(text)
    fields = payload.get("fields", [])
    rows = payload.get("data", [])
    index = {name: i for i, name in enumerate(fields)}
    records = []
    for row in rows:
        diameter = row[index["diameter"]] if "diameter" in index else None
        if diameter is None:
            continue
        try:
            value = float(diameter)
        except (TypeError, ValueError):
            continue
        name = (row[index.get("full_name", 0)] or "").strip()
        klass = row[index["class"]] if "class" in index else None
        if allowed_classes is not None and klass not in allowed_classes:
            continue
        records.append(
            {
                "id": name,
                "name": name,
                "value": value,
                "unit": "km",
                "period": "",
                "extra": {"class": klass},
            }
        )
    return records


def parse_openalex(text: str, allowed_types: set[str] | None = None) -> list[dict]:
    payload = json.loads(text)
    rows = payload.get("results", [])
    records = []
    for row in rows:
        if allowed_types is not None and row.get("type") not in allowed_types:
            continue
        value = row.get("cited_by_count")
        if value is None:
            continue
        records.append(
            {
                "id": row.get("id", ""),
                "name": row.get("display_name", ""),
                "value": value,
                "unit": "citations (OpenAlex, all time)",
                "period": "",
                "extra": {
                    "works_count": row.get("works_count"),
                    "country_code": row.get("country_code"),
                    "type": row.get("type"),
                    "issn_l": row.get("issn_l"),
                },
            }
        )
    return records


def parse_openalex_journals(text: str, min_works: int = 2000) -> list[dict]:
    """Citations per published work, to stop size masquerading as impact.

    Raw all-time citations put whichever journal has published the most behind
    the leader. Dividing by works_count answers a comparable question: how often
    does a typical paper in this journal get cited.

    Journals with implausibly small output are excluded, because a handful of
    papers can produce a meaningless ratio. The ratio is only computed inside
    the candidate set of the most-cited journals, not across all of OpenAlex.
    """
    payload = json.loads(text)
    rows = payload.get("results", [])
    records = []
    for row in rows:
        if row.get("type") != "journal":
            continue
        works = row.get("works_count")
        citations = row.get("cited_by_count")
        if not works or citations is None:
            continue
        try:
            works = int(works)
            citations = float(citations)
        except (TypeError, ValueError):
            continue
        if works < min_works:
            continue
        if citations < 0:
            continue
        records.append(
            {
                "id": row.get("id", ""),
                "name": row.get("display_name", ""),
                "value": citations / works,
                "unit": "citations per published work (OpenAlex, all time)",
                "period": "",
                "extra": {
                    "works_count": works,
                    "cited_by_count": int(citations),
                    "issn_l": row.get("issn_l"),
                    "type": row.get("type"),
                },
            }
        )
    return records


def parse_coingecko(text: str) -> list[dict]:
    rows = json.loads(text)
    records = []
    for row in rows:
        market_cap = row.get("market_cap")
        if market_cap is None:
            continue
        records.append(
            {
                "id": row.get("id", ""),
                "name": row.get("name", ""),
                "value": market_cap,
                "unit": "USD market capitalisation",
                "period": "",
                "extra": {
                    "symbol": row.get("symbol"),
                    "price_usd": row.get("current_price"),
                    "provider_rank": row.get("market_cap_rank"),
                },
            }
        )
    return records


def parse_usgs(text: str) -> list[dict]:
    payload = json.loads(text)
    records = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        magnitude = props.get("mag")
        if magnitude is None:
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None, None]
        records.append(
            {
                "id": feature.get("id", ""),
                "name": props.get("place") or feature.get("id", ""),
                "value": magnitude,
                "unit": "moment magnitude (Mw)",
                "period": str(props.get("time", "")),
                "extra": {
                    "time_utc": props.get("time"),
                    "depth_km": coords[2] if len(coords) > 2 else None,
                    "tsunami": props.get("tsunami"),
                },
            }
        )
    return records


def parse_radio(text: str) -> list[dict]:
    rows = json.loads(text)
    records = []
    for row in rows:
        clicks = row.get("clickcount")
        if clicks in (None, 0):
            continue
        records.append(
            {
                "id": row.get("stationuuid", ""),
                "name": html.unescape(row.get("name") or ""),
                "value": clicks,
                "unit": "clicks (Radio Browser, all time)",
                "period": "",
                "extra": {
                    "country": row.get("country"),
                    "tags": (row.get("tags") or "")[:120],
                    "codec": row.get("codec"),
                },
            }
        )
    return records


# -------------------------------------------------------------------- fetchers


def worldbank_indicator(indicator: str, unit: str, measure: str) -> "callable":
    """Build a World Bank adapter for one indicator."""

    def run(*, offline: bool, refresh: bool) -> Dataset:
        countries_url = f"{WB}/country?format=json&per_page=400"
        data_url = f"{WB}/country/all/indicator/{indicator}?format=json&per_page=400&mrnev=1"
        countries_text, countries_meta = _fetch(countries_url, offline=offline, refresh=refresh)
        data_text, data_meta = _fetch(data_url, offline=offline, refresh=refresh)
        valid = parse_worldbank_countries(countries_text)
        if not valid:
            raise FetchError(f"World Bank country list returned no valid countries for {indicator}")
        records = parse_worldbank_indicator(data_text, valid)
        for record in records:
            record["unit"] = unit
        return Dataset(
            records=records,
            source_ids=["world_bank"],
            urls=[countries_url, data_url],
            notes=[
                "The World Bank reports the most recent non-empty value per country, so reference years differ slightly between countries.",
                "Aggregates (regions, income groups) are removed using the World Bank country metadata.",
            ],
            retrieved_at=data_meta.get("retrieved_at"),
            snapshot={"indicator": indicator},
            unit=unit,
            measure=measure,
            provider_updated=worldbank_last_updated(data_text),
        )

    return run


def _owid(slug: str, column: str, unit: str, measure: str, notes: list[str]) -> "callable":
    def run(*, offline: bool, refresh: bool) -> Dataset:
        url = f"{OWID}/{slug}.csv?v=1&csvType=full&useColumnShortNames=true"
        text, meta = _fetch(url, offline=offline, refresh=refresh)
        records, year = parse_owid_csv(text, column)
        for record in records:
            record["unit"] = unit
            record["period"] = str(year)
        if not records:
            raise FetchError(f"OWID dataset {slug} returned no usable country rows")
        return Dataset(
            records=records,
            source_ids=["our_world_in_data"],
            urls=[url],
            notes=[
                f"Single reference year ({year}) selected as the latest year with at least 50 country rows.",
                *notes,
            ],
            retrieved_at=meta.get("retrieved_at"),
            snapshot={"reference_year": year, "grapher_slug": slug},
            unit=unit,
            measure=measure,
        )

    return run


def exoplanets(*, offline: bool, refresh: bool) -> Dataset:
    query = (
        "select+top+50+pl_name,pl_bmasse,pl_rade,disc_year+from+ps+"
        "where+default_flag=1+and+pl_bmasse+is+not+null+order+by+pl_bmasse+desc"
    )
    url = f"{NASA_TAP}?query={query}&format=json"
    text, meta = _fetch(url, offline=offline, refresh=refresh)
    records = parse_exoplanets(text)
    return Dataset(
        records=records,
        source_ids=["nasa_exoplanet"],
        urls=[url],
        notes=[
            "Uses the confirmed-planet table (default_flag=1) and the archive's mass estimate; some masses are minimum masses (M sin i).",
            "Mass is not a quality measure; a 'most massive planet' list is a physical-property ranking.",
        ],
        retrieved_at=meta.get("retrieved_at"),
        snapshot={"query": "ps where default_flag=1 order by pl_bmasse desc"},
        unit="Earth masses",
        measure="Planet mass (Earth masses, archive estimate)",
    )


def asteroids(*, offline: bool, refresh: bool) -> Dataset:
    # Constrain by diameter rather than taking an arbitrary slice, so the
    # largest objects cannot be missing from the candidate set.
    constraint = quote(json.dumps({"AND": ["diameter|GE|50"]}))
    url = f"{JPL}?fields=full_name,diameter,class&sb-kind=a&sb-cdata={constraint}&limit=1000"
    text, meta = _fetch(url, offline=offline, refresh=refresh)
    # Main-belt classes only: without this, distant centaurs and TNOs such as
    # Varuna appear in an "asteroid size" list and dominate it.
    records = parse_asteroids(text, allowed_classes={"MBA", "IMB", "OMB"})
    return Dataset(
        records=records,
        source_ids=["jpl_sbdb"],
        urls=[url],
        notes=[
            "Candidate set is every main-belt asteroid (MBA/IMB/OMB) in the JPL Small-Body Database with an estimated diameter of at least 50 km.",
            "Diameter is an estimated effective diameter; values come from IRAS, WISE/NEOWISE and similar surveys.",
        ],
        retrieved_at=meta.get("retrieved_at"),
        snapshot={"catalogue": "JPL Small-Body Database, main-belt asteroids with diameter >= 50 km"},
        unit="km",
        measure="Estimated effective diameter",
    )


def openalex_institutions(*, offline: bool, refresh: bool) -> Dataset:
    url = (
        f"{OPENALEX}/institutions?per_page=100&sort=cited_by_count:desc"
        "&select=id,display_name,works_count,cited_by_count,country_code,type"
    )
    text, meta = _fetch(url, offline=offline, refresh=refresh)
    records = parse_openalex(text, allowed_types={"education", "facility", "government", "company"})
    return Dataset(
        records=records,
        source_ids=["openalex"],
        urls=[url],
        notes=[
            "OpenAlex mixes universities, hospitals, government labs and corporate research groups; the type is kept per record.",
            "All-time citation counts are not field- or age-normalised.",
        ],
        retrieved_at=meta.get("retrieved_at"),
        snapshot={"provider": "OpenAlex institutions, sorted by cited_by_count"},
        unit="citations (OpenAlex, all time)",
        measure="All-time citations to works affiliated with the institution",
    )


def openalex_journals(*, offline: bool, refresh: bool) -> Dataset:
    # 200 candidates by all-time citations. Per-work citations are then computed
    # inside that candidate set, so the ratio is honest about its own bounds.
    url = (
        f"{OPENALEX}/sources?per_page=200&sort=cited_by_count:desc"
        "&select=id,display_name,works_count,cited_by_count,issn_l,type"
        "&filter=type:journal"
    )
    text, meta = _fetch(url, offline=offline, refresh=refresh)
    records = parse_openalex_journals(text, min_works=2000)
    return Dataset(
        records=records,
        source_ids=["openalex"],
        urls=[url],
        notes=[
            "Measured as all-time citations divided by works published, which stops the largest journals from winning on volume alone.",
            "The candidate set is the 200 journals with the most all-time citations in OpenAlex, so a small, highly cited journal outside that set is not considered.",
            "Journals with fewer than 2,000 published works are excluded, because a handful of papers can produce a meaningless ratio.",
            "OpenAlex source types and citation coverage are not complete for every region, and per-work ratios are not field-normalised.",
        ],
        retrieved_at=meta.get("retrieved_at"),
        snapshot={
            "provider": "OpenAlex sources filtered to type=journal",
            "candidate_set": "top 200 journals by all-time citations",
            "minimum_works": 2000,
        },
        unit="citations per published work (OpenAlex, all time)",
        measure="All-time citations per published work",
    )


def cryptocurrencies(*, offline: bool, refresh: bool) -> Dataset:
    url = f"{COINGECKO}/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
    text, meta = _fetch(url, offline=offline, refresh=refresh)
    records = parse_coingecko(text)
    return Dataset(
        records=records,
        source_ids=["coingecko"],
        urls=[url],
        notes=[
            "Market capitalisation is circulating supply times price and changes continuously.",
            "The free CoinGecko API requires attribution and is rate-limited; check the current terms before commercial use.",
        ],
        retrieved_at=meta.get("retrieved_at"),
        snapshot={"provider": "CoinGecko /coins/markets, order=market_cap_desc"},
        unit="USD market capitalisation",
        measure="Market capitalisation (circulating supply x price)",
    )


def earthquakes(*, offline: bool, refresh: bool) -> Dataset:
    # USGS returns 403 for sorted queries, so we fetch and sort locally.
    url = f"{USGS}?format=geojson&minmagnitude=8&starttime=1900-01-01&limit=200"
    text, meta = _fetch(url, offline=offline, refresh=refresh)
    records = parse_usgs(text)
    return Dataset(
        records=records,
        source_ids=["usgs_earthquake"],
        urls=[url],
        notes=[
            "Includes catalogued events of magnitude 8.0 and above; the catalogue is not complete before the 20th century.",
            "Magnitude is a physical measure of energy release, not of human impact.",
        ],
        retrieved_at=meta.get("retrieved_at"),
        snapshot={"query": "USGS FDSN minmagnitude=8 since 1900-01-01, limit=200"},
        unit="moment magnitude (Mw)",
        measure="Moment magnitude of catalogued events",
    )


def radio_stations(*, offline: bool, refresh: bool) -> Dataset:
    url = f"{RADIO}/50"
    text, meta = _fetch(url, offline=offline, refresh=refresh)
    records = parse_radio(text)
    return Dataset(
        records=records,
        source_ids=["radio_browser"],
        urls=[url],
        notes=[
            "Click counts are accumulated by the Radio Browser community and favour stations listed there for a long time.",
            "Station metadata is crowd-maintained and can contain duplicates or stale entries.",
        ],
        retrieved_at=meta.get("retrieved_at"),
        snapshot={"provider": "Radio Browser topclick, 50 stations"},
        unit="clicks (Radio Browser, all time)",
        measure="Cumulative station clicks recorded by Radio Browser",
    )


ADAPTERS = {
    "worldbank_gdp": worldbank_indicator(
        "NY.GDP.MKTP.CD", "current US$", "GDP at current market prices, current US$"
    ),
    "worldbank_life_expectancy": worldbank_indicator(
        "SP.DYN.LE00.IN", "years", "Life expectancy at birth, total population"
    ),
    "worldbank_age_65_share": worldbank_indicator(
        "SP.POP.65UP.TO.ZS", "share of population (%)", "Population aged 65 and above, % of total"
    ),
    "owid_co2": _owid(
        "annual-co2-emissions-per-country",
        "emissions_total",
        "tonnes CO2",
        "Annual territorial CO2 emissions",
        ["Territorial emissions only; consumption-based emissions give a different ranking."],
    ),
    "owid_renewable_share": _owid(
        "share-electricity-renewables",
        "renewable_share_of_electricity__pct",
        "% of electricity",
        "Renewable share of electricity generation",
        ["Share of generation, not total renewable capacity; small hydro-heavy grids rank high."],
    ),
    "nasa_exoplanets": exoplanets,
    "jpl_asteroids": asteroids,
    "openalex_institutions": openalex_institutions,
    "openalex_journals": openalex_journals,
    "coingecko_market_cap": cryptocurrencies,
    "usgs_earthquakes": earthquakes,
    "radio_browser": radio_stations,
}
