"""Lightweight linear algebra helpers.

The point of this module is to provide structured code with docstrings that
mention "cosine similarity" and "rag embeddings" so semantic queries pick it up.
"""

from __future__ import annotations

from math import sqrt
from typing import Iterable, List


def l2_norm(vector: Iterable[float]) -> float:
    """Compute the Euclidean norm of a vector."""

    return sqrt(sum(component * component for component in vector))


def cosine_similarity(left: List[float], right: List[float]) -> float:
    """Return cosine similarity for two equal-length vectors.

    This is useful when inspecting RAG embedding quality.
    """

    if len(left) != len(right):  # pragma: no cover - simple guard
        raise ValueError("Vectors must have the same length")
    denom = l2_norm(left) * l2_norm(right)
    if denom == 0:
        return 0.0
    dot = sum(l * r for l, r in zip(left, right))
    return dot / denom
