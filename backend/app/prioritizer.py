"""Priority scoring: turns raw signals into one 0-100 editorial ranking."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .config import settings


def parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def freshness(age_hours: float) -> float:
    """Exponential decay: 1.0 at t=0, 0.5 at the half-life, -> 0."""
    if age_hours < 0:
        age_hours = 0.0
    return 0.5 ** (age_hours / settings.freshness_half_life_hours)


def category_weight(categories: list[str]) -> float:
    if not categories:
        return 0.4
    return max(settings.category_weights.get(c, 0.4) for c in categories)


def cluster_bonus(cluster_size: int) -> float:
    """A story covered by N independent sources is trending. Diminishing returns."""
    if cluster_size <= 1:
        return 0.0
    return min(1.0, math.log2(cluster_size) / 3.0)


def priority_score(*, trending: float, age_hours: float, authority: float,
                   categories: list[str], novelty: float,
                   cluster_size: int = 1) -> float:
    w = settings.weights
    trending_norm = max(0.0, min(10.0, trending + cluster_bonus(cluster_size) * 2.0)) / 10.0
    parts = {
        "trending": w["trending"] * trending_norm,
        "freshness": w["freshness"] * freshness(age_hours),
        "source": w["source"] * max(0.0, min(1.0, authority)),
        "category": w["category"] * category_weight(categories),
        "novelty": w["novelty"] * max(0.0, min(1.0, novelty)),
    }
    return round(100.0 * sum(parts.values()), 1)


def priority_band(score: float) -> str:
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    if score >= 25:
        return "cool"
    return "cold"
