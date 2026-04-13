"""
Data validation helpers. Each validator raises ValueError on failure.
Run before uploading to S3 to catch bad data early.
"""

from typing import Any


def require_keys(data: dict, keys: list[str], context: str = "") -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError(f"{context}: missing keys {missing}")


def require_nonempty(data: list, context: str = "") -> None:
    if not data:
        raise ValueError(f"{context}: empty list")


def require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")


def validate_investment_overview(data: dict) -> None:
    require_keys(data, ["years", "disease_split", "authorized_vs_deployed"], "investment_overview")
    require_nonempty(data["years"], "investment_overview.years")
    for row in data["years"]:
        require_keys(row, ["year", "pmi", "gf", "nih"], "investment_overview.years row")
        require_positive(row["pmi"], "pmi")


def validate_world_map(data: dict) -> None:
    require_keys(data, ["flows"], "world_map")
    require_nonempty(data["flows"], "world_map.flows")
    for flow in data["flows"]:
        require_keys(flow, ["iso3", "name", "us_allocation_usd"], "world_map.flows row")


def validate_us_ecosystem(data: dict) -> None:
    require_keys(data, ["states", "total_nih_usd", "total_orgs", "total_trials"], "us_ecosystem")
    require_nonempty(data["states"], "us_ecosystem.states")


def validate_impact(data: dict) -> None:
    require_keys(
        data,
        ["lives_saved_total", "cases_averted_annual", "cost_per_life_saved_usd", "country_progress"],
        "impact",
    )
    require_positive(data["lives_saved_total"], "lives_saved_total")


def validate_outlook(data: dict) -> None:
    require_keys(
        data,
        ["funding_gap_usd", "who_target_usd", "high_dependency_countries", "resistance_hotspots"],
        "outlook",
    )
    require_nonempty(data["high_dependency_countries"], "high_dependency_countries")
