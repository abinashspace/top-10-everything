# Top 10 Everything — research catalog

A machine-readable map of what can honestly be ranked, with which free data, and how.

**[Browse the catalog →](https://abinashspace.github.io/top-10-everything/)** — searchable topics, sources,
methods and the twelve worked rankings, generated from the JSON in this repository.

This repository is **not** a collection of rankings. It is the research layer behind them: a
hierarchical topic taxonomy, a curated directory of data sources, a reusable library of ranking
methods, and an explicit record of where the data does not exist. It is designed to be served
straight from GitHub (raw JSON or GitHub Pages) and rebuilt with nothing but Python.

The guiding rule is simple: **never invent an API, a limit, a licence, or a ranking.** When
something is restricted, unverifiable or only available through a proprietary index, the catalog
says so and marks the topic as limited, proxy-based, or unsupported.

---

## What is in here

| Artifact | Path | What it contains |
| --- | --- | --- |
| Topic index | `topics/index.json` | Totals, per-category counts, status and availability distributions |
| Category files | `topics/<category>.json` | Every topic in that category with sources, method, cadence and caveats |
| Source directory | `sources/source-directory.json` | All sources with access, licence, limits, verification and topic usage |
| Verification results | `sources/source-status.json` | Last reachability check per source |
| Licence review | `sources/licensing.json` | Sources grouped by licence, plus a high-risk list |
| Method library | `ranking-methods/methods.json` | 20 reusable ranking methods with scoring rules |
| Method assignments | `ranking-methods/<category>.json` | Which method each topic uses, and the exact question it answers |
| Unsupported topics | `reports/unsupported-topics.json` | Topics that cannot be built responsibly from free data |
| Coverage gaps | `reports/coverage-gaps.json` | Partial and proxy topics that need deeper source work |
| Unused sources | `reports/unused-sources.json` | Catalogued sources not yet mapped to a topic |
| Progress summary | `reports/research-progress.json` | Coverage statistics and next priorities |
| Worked rankings | `rankings/index.json` | Twelve proven rankings with provenance, snapshots and caveats |
| Public site | `site/` | Generated catalog browser served by GitHub Pages |
| Ingestion pipeline | `pipeline/` | Fetch, cache, parse, rank, emit — with offline tests |
| Schemas | `schema/*.json` | JSON Schema (draft 2020-12) for topics, categories, sources and methods |
| Scripts | `scripts/*.py` | The editable source of truth and the build/verify/validate tooling |

### Current size

- **20 categories**, **530 topics**, **2,063 suggested subcategories**
- **143 sources**: 79 open, 34 free with an API key, 17 free tier, 5 free account, 6 restricted, 2 paid
- **19 methods in active use** (a 20th, `editorial`, documents the licensed-ranking path)
- **2,000+ source references** across primary and backup slots

Status distribution: `researched` 190, `researched_proxy` 35, `partial` 276, `unsupported` 29.

**Twelve topics are proven end to end.** They are not claims in a table: `pipeline/` fetches the
live dataset, applies the catalogued method, and writes a ranking with retrieved-at timestamps,
candidate-set size, missing-value counts, tie handling and the provider's licence terms. See
[`docs/ingestion.md`](docs/ingestion.md).

---

## The data model

### Topic

```json
{
  "id": "science.exoplanets",
  "name": "Exoplanets",
  "parent_id": "science",
  "subcategories": ["Confirmed", "Habitable zone", "Earth-sized", "Recent discoveries"],
  "geographic_coverage": ["global"],
  "sources": {
    "primary": [{ "id": "nasa_open", "name": "NASA Open APIs", "access_model": "free_key" }],
    "backup": [{ "id": "nasa_exoplanet", "name": "NASA Exoplanet Archive TAP", "access_model": "open" }],
    "independent_source_coverage": true
  },
  "ranking_method": {
    "id": "official_stat",
    "question": "Top 10 exoplanets for a chosen property (mass, radius, equilibrium temperature, distance or discovery year), using the NASA Exoplanet Archive confirmed-planet table with the query date stated.",
    "metric": "Mass, radius, orbital period, distance and discovery year from the NASA Exoplanet Archive",
    "subjectivity": "objective"
  },
  "update_frequency": "monthly",
  "data_availability": "strong",
  "research_status": "researched",
  "licensing_risk": "medium",
  "notes": []
}
```

Every topic answers three questions: *what exactly is being ranked*, *with what data*, and *how
often can it be refreshed*. The `metric` field states the measured quantity **and** the honest
caveat (for weak topics it reads like "…is commercial; use X as a proxy"), so a reader can see the
limitation without opening the notes.

### Source

Each source records the official URL, API docs, a representative test endpoint, access model,
authentication, free-tier limits, licence, commercial-use assessment, attribution and share-alike
flags, redistribution notes, bulk availability, update cadence, caveats, the last verification
result, and every topic that uses it as a primary or backup source.

### Method

A method is a reusable recipe: criteria, indicators, a prescriptive scoring rule, data
requirements, whether human verification is mandatory, and known limitations. A method says how a
ranking *must* be computed; it does not claim the data exists for every topic that references it.

---

## Vocabulary

`data_availability`

| Value | Meaning |
| --- | --- |
| `strong` | Official, comparable and ready for automated ingestion |
| `moderate` | Usable, with known coverage or comparability caveats |
| `limited` | Partial, fragmented, or only available through a proxy |
| `none` | No responsible free source identified |

`research_status`

| Value | Meaning |
| --- | --- |
| `researched` | A specific source and method are identified and viable |
| `researched_proxy` | Only attention/canonical proxies exist; the ranking measures attention, not quality |
| `partial` | Sources exist but meaningful gaps remain |
| `unsupported` | Valid product idea, but cannot be built from free data today |

`subjectivity` distinguishes `objective` measurements, `subjective` audience or expert judgement,
`mixed` composite indices, and `proxy` signals that stand in for something unmeasured.

---

## What the verification actually proves

`scripts/verify_sources.py` sends **one small unauthenticated GET request per source** with a
descriptive User-Agent, a 25-second timeout and a 64 KB read cap. Results are recorded as:

| Result | Meaning |
| --- | --- |
| `ok` | The URL returned 2xx |
| `auth_required` | The endpoint responded but needs credentials (401, or 400 on a known key-only API) |
| `forbidden` | The endpoint responded but refused the request (403: WAF or policy) |
| `rate_limited` | HTTP 429 |
| `http_error` | Any other 4xx/5xx, including moved endpoints |
| `network_error` | No HTTP response (DNS, TLS, timeout) |

**This is reachability, not legal clearance and not ingestion correctness.** A `200` on a
documentation page proves the provider exists, not that a specific dataset is usable. Some test
URLs deliberately point at official documentation when the real endpoint needs a key. The
`verification.test_scope` field says which one was checked.

Latest run: 107 `ok`, 16 `forbidden`, 14 `auth_required`, 3 `network_error`, 2 `rate_limited`,
1 `http_error`.

---

## Licensing: read this before publishing anything

The catalogue records what providers state, conservatively. It is **not legal advice**, and
dataset-level terms often differ from provider-level terms.

Known restrictions already captured in the catalog:

- **WHO GHO** is CC BY-NC-SA — commercial use prohibited.
- **Open-Meteo** free tier is non-commercial; commercial use needs a paid plan.
- **IMDb datasets** are non-commercial only.
- **Spotify, NewsAPI and The Guardian** free tiers restrict commercial use.
- **QS, THE, MICHELIN, Numbeo** are proprietary; they are catalogued for reference and
  methodology comparison, not for redistribution.
- **Transparency International CPI** is CC BY-ND: modified rankings may not be redistributed.
- **RSF and Freedom House** indices have their own reuse restrictions.
- **EM-DAT, IAEA PRIS, IHME GBD** have access terms that must be reviewed at dataset level.
- Many "open" sources contain **third-party data under different licences** (Our World in Data
  and Wikipedia are the obvious cases).

Re-check the provider's terms, the specific dataset's terms, and your jurisdiction's database
rights before commercial publication. `sources/licensing.json` lists every source whose
commercial status is `prohibited`, `unclear` or `varies`.

---

## Worked rankings (the proof)

The catalog is a plan. `rankings/` is the evidence that parts of the plan work.

| Topic | Provider | Method | Leader at last run |
| --- | --- | --- | --- |
| Economies | World Bank | official stat | United States |
| Longevity | World Bank | official stat | Monaco |
| Aging | World Bank | official stat | Monaco |
| Carbon emitters | Our World in Data | official stat | China |
| Renewable energy | Our World in Data (Ember) | official stat | Paraguay |
| Exoplanets | NASA Exoplanet Archive | official stat | 11 UMi b (most massive with an estimate) |
| Asteroids | JPL Small-Body Database | official stat | 1 Ceres |
| Research institutions | OpenAlex | bibliometric | CNRS |
| Scientific journals | OpenAlex | bibliometric | Chemical Reviews |
| Cryptocurrencies | CoinGecko | market cap | Bitcoin |
| Earthquake monitoring | USGS | official stat | 1960 Valdivia (Mw 9.5) |
| Radio stations | Radio Browser | community activity | RTL |

Each file records the exact question, the applied measure and unit, the retrieval timestamp, the
number of comparable records, how many were dropped for a missing value, whether rank 10 is tied,
every source with its licence status, and the limitations that travel with the method.

```bash
python -m pipeline.run --all                     # rebuild from cache
python -m pipeline.run --all --refresh           # re-fetch from providers
python -m pipeline.run --topic science.asteroids --top 25
python scripts/validate_rankings.py
python -m unittest discover -s pipeline/tests -t .   # 22 offline tests
```

Choosing these twelve was itself a finding: they are the topics where the catalog's `strong`
availability rating survived contact with a real endpoint. Where a provider needed a key, blocked
automated access, or returned data that could not answer the catalogued question, the topic was
left unbuilt rather than approximated.

## Rebuilding

Requires Python 3.10+ (developed on 3.14). No third-party packages are needed for the build;
`jsonschema` is optional and only enables schema validation.

```bash
python scripts/build_catalog.py     # regenerate every JSON artifact
python scripts/verify_sources.py    # live reachability check (network, ~2-4 minutes)
python scripts/build_catalog.py     # merge verification results into the artifacts
python scripts/validate_catalog.py  # consistency checks; exit code 1 on error
python -m pipeline.run --all        # rebuild the twelve worked rankings
python scripts/validate_rankings.py # ranking provenance and ordering checks
python scripts/build_site.py        # regenerate the static catalog browser in site/
```

The Python files in `scripts/` are the source of truth:

- `scripts/topic_catalog.py` — categories, topics, bundles of default sources, extra backups
- `scripts/source_catalog.py` — source records and their metadata
- `scripts/method_catalog.py` — the ranking method library

Never edit the generated JSON by hand; it will be overwritten.

### Validation

`scripts/validate_catalog.py` checks unique IDs, slug format, parent links, method and source
references, count consistency, status/availability vocabulary, `unsupported` topics having no
free source, usage lists pointing at real topics, and (when `jsonschema` is installed) full schema
conformance for every generated record. Errors fail; warnings (for example an unused source) do
not.

---

## Adding a topic

1. Add a `T(...)` entry to the right category in `scripts/topic_catalog.py`.
2. Pick a method from `ranking-methods/methods.json`; if none fits, add one to
   `scripts/method_catalog.py` rather than overloading an existing method.
3. Reference sources that exist in `scripts/source_catalog.py`. Prefer two independent sources.
4. If only a proprietary dataset exists, set `status="unsupported"`, `availability="none"`, and
   explain why in `caveats`. Do not invent an open alternative.
5. If the ranking is an attention or canon proxy, set `status="researched_proxy"` and say so in the
   question and the notes.
6. Rebuild and validate.

---

## Adding a source

1. Add an `S(...)` record with the official URL, docs URL, a small representative test URL, access
   model, auth, limits and licence.
2. If the licence cannot be confirmed, use `commercial="unclear"` and explain in `caveats`. Do not
   guess.
3. Run `verify_sources.py`, then `build_catalog.py` so the verification block is merged.
4. Reference it from a topic so it stops appearing in `reports/unused-sources.json`.

---

## Honest limitations

- Coverage is deliberately uneven: consumer products, culture and services are thin on free data,
  while science, macro statistics and geospatial topics are strong. That is a finding, not an
  oversight.
- Attention proxies (Wikipedia pageviews, Wikidata sitelinks, Last.fm scrobbles, GitHub stars) are
  labelled as proxies everywhere. They measure recorded attention, with a strong English and
  Western skew, and they are not popularity, sales or quality.
- Composite indices encode value judgements. The method library requires published weights and a
  sensitivity check, but the underlying indices remain contested.
- 29 topics are marked unsupported. They are listed publicly so the gap is visible.
- Source verification is a snapshot. Endpoints move, quotas shrink and licences change; the
  `last_checked` field is the only guarantee of freshness.

---

## Licence

The catalog metadata in this repository is released under CC0 1.0. The data described by the
catalog is **not** covered by that licence: each source keeps its own terms, and those terms
govern any downstream use.
