import pytest
from evaluation.metrics import character_error_rate, precision_recall_f1, rubric_score


def test_precision_recall_f1_counts_false_negatives():
    result = precision_recall_f1([1, 1, 0, 0], [1, 0, 1, 0])
    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["tn"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5
    assert result["false_negative_rate"] == 0.5


def test_metrics_reject_mismatched_inputs():
    with pytest.raises(ValueError):
        precision_recall_f1([1], [1, 0])


def test_character_error_rate():
    assert character_error_rate("cat", "cat") == 0
    assert character_error_rate("cat", "cut") == pytest.approx(1 / 3)


def test_rubric_summary():
    result = rubric_score([2, 2, 1, 0, 2])
    assert result["score"] == 7
    assert result["maximum"] == 10
    assert result["percent"] == 70
