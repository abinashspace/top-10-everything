#!/usr/bin/env python3
"""Build the static GitHub Pages site from the generated catalog artifacts.

Reads the committed JSON (topics, sources, methods, rankings, reports) and writes
a dependency-free single-page catalog browser to ``site/``.

    python scripts/build_site.py

The output is intentionally plain HTML/CSS/JS with no third-party runtime, so it
works on GitHub Pages, on a local file server, and offline once loaded.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DATA = SITE / "data"
REPO = os.environ.get("GITHUB_REPOSITORY", "abinashspace/top-10-everything")


def load(path: str):
    with (ROOT / path).open(encoding="utf-8") as fh:
        return json.load(fh)


def clean(text):
    """Collapse whitespace in prose fields so the UI stays compact."""
    if not isinstance(text, str):
        return text
    return re.sub(r"\s+", " ", text).strip()


def build_payload() -> dict:
    index = load("topics/index.json")
    source_directory = load("sources/source-directory.json")
    methods = load("ranking-methods/methods.json")
    ranking_index = load("rankings/index.json")
    unsupported = load("reports/unsupported-topics.json")

    categories = []
    topics = []
    for category in index["categories"]:
        categories.append(
            {
                "id": category["id"],
                "name": category["name"],
                "topic_count": category["topic_count"],
                "subcategory_count": category["subcategory_count"],
                "status": category.get("research_status_counts", {}),
                "availability": category.get("data_availability_counts", {}),
            }
        )
        category_file = load(category["file"])
        for topic in category_file["topics"]:
            method = topic.get("ranking_method") or {}
            sources = topic.get("sources") or {}

            def slim_source(item):
                return {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "access": item.get("access_model"),
                    "commercial": item.get("commercial_use"),
                }

            topics.append(
                {
                    "id": topic["id"],
                    "name": topic["name"],
                    "category": category["id"],
                    "category_name": category["name"],
                    "path": topic.get("path", []),
                    "subcategories": topic.get("subcategories", []),
                    "coverage": topic.get("geographic_coverage", []),
                    "frequency": topic.get("update_frequency"),
                    "availability": topic.get("data_availability"),
                    "status": topic.get("research_status"),
                    "risk": topic.get("licensing_risk"),
                    "method": {
                        "id": method.get("id"),
                        "name": method.get("name"),
                        "question": clean(method.get("question", "")),
                        "metric": clean(method.get("metric", "")),
                        "subjectivity": method.get("subjectivity"),
                    },
                    "sources": {
                        "primary": [slim_source(s) for s in sources.get("primary", [])],
                        "backup": [slim_source(s) for s in sources.get("backup", [])],
                        "independent": bool(sources.get("independent_source_coverage")),
                    },
                    "notes": [clean(n) for n in topic.get("notes", [])],
                }
            )

    sources = []
    for source in source_directory["sources"]:
        access = source.get("access") or {}
        license_info = source.get("license") or {}
        verification = source.get("verification") or {}
        usage = source.get("usage") or {}
        sources.append(
            {
                "id": source["id"],
                "name": source["name"],
                "organization": source.get("organization"),
                "url": source.get("official_url"),
                "docs": source.get("api_docs_url"),
                "access": access.get("model"),
                "auth": access.get("authentication"),
                "limits": clean(access.get("limits_summary", "")),
                "license": license_info.get("name"),
                "commercial": license_info.get("commercial_use"),
                "attribution": license_info.get("attribution_required"),
                "verification": verification.get("result"),
                "checked": verification.get("last_checked"),
                "frequency": source.get("update_frequency"),
                "reference_only": bool(source.get("reference_only")),
                "primary_topics": usage.get("primary_for_count", 0),
                "backup_topics": usage.get("backup_for_count", 0),
                "caveats": [clean(c) for c in source.get("caveats", [])],
            }
        )

    method_list = []
    for method in methods["methods"]:
        method_list.append(
            {
                "id": method["id"],
                "name": method["name"],
                "basis": method.get("basis"),
                "subjectivity": method.get("subjectivity"),
                "description": clean(method.get("description", "")),
                "criteria": [clean(c) for c in method.get("criteria", [])],
                "indicators": [clean(i) for i in method.get("indicators", [])],
                "scoring": clean(method.get("scoring", "")),
                "data_requirements": [clean(d) for d in method.get("data_requirements", [])],
                "human_review": bool(method.get("human_verification_required")),
                "limitations": [clean(item) for item in method.get("limitations", [])],
            }
        )

    rankings = []
    for entry in ranking_index["rankings"]:
        rankings.append(load(entry["file"]))

    return {
        "meta": {
            "generated_at": index["generated_at"],
            "repo": REPO,
            "totals": {
                "categories": index["total_categories"],
                "topics": index["total_topics"],
                "subcategories": index["total_subcategories"],
                "sources": source_directory["source_count"],
                "methods": methods["method_count"],
                "rankings": ranking_index["count"],
            },
            "status": index["research_status_counts"],
            "availability": index["data_availability_counts"],
            "risk": index["licensing_risk_counts"],
            "access": source_directory["access_model_counts"],
            "commercial": source_directory["commercial_use_counts"],
            "verification": source_directory["verification_result_counts"],
            "ranking_generated_at": ranking_index["generated_at"],
        },
        "categories": categories,
        "topics": topics,
        "sources": sources,
        "methods": method_list,
        "rankings": rankings,
        "unsupported": unsupported,
    }


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Top 10 Everything — the research catalog</title>
<meta name="description" content="A machine-readable map of what can honestly be ranked, with which free data, and how. 530 topics, 143 sources, 20 ranking methods and 12 proven rankings.">
<meta name="theme-color" content="#f6f2ea">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='10' fill='%23171512'/%3E%3Ctext x='32' y='44' font-family='Georgia,serif' font-size='34' font-weight='700' fill='%23f6f2ea' text-anchor='middle'%3E10%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<a class="skip" href="#topics">Skip to the catalog</a>

<header class="masthead">
  <div class="wrap masthead-inner">
    <a class="brand" href="#top"><span class="brand-mark">10</span><span class="brand-text">Top 10 Everything</span></a>
    <nav aria-label="Sections">
      <a href="#rankings">Rankings</a>
      <a href="#topics">Topics</a>
      <a href="#sources">Sources</a>
      <a href="#methods">Methods</a>
    </nav>
    <a class="ghost-button" id="repo-link" href="https://github.com/__REPO__" rel="noopener">GitHub ↗</a>
  </div>
</header>

<main id="top">
  <section class="hero wrap">
    <p class="eyebrow">Research catalog · CC0 metadata</p>
    <h1>What can honestly<br>be ranked<span class="accent">.</span></h1>
    <p class="lede">A machine-readable map of <strong>530 topics</strong>, the free data behind them,
      the method each ranking would use, and the places where the data simply does not exist.
      This is the research layer behind rankings — not a pile of invented lists.</p>
    <div class="stats" id="hero-stats" aria-label="Catalog totals"></div>
    <div class="hero-actions">
      <a class="button primary" href="#rankings">See the 12 proven rankings</a>
      <a class="button" href="#topics">Browse all 530 topics</a>
      <a class="button quiet" href="https://github.com/__REPO__/tree/main/topics" rel="noopener">Raw JSON ↗</a>
    </div>
    <p class="hero-note">Guiding rule: never invent an API, a limit, a licence, or a ranking.
      When something is restricted or unverifiable, the catalog says so.</p>
  </section>

  <section class="band" id="rankings">
    <div class="wrap">
      <div class="section-head">
        <div>
          <p class="kicker">01 — The proof</p>
          <h2>Twelve rankings, built end to end</h2>
        </div>
        <p class="section-note">Each one fetches a live dataset, applies the catalogued method and records
          provenance, candidate-set size, missing values, ties and licence terms. Click a card for the full list.</p>
      </div>
      <div class="ranking-grid" id="ranking-grid"></div>
    </div>
  </section>

  <section class="wrap section" id="topics">
    <div class="section-head">
      <div>
        <p class="kicker">02 — The catalog</p>
        <h2>Every topic, with its honest status</h2>
      </div>
      <p class="section-note"><span class="badge researched">researched</span> means a viable source and method exist.
        <span class="badge partial">partial</span> means gaps remain. <span class="badge unsupported">unsupported</span> means
        the idea is valid but free data is not.</p>
    </div>

    <div class="controls" role="search">
      <label class="field grow">
        <span>Search</span>
        <input id="topic-search" type="search" placeholder="Try “exoplanets”, “coffee”, “longevity”…" autocomplete="off">
      </label>
      <label class="field">
        <span>Category</span>
        <select id="topic-category"><option value="">All categories</option></select>
      </label>
      <label class="field">
        <span>Status</span>
        <select id="topic-status">
          <option value="">Any status</option>
          <option value="researched">Researched</option>
          <option value="researched_proxy">Researched (proxy)</option>
          <option value="partial">Partial</option>
          <option value="unsupported">Unsupported</option>
        </select>
      </label>
      <label class="field">
        <span>Data</span>
        <select id="topic-availability">
          <option value="">Any availability</option>
          <option value="strong">Strong</option>
          <option value="moderate">Moderate</option>
          <option value="limited">Limited</option>
          <option value="none">None</option>
        </select>
      </label>
    </div>

    <div class="result-line"><span id="topic-count" aria-live="polite"></span>
      <button class="link-button" id="topic-reset" type="button">Reset filters</button></div>
    <div class="topic-list" id="topic-list"></div>
    <div class="load-more-row"><button class="button" id="topic-more" type="button" hidden>Show more topics</button></div>
  </section>

  <section class="band" id="sources">
    <div class="wrap">
      <div class="section-head">
        <div>
          <p class="kicker">03 — The data</p>
          <h2>143 sources, verified, not assumed</h2>
        </div>
        <p class="section-note">Reachability was checked with one small unauthenticated request per source.
          That proves the provider responds — not that a dataset is legally cleared or ingestible.</p>
      </div>
      <div class="controls">
        <label class="field grow">
          <span>Search sources</span>
          <input id="source-search" type="search" placeholder="Provider, data type, licence…" autocomplete="off">
        </label>
        <label class="field">
          <span>Access</span>
          <select id="source-access">
            <option value="">Any access</option>
            <option value="open">Open</option>
            <option value="free_key">Free with API key</option>
            <option value="free_tier">Free tier</option>
            <option value="free_account">Free account</option>
            <option value="restricted">Restricted</option>
            <option value="paid">Paid</option>
          </select>
        </label>
        <label class="field">
          <span>Commercial use</span>
          <select id="source-commercial">
            <option value="">Any licence</option>
            <option value="allowed">Allowed</option>
            <option value="allowed_with_conditions">Allowed with conditions</option>
            <option value="unclear">Unclear</option>
            <option value="varies">Varies</option>
            <option value="prohibited">Prohibited</option>
          </select>
        </label>
      </div>
      <div class="result-line"><span id="source-count" aria-live="polite"></span></div>
      <div class="source-list" id="source-list"></div>
    </div>
  </section>

  <section class="wrap section" id="methods">
    <div class="section-head">
      <div>
        <p class="kicker">04 — The recipes</p>
        <h2>Twenty reusable ranking methods</h2>
      </div>
      <p class="section-note">A method says how a ranking must be computed: criteria, indicators, scoring rule,
        data requirements and known limitations. It does not claim the data exists for every topic that cites it.</p>
    </div>
    <div class="method-grid" id="method-grid"></div>
  </section>

  <section class="band" id="limits">
    <div class="wrap">
      <div class="section-head">
        <div>
          <p class="kicker">05 — The fine print</p>
          <h2>Limitations and licensing</h2>
        </div>
      </div>
      <div class="note-grid">
        <article class="note-card">
          <h3>What this catalog does not claim</h3>
          <ul>
            <li>Coverage is deliberately uneven: science, macro statistics and geospatial topics are strong; consumer products and culture are thin on free data. That is a finding.</li>
            <li>Attention proxies (Wikipedia pageviews, Wikidata sitelinks, Last.fm scrobbles, GitHub stars) measure recorded attention — not popularity, sales or quality.</li>
            <li>Composite indices encode value judgements. Weights must be published and sensitivity-checked, but the indices remain contested.</li>
            <li>Source verification is a snapshot. Endpoints move, quotas shrink and licences change.</li>
          </ul>
        </article>
        <article class="note-card warning">
          <h3>Read before republishing</h3>
          <p>The catalog metadata is CC0. The <strong>data it describes is not</strong> — each source keeps its own terms,
            and those terms govern downstream use. Known restrictions include WHO GHO (non-commercial),
            Open-Meteo free tier (non-commercial), IMDb (non-commercial), Spotify/NewsAPI/Guardian free tiers,
            and the CC BY-ND Transparency International CPI (modified rankings may not be redistributed).</p>
          <p>This is a research aid, not legal advice. Check the provider's terms, the specific dataset's terms and your
            jurisdiction's database rights before commercial publication.</p>
        </article>
      </div>
      <div class="unsupported-block">
        <h3>29 topics are marked unsupported — publicly</h3>
        <p>The gap is the point. These are valid ideas that cannot be built responsibly from free data today.</p>
        <div class="chips" id="unsupported-chips"></div>
      </div>
    </div>
  </section>
</main>

<footer class="footer">
  <div class="wrap footer-inner">
    <div>
      <p class="footer-title">Top 10 Everything</p>
      <p>Research catalog metadata released under CC0 1.0. Described datasets keep their own licences.</p>
    </div>
    <div class="footer-links">
      <a href="https://github.com/__REPO__" rel="noopener">Repository ↗</a>
      <a href="https://github.com/__REPO__/blob/main/README.md" rel="noopener">README ↗</a>
      <a href="https://github.com/__REPO__/tree/main/sources" rel="noopener">Sources JSON ↗</a>
      <a href="#top">Back to top ↑</a>
    </div>
  </div>
  <div class="wrap footer-meta"><span id="generated"></span></div>
</footer>

<dialog id="ranking-dialog" aria-labelledby="dialog-title">
  <div class="dialog-head">
    <div>
      <p class="kicker" id="dialog-kicker">Worked ranking</p>
      <h2 id="dialog-title">Ranking</h2>
    </div>
    <button class="icon-button" id="dialog-close" type="button" aria-label="Close">×</button>
  </div>
  <div id="dialog-body"></div>
</dialog>

<script src="data/catalog.js"></script>
<script src="assets/site.js"></script>
</body>
</html>
"""


def write_payload(payload: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    # A JS assignment rather than fetch() so the page also works from file://.
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (DATA / "catalog.js").write_text(
        "window.CATALOG = " + body + ";\n", encoding="utf-8"
    )
    (DATA / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    payload = build_payload()
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(HTML.replace("__REPO__", REPO), encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    write_payload(payload)

    topics = payload["topics"]
    counts = {}
    for topic in topics:
        counts[topic["status"]] = counts.get(topic["status"], 0) + 1
    print(
        "Built site/: "
        f"{len(topics)} topics, {len(payload['sources'])} sources, "
        f"{len(payload['methods'])} methods, {len(payload['rankings'])} rankings"
    )
    print("Status:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
