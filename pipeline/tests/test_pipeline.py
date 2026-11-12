"""Offline tests for the ingestion pipeline.

Run from the repository root:
    python -m unittest discover -s pipeline/tests -t .
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from pipeline import adapters, rankings
from pipeline.methods import bayesian_average, min_max, select_top

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class SelectTopTests(unittest.TestCase):
    def test_sorts_descending_and_drops_missing(self):
        records = [
            {"id": "a", "name": "A", "value": 5},
            {"id": "b", "name": "B", "value": None},
            {"id": "c", "name": "C", "value": 12},
            {"id": "d", "name": "D", "value": 7},
        ]
        ranked, missing, diag = select_top(records, top_n=2)
        self.assertEqual([r.record["id"] for r in ranked], ["c", "d"])
        self.assertEqual([r.rank for r in ranked], [1, 2])
        self.assertEqual([m["id"] for m in missing], ["b"])
        self.assertEqual(diag["records_in"], 4)
        self.assertEqual(diag["records_ranked"], 3)
        self.assertEqual(diag["records_missing_value"], 1)
        self.assertFalse(diag["tied_at_cut"])

    def test_dense_ranks_for_ties(self):
        records = [
            {"id": "a", "name": "A", "value": 10},
            {"id": "b", "name": "B", "value": 10},
            {"id": "c", "name": "C", "value": 9},
        ]
        ranked, _, diag = select_top(records, top_n=3)
        self.assertEqual([r.rank for r in ranked], [1, 1, 2])
        self.assertEqual(diag["distinct_values_selected"], 2)

    def test_tie_at_cut_is_reported(self):
        # Six entities share the cut value, so rank 5 is not unique.
        records = [{"id": str(i), "name": str(i), "value": 10 if i < 6 else 5} for i in range(10)]
        _, _, diag = select_top(records, top_n=5)
        self.assertTrue(diag["tied_at_cut"])

    def test_no_tie_at_cut_when_cut_is_unique(self):
        records = [{"id": str(i), "name": str(i), "value": 10 if i < 5 else 5} for i in range(10)]
        _, _, diag = select_top(records, top_n=5)
        self.assertFalse(diag["tied_at_cut"])

    def test_ascending_direction(self):
        records = [{"id": "a", "name": "A", "value": 3}, {"id": "b", "name": "B", "value": 1}]
        ranked, _, _ = select_top(records, descending=False, top_n=2)
        self.assertEqual([r.record["id"] for r in ranked], ["b", "a"])

    def test_rejects_invalid_top_n(self):
        with self.assertRaises(ValueError):
            select_top([], top_n=0)

    def test_ignores_boolean_and_nan(self):
        records = [
            {"id": "a", "name": "A", "value": True},
            {"id": "b", "name": "B", "value": float("nan")},
            {"id": "c", "name": "C", "value": "4.5"},
        ]
        ranked, missing, _ = select_top(records, top_n=3)
        self.assertEqual([r.record["id"] for r in ranked], ["c"])
        self.assertEqual(len(missing), 2)


class MethodMathTests(unittest.TestCase):
    def test_bayesian_average_shrinks_small_samples(self):
        # One perfect 10 with 1 vote should not beat a 9.0 with 1000 votes.
        small = bayesian_average(10.0, 1, 7.0, 50)
        large = bayesian_average(9.0, 1000, 7.0, 50)
        self.assertLess(small, large)
        self.assertAlmostEqual(bayesian_average(9.0, 0, 7.0, 10), 7.0)

    def test_min_max_constant_series(self):
        self.assertEqual(min_max([5, 5, 5]), [0.5, 0.5, 0.5])

    def test_min_max_normal_series(self):
        self.assertEqual(min_max([0, 5, 10]), [0.0, 0.5, 1.0])


class ParserTests(unittest.TestCase):
    def test_worldbank_drops_aggregates_and_missing_values(self):
        valid = adapters.parse_worldbank_countries(fixture("worldbank_countries.json"))
        self.assertEqual(valid, {"USA", "CHN"})
        records = adapters.parse_worldbank_indicator(fixture("worldbank_indicator.json"), valid)
        self.assertEqual({r["id"] for r in records}, {"USA", "CHN"})
        self.assertEqual(records[0]["period"], "2025")

    def test_worldbank_last_updated(self):
        self.assertEqual(adapters.worldbank_last_updated(fixture("worldbank_indicator.json")), "2026-11-11")

    def test_owid_drops_aggregates_and_picks_latest_year(self):
        records, year = adapters.parse_owid_csv(fixture("owid.csv"), "emissions_total")
        self.assertEqual(year, 2023)
        self.assertEqual({r["id"] for r in records}, {"AAA", "BBB", "GGG"})
        values = {r["id"]: r["value"] for r in records}
        self.assertEqual(values["AAA"], 20)  # 2023, not the 2022 value
        self.assertEqual(values["GGG"], 50)

    def test_exoplanets_skips_missing_mass(self):
        records = adapters.parse_exoplanets(fixture("exoplanets.json"))
        self.assertEqual([r["name"] for r in records], ["Small b", "Heavy b"])
        self.assertEqual(records[0]["unit"], "Earth masses")

    def test_asteroids_trims_names_and_skips_missing_diameter(self):
        records = adapters.parse_asteroids(fixture("asteroids.json"))
        self.assertEqual([r["name"] for r in records], ["1 Ceres", "4 Vesta", "20000 Varuna"])
        self.assertEqual(records[0]["value"], 939.4)

    def test_asteroids_can_exclude_distant_objects(self):
        records = adapters.parse_asteroids(fixture("asteroids.json"), allowed_classes={"MBA"})
        self.assertEqual([r["name"] for r in records], ["1 Ceres", "4 Vesta"])

    def test_openalex_filters_type_and_missing_citations(self):
        records = adapters.parse_openalex(fixture("openalex.json"), allowed_types={"education"})
        self.assertEqual([r["name"] for r in records], ["University A"])

    def test_openalex_journals_use_citations_per_work(self):
        records = adapters.parse_openalex_journals(
            fixture("openalex_journals.json"), min_works=2000
        )
        # Tiny journal and the book series are dropped; the ratio decides order.
        by_name = {r["name"]: r for r in records}
        self.assertEqual(set(by_name), {"Big Journal", "Dense Journal"})
        self.assertAlmostEqual(by_name["Dense Journal"]["value"], 20.0)
        self.assertAlmostEqual(by_name["Big Journal"]["value"], 10.0)
        self.assertEqual(by_name["Big Journal"]["extra"]["works_count"], 10000)
        self.assertIn("per published work", by_name["Big Journal"]["unit"])

    def test_coingecko_skips_null_market_cap(self):
        records = adapters.parse_coingecko(fixture("coingecko.json"))
        self.assertEqual([r["id"] for r in records], ["bitcoin"])

    def test_usgs_skips_null_magnitude_and_keeps_depth(self):
        records = adapters.parse_usgs(fixture("usgs.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], 9.5)
        self.assertEqual(records[0]["extra"]["depth_km"], 25.0)

    def test_radio_unescapes_names_and_skips_zero_clicks(self):
        records = adapters.parse_radio(fixture("radio.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "RTL & Co")
        self.assertEqual(records[0]["value"], 10)


class BuildRankingTests(unittest.TestCase):
    def test_builds_payload_from_catalog_and_stub_adapter(self):
        from pipeline.adapters import Dataset

        stub = Dataset(
            records=[
                {"id": "x", "name": "X", "value": 2, "unit": "widgets", "period": "2025", "extra": {}},
                {"id": "y", "name": "Y", "value": 1, "unit": "widgets", "period": "2025", "extra": {}},
                {"id": "z", "name": "Z", "value": None, "unit": "widgets", "period": "2025", "extra": {}},
            ],
            source_ids=["world_bank"],
            urls=["https://example.invalid"],
            notes=["fixture note"],
            retrieved_at="2026-01-01T00:00:00+00:00",
            snapshot={"fixture": True},
            unit="widgets",
            measure="Widgets produced",
            provider_updated="2025-12-31",
        )
        topics = rankings.load_topics()
        sources = rankings.load_sources()
        patched = dict(adapters.ADAPTERS)
        patched["worldbank_gdp"] = lambda **_: stub
        original = rankings.ADAPTERS
        rankings.ADAPTERS = patched
        try:
            payload = rankings.build_ranking(
                "business-finance.economies",
                topics=topics,
                sources=sources,
                now="2026-01-02T00:00:00+00:00",
            )
        finally:
            rankings.ADAPTERS = original

        self.assertEqual(payload["topic_id"], "business-finance.economies")
        self.assertEqual([row["rank"] for row in payload["ranking"]], [1, 2])
        self.assertEqual([row["name"] for row in payload["ranking"]], ["X", "Y"])
        self.assertEqual(payload["method"]["id"], topics["business-finance.economies"]["ranking_method"]["id"])
        self.assertTrue(payload["method"]["matches_catalog_method"])
        self.assertEqual(payload["measure"]["unit"], "widgets")
        self.assertEqual(payload["snapshot"]["records_missing_value"], 1)
        self.assertEqual(payload["sources"][0]["id"], "world_bank")
        self.assertIn("fixture note", payload["caveats"])
        self.assertTrue(payload["caveats"])
        self.assertEqual(payload["refresh_after"], "2026-04-02")


if __name__ == "__main__":
    unittest.main()
