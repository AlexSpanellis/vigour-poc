"""
Unit tests for bib OCR resolve_bibs majority vote logic.
Run: pytest tests/unit/test_ocr.py
"""
from pipeline.ocr import resolve_bibs


def test_majority_vote_resolves_clear_winner():
    readings = [
        {1: 7, 2: 14},
        {1: 7, 2: 14},
        {1: 7, 2: None},
        {1: 8, 2: 14},
    ]
    resolved = resolve_bibs(readings, min_confidence=0.6)
    assert resolved[1][0] == 7         # majority is 7
    assert resolved[2][0] == 14        # all reads agree


def test_unresolved_when_below_confidence():
    readings = [
        {1: 5},
        {1: 6},
        {1: 5},
    ]
    # 5 wins 2/3 = 0.67 — above 0.6 threshold
    resolved = resolve_bibs(readings, min_confidence=0.6)
    assert resolved[1][0] == 5

    # Raise threshold to 0.9 — should be unresolved
    resolved_strict = resolve_bibs(readings, min_confidence=0.9)
    assert resolved_strict[1][0] is None


def test_no_reads_returns_none():
    readings = [{1: None}, {1: None}]
    resolved = resolve_bibs(readings, min_confidence=0.6)
    assert resolved[1][0] is None
    assert resolved[1][1] == 0.0
