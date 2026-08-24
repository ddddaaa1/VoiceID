"""Vector operations and robust voice-template construction."""

from __future__ import annotations

import math
from collections.abc import Sequence

Vector = tuple[float, ...]


def normalize(vector: Sequence[float]) -> Vector:
    if not vector:
        raise ValueError("an embedding cannot be empty")
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 1e-12:
        raise ValueError("an embedding cannot be the zero vector")
    return tuple(value / magnitude for value in vector)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embeddings must have the same dimension")
    a, b = normalize(left), normalize(right)
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True))))


def centroid(embeddings: Sequence[Sequence[float]]) -> Vector:
    if not embeddings:
        raise ValueError("at least one embedding is required")
    dimension = len(embeddings[0])
    if dimension == 0 or any(len(item) != dimension for item in embeddings):
        raise ValueError("all embeddings must have the same non-zero dimension")
    mean = [sum(item[index] for item in embeddings) / len(embeddings) for index in range(dimension)]
    return normalize(mean)


def robust_voice_template(
    embeddings: Sequence[Sequence[float]],
    *,
    min_samples: int = 3,
    outlier_threshold: float = 0.45,
) -> Vector:
    """Create a centroid after rejecting inconsistent enrollment samples."""
    if len(embeddings) < min_samples:
        raise ValueError(f"at least {min_samples} enrollment samples are required")

    normalized = [normalize(item) for item in embeddings]
    retained: list[Vector] = []
    for index, candidate in enumerate(normalized):
        peers = normalized[:index] + normalized[index + 1 :]
        try:
            peer_centroid = centroid(peers)
        except ValueError:
            continue
        if cosine_similarity(candidate, peer_centroid) >= outlier_threshold:
            retained.append(candidate)

    if len(retained) < min_samples:
        raise ValueError("enrollment samples are not mutually consistent")
    return centroid(retained)
