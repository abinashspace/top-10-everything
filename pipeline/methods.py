"""Ranking and selection methods.

These implement the generic mechanics used by the method library in
ranking-methods/methods.json. A method is applied to already-normalised records
that all share one numeric measure; the adapter is responsible for making the
values comparable.

The functions here are pure so they can be tested without network access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class Ranked:
    rank: int
    record: dict


def coerce_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):  # NaN/inf
        return None
    return number


def select_top(
    records: Iterable[dict],
    *,
    value_key: str = "value",
    descending: bool = True,
    top_n: int = 10,
) -> tuple[list[Ranked], list[dict], dict]:
    """Sort, drop missing values, and assign dense ranks.

    Returns (selected, excluded_for_missing_value, diagnostics).

    Ties share a rank. Selection takes the first `top_n` records after sorting;
    if the value at the cut is shared with the next record, the ranking reports
    `tied_at_cut` so a reader can see that rank 10 is not unique.
    """
    if top_n < 1:
        raise ValueError("top_n must be >= 1")

    usable: list[dict] = []
    missing: list[dict] = []
    for record in records:
        number = coerce_number(record.get(value_key))
        if number is None:
            missing.append(record)
            continue
        enriched = dict(record)
        enriched["_value"] = number
        usable.append(enriched)

    usable.sort(key=lambda r: (r["_value"], r.get("name", "")), reverse=descending)
    if not descending:
        usable.sort(key=lambda r: (r["_value"], r.get("name", "")))

    selected = usable[:top_n]

    ranked: list[Ranked] = []
    dense_rank = 0
    previous: float | None = None
    for record in selected:
        value = record["_value"]
        if previous is None or value != previous:
            dense_rank += 1
        previous = value
        ranked.append(Ranked(rank=dense_rank, record=record))

    tied_at_cut = False
    if len(usable) > top_n and selected:
        tied_at_cut = usable[top_n]["_value"] == selected[-1]["_value"]

    diagnostics = {
        "records_in": len(usable) + len(missing),
        "records_ranked": len(usable),
        "records_missing_value": len(missing),
        "tied_at_cut": tied_at_cut,
        "distinct_values_selected": dense_rank,
    }
    return ranked, missing, diagnostics


def bayesian_average(mean: float, votes: int, global_mean: float, prior_votes: float) -> float:
    """Shrink a user rating toward the global mean.

    (v / (v + m)) * R + (m / (v + m)) * C
    """
    if votes < 0 or prior_votes < 0:
        raise ValueError("votes and prior_votes must be non-negative")
    total = votes + prior_votes
    if total == 0:
        return global_mean
    return (votes / total) * mean + (prior_votes / total) * global_mean


def min_max(values: list[float]) -> list[float]:
    """Scale values to 0..1; a constant series maps to 0.5."""
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [0.5] * len(values)
    return [(v - low) / (high - low) for v in values]


def weighted_score(parts: list[tuple[float, float]]) -> float:
    """Combine (normalised_value, weight) pairs."""
    total_weight = sum(weight for _, weight in parts)
    if total_weight <= 0:
        raise ValueError("weights must sum to a positive number")
    return sum(value * weight for value, weight in parts) / total_weight


# Caveats that must travel with a ranking, by method id. These are not
# decoration: they state what the number cannot tell you.
METHOD_LIMITATIONS = {
    "official_stat": [
        "Cross-country comparability depends on the indicator's definition and reporting quality.",
        "Values may be revised after publication; the retrieval date is recorded.",
    ],
    "bibliometric": [
        "Citation counts favour large, English-language and health/life-science fields.",
        "Entity and institution name disambiguation is imperfect in any bibliographic database.",
    ],
    "market_cap": [
        "Market capitalisation is volatile and reflects expectations, not fundamentals alone.",
        "Private companies and non-listed entities are excluded by construction.",
    ],
    "attention_proxy": [
        "This measures recorded attention, not sales, quality or popularity.",
        "Attention is event-driven and skewed toward English-language sources.",
    ],
    "community_activity": [
        "Community interaction counts reflect the size and habits of one platform's audience.",
        "Platform-specific metrics are not comparable across platforms.",
    ],
    "geospatial": [
        "Geometry completeness depends on the underlying map or catalogue.",
        "Measured size is not a measure of importance.",
    ],
    "canon_proxy": [
        "Coverage reflects documentation and editorial attention, not objective merit.",
    ],
    "rating_aggregate": [
        "Audiences are self-selected; ratings are not a measure of objective quality.",
    ],
    "sales_share": [
        "Sales definitions (units vs value, sell-in vs sell-through) vary by provider.",
    ],
    "composite_index": [
        "Weights are value judgements; a different weighting produces a different ranking.",
    ],
    "survey": [
        "Question wording and cultural response styles affect cross-country comparisons.",
    ],
    "trade_flow": [
        "Mirror statistics differ between reporters; re-exports may be counted twice.",
    ],
    "patent": [
        "Filings measure strategy as much as invention; citation windows lag.",
    ],
    "event_outcome": [
        "An event result is a snapshot, not an ongoing measure of performance.",
    ],
    "approvals": [
        "Approval is a regulatory event, not evidence of efficacy or quality.",
    ],
    "benchmark": [
        "Benchmark scores are sensitive to test conditions and vendor optimisation.",
    ],
    "price_index": [
        "Baskets and reference cities differ between indices.",
    ],
    "human_review": [
        "No automated ranking should be published for this topic.",
    ],
    "editorial": [
        "Editorial rankings are licensed content, not a data product you can redistribute.",
    ],
}
