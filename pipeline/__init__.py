"""Ingestion proof of concept for Top 10 Everything.

The catalog says which sources and methods a topic needs. This package shows
that a subset of those topics can actually be built end to end: fetch, parse,
rank, and emit a provenance-rich result.

Run with:
    python -m pipeline.run --all
"""
