# Ingestion proof of concept

The catalog claims that certain topics can be ranked from free data with a documented method.
This pipeline tests that claim on a small set of topics: it fetches the real datasets, applies the
catalogued method, and emits a result with full provenance.

It is a proof of concept, not a production service. It runs on demand or weekly, writes static
JSON, and never publishes a ranking it could not build from an identified source.

## Why only twelve topics

Every adapter must satisfy four conditions:

1. The provider is reachable without a paid plan (open, or a documented free tier).
2. The licence permits at least non-commercial use, and the restriction is recorded in the output.
3. The dataset actually answers the catalogued question, rather than a convenient neighbour of it.
4. The measure is comparable across entities after documented filtering (aggregates removed,
   missing values dropped, reference period stated).

Topics that fail any condition stay in the catalog as `partial`, `researched_proxy` or
`unsupported`. They are not faked here.

## Architecture

```
pipeline/
  fetch.py       polite HTTP + on-disk cache (12h default), retries, size caps
  adapters.py    one adapter per dataset: fetch -> parse -> normalised records
  methods.py     pure ranking mechanics: dense ranks, ties, Bayesian average, min-max
  rankings.py    spec table + payload assembly + index writer
  run.py         CLI (--all, --topic, --offline, --refresh, --top, --list)
  fixtures/      small recorded samples used by the offline tests
  tests/         22 unit tests, no network required

rankings/
  <topic-id>.json   one worked ranking
  index.json        summary of every ranking on disk
```

Data flow:

```
catalog topic  ──► spec (topic -> adapter)
                     │
                     ▼
              fetch (cache/HTTP) ──► parse ──► records[{id,name,value,unit,period}]
                                                   │
                                                   ▼
                                    select_top (sort, drop nulls, dense ranks)
                                                   │
                                                   ▼
                        payload + provenance + caveats ──► rankings/<topic>.json
```

## The twelve worked rankings

| Topic | Provider | Method | Candidate set |
| --- | --- | --- | --- |
| Economies | World Bank `NY.GDP.MKTP.CD` | official stat | 214 countries |
| Longevity | World Bank `SP.DYN.LE00.IN` | official stat | 217 countries |
| Aging | World Bank `SP.POP.65UP.TO.ZS` | official stat | 217 countries |
| Carbon emitters | Our World in Data (Global Carbon Budget) | official stat | 220 countries, latest common year |
| Renewable energy | Our World in Data (Ember) | official stat | 90 countries |
| Exoplanets | NASA Exoplanet Archive TAP | official stat | confirmed planets with a mass estimate |
| Asteroids | JPL Small-Body Database | official stat | main-belt asteroids with diameter ≥ 50 km |
| Research institutions | OpenAlex | bibliometric | top 100 institutions by citations |
| Scientific journals | OpenAlex | bibliometric | top 200 journals by citations, ≥ 2,000 works |
| Cryptocurrencies | CoinGecko | market cap | top 100 by market cap |
| Earthquake monitoring | USGS FDSN event API | official stat | catalogued events Mw ≥ 8 since 1900 |
| Radio stations | Radio Browser | community activity | top 50 by cumulative clicks |

All twelve are key-free at the endpoint used. OpenAlex and CoinGecko apply free-tier rate limits
and ask for attribution; those obligations are repeated in each output's `sources` block.

## What each output contains

```json
{
  "topic_id": "environment-nature.carbon-emitters",
  "question": "...catalogued question...",
  "method": { "id": "official_stat", "matches_catalog_method": true },
  "measure": { "label": "Annual territorial CO2 emissions", "unit": "tonnes CO2" },
  "generated_at": "2026-11-12T12:00:00+00:00",
  "refresh_after": "2027-11-12",
  "snapshot": {
    "retrieved_at": "...",
    "reference_period": "2024",
    "records_considered": 220,
    "records_ranked": 220,
    "records_missing_value": 0,
    "tied_at_cut": false
  },
  "sources": [{ "id": "our_world_in_data", "commercial_use": "allowed", "verification_result": "ok" }],
  "ranking": [{ "rank": 1, "entity_id": "CHN", "name": "China", "value": 12417493000, "unit": "tonnes CO2" }],
  "caveats": ["...topic notes...", "...method limitations...", "...dataset notes..."]
}
```

`records_considered` is the size of the cleaned candidate set, not the number of rows returned by
the provider. It exists so a reader can tell whether "top 10" means "top 10 of 214 comparable
countries" or "top 10 of whatever arrived".

## Ranking rules

- One numeric measure per ranking. Units are identical across rows.
- Aggregates, regions and income groups are removed using the provider's own metadata.
- Records without a usable value are dropped and counted in `records_missing_value`.
- Ties share a dense rank (`1, 1, 2`). If the value at the cut is shared with the next record,
  `tied_at_cut` is true.
- Values are emitted as received. No rounding, smoothing or unit conversion happens silently.
- The catalog method id is copied into the output, and `matches_catalog_method` is asserted by the
  validator. A ranking cannot silently use a different method from the one catalogued.

### When the metric had to change

The first journals build ranked by raw all-time citations. It placed *Choice Reviews Online* at
rank 8 with 195,763 "works", in a list otherwise made of research journals — a data artefact
winning on volume rather than impact. Two candidate fixes were tested:

| Candidate metric | Result | Verdict |
| --- | --- | --- |
| `summary_stats.2yr_mean_citedness` | African Journal of Business Management at 200.8, above Cell | unusable, polluted by artefacts |
| citations ÷ works, within the top-200-by-citations set | Chemical Reviews 393.5, Cell 328.5, Chem Soc Rev 265.1 | adopted |

The thresholds (top 200 candidates, ≥ 2,000 works) are stated in the output's `snapshot` and in the
caveats, so a reader can see that the ratio is bounded by its candidate set rather than pretending
to cover every journal in OpenAlex.

## Reproducing

```bash
python -m pipeline.run --list                 # configured topics
python -m pipeline.run --all                  # build all twelve (uses cache)
python -m pipeline.run --all --refresh        # ignore cache, re-fetch
python -m pipeline.run --topic science.exoplanets --top 25
python -m pipeline.run --all --offline        # cache only, fails on a cold cache
python scripts/validate_rankings.py           # consistency + provenance checks
python -m unittest discover -s pipeline/tests -t .   # 22 offline tests
```

The cache lives in `pipeline/.cache/` (git-ignored). Each entry records the URL, retrieval time and
raw body, so a failure can be diagnosed without re-fetching.

## Adding a thirteenth topic

1. Confirm the topic exists in `topics/<category>.json` and that its method matches what you will
   actually compute.
2. Add a parser if the response shape is new, plus a fixture and a unit test.
3. Add an adapter returning `Dataset(records=..., source_ids=..., urls=..., notes=...)`. Set
   `measure`, `unit` and `provider_updated`.
4. Add the spec entry in `pipeline/rankings.py`.
5. Run the topic, check the leader and the top ten manually against the provider's own site, then
   run `validate_rankings.py`.
6. If the result is implausible, do not adjust the numbers. Fix the candidate set or drop the
   topic.

## Known limitations

- Point-in-time snapshots only; there is no history table yet.
- No entity-resolution layer beyond provider IDs (OpenAlex IDs, ISO3 codes, JPL designations).
- Citation rankings are not field- or age-normalised, so they favour large and old institutions.
- CoinGecko and Radio Browser metrics are platform-scoped and not comparable to anything else.
- The pipeline has no retry budget for paid or keyed sources by design; adding one would require a
  secrets strategy and a licence review.
- `rankings/` is generated output. Editing it by hand will be overwritten.
