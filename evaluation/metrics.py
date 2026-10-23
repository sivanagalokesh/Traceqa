"""Small, dependency-free evaluation helpers for TraceQA.

These functions calculate metrics from manually labeled ground truth. They do not
claim model performance; users must provide representative, reviewed examples.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence


def precision_recall_f1(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, float | int]:
    """Binary metrics with 1 = positive (e.g. a real change or stale case)."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    if not y_true:
        raise ValueError("At least one labeled example is required")
    if any(v not in (0, 1) for v in (*y_true, *y_pred)):
        raise ValueError("Labels must be binary integers: 0 or 1")
    tp = sum(t == 1 and p == 1 for t, p in zip(y_true, y_pred))
    fp = sum(t == 0 and p == 1 for t, p in zip(y_true, y_pred))
    fn = sum(t == 1 and p == 0 for t, p in zip(y_true, y_pred))
    tn = sum(t == 0 and p == 0 for t, p in zip(y_true, y_pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(y_true)
    return {
        "n": len(y_true), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy,
        "false_negative_rate": fn / (fn + tp) if fn + tp else 0.0,
    }


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Character error rate = Levenshtein distance / reference character count."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    previous = list(range(len(hypothesis) + 1))
    for i, ref_char in enumerate(reference, start=1):
        current = [i]
        for j, hyp_char in enumerate(hypothesis, start=1):
            current.append(min(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ref_char != hyp_char),
            ))
        previous = current
    return previous[-1] / len(reference)


def rubric_score(scores: Iterable[int]) -> dict[str, float | int]:
    """Summarize 0-2 human rubric scores (e.g. correctness/coverage/etc.)."""
    values = list(scores)
    if not values:
        raise ValueError("At least one rubric score is required")
    if any(not isinstance(v, int) or v < 0 or v > 2 for v in values):
        raise ValueError("Rubric scores must be integers from 0 to 2")
    return {
        "criteria_scored": len(values),
        "score": sum(values),
        "maximum": 2 * len(values),
        "percent": 100 * sum(values) / (2 * len(values)),
    }
