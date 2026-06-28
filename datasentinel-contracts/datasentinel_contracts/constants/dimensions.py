"""Quality dimension weights (from legacy DQAEngine)."""

DIMENSION_WEIGHTS = {
    "Completeness": 0.15,
    "Integrity": 0.20,
    "Timeliness": 0.10,
    "Uniqueness": 0.10,
    "Accuracy": 0.20,
    "Consistency": 0.15,
    "Relevance": 0.10,
}

DIMENSIONS = list(DIMENSION_WEIGHTS.keys())
