"""Path helpers driven by config/stores.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.repo_root import find_repo_root

ROOT = find_repo_root(Path(__file__).parent)


def load_stores_config() -> dict[str, Any]:
    with open(ROOT / "config" / "stores.json", encoding="utf-8") as handle:
        return json.load(handle)


def list_countries() -> list[str]:
    config = load_stores_config()
    return list(config.get("countries", {}).keys())


def list_stores(country: str | None = None) -> list[str]:
    config = load_stores_config()
    country = country or config.get("default_country", "nl")
    stores = config["countries"].get(country, {}).get("stores", {})
    return list(stores.keys())


def store_config(country: str, slug: str) -> dict[str, Any]:
    config = load_stores_config()
    stores = config["countries"][country]["stores"]
    if slug not in stores:
        raise KeyError(f"Unknown store {country}/{slug}")
    return stores[slug]


def store_dir(country: str, slug: str) -> Path:
    cfg = store_config(country, slug)
    return ROOT / cfg["dir"]


def catalog_path(country: str, slug: str) -> Path:
    cfg = store_config(country, slug)
    return store_dir(country, slug) / cfg["catalog"]


def catalog_rel_path(country: str, slug: str) -> str:
    return str(catalog_path(country, slug).relative_to(ROOT))


def all_catalog_paths(country: str | None = None) -> list[tuple[str, str, Path]]:
    config = load_stores_config()
    country = country or config.get("default_country", "nl")
    result: list[tuple[str, str, Path]] = []
    for slug in list_stores(country):
        result.append((country, slug, catalog_path(country, slug)))
    return result


def intermediate_globs(country: str | None = None) -> list[str]:
    config = load_stores_config()
    country = country or config.get("default_country", "nl")
    patterns: list[str] = []
    for slug in list_stores(country):
        cfg = store_config(country, slug)
        store_rel = cfg["dir"]
        for pattern in cfg.get("intermediate_globs", []):
            patterns.append(f"{store_rel}/{pattern}")
    return patterns
