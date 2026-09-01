#!/usr/bin/env python3
"""
Layer 3 corpus integrity check — runs in CI without needing the Qwen model.

Validates that layer3_eval_corpus.py is structurally sound:
  - Every entry has all required fields
  - IDs are unique
  - should_flag is a bool
  - expected_categories is a non-empty list when should_flag is True
  - diff strings are non-empty and contain at least one + line (for TP entries)
  - Category / language coverage meets minimums

Run standalone:
    python3 tests/check_corpus.py

Run via pytest:
    pytest tests/check_corpus.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from layer3_eval_corpus import CORPUS

REQUIRED_FIELDS = {"id", "language", "category", "should_flag", "expected_categories", "diff"}

# Minimum number of unique categories and languages the corpus must cover
MIN_CATEGORIES = 4
MIN_LANGUAGES  = 3

# Coverage thresholds: at least N true-positives and N true-negatives
MIN_TP = 50
MIN_TN = 20


# ── Field-level checks ─────────────────────────────────────────────────────────

def test_corpus_non_empty() -> None:
    assert len(CORPUS) > 0, "CORPUS is empty"


def test_all_required_fields_present() -> None:
    missing: list[str] = []
    for entry in CORPUS:
        absent = REQUIRED_FIELDS - entry.keys()
        if absent:
            missing.append(f"id={entry.get('id', '?')} missing {absent}")
    assert not missing, "\n".join(missing)


def test_ids_are_unique() -> None:
    ids = [e["id"] for e in CORPUS]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"Duplicate IDs: {dupes}"


def test_should_flag_is_bool() -> None:
    bad = [e["id"] for e in CORPUS if not isinstance(e["should_flag"], bool)]
    assert not bad, f"should_flag is not bool in: {bad}"


def test_expected_categories_non_empty_for_tp() -> None:
    bad = [
        e["id"] for e in CORPUS
        if e["should_flag"] and not e.get("expected_categories")
    ]
    assert not bad, f"TP entries with empty expected_categories: {bad}"


def test_diff_strings_non_empty() -> None:
    bad = [e["id"] for e in CORPUS if not e.get("diff", "").strip()]
    assert not bad, f"Entries with empty diff: {bad}"


def test_tp_diffs_have_added_lines() -> None:
    """Every true-positive diff must have at least one + line for L1/L3 to scan."""
    bad = [
        e["id"] for e in CORPUS
        if e["should_flag"] and not any(
            line.startswith("+") and not line.startswith("+++")
            for line in e["diff"].splitlines()
        )
    ]
    assert not bad, f"TP entries with no + lines in diff: {bad}"


# ── Coverage checks ────────────────────────────────────────────────────────────

def test_minimum_tp_count() -> None:
    n = sum(1 for e in CORPUS if e["should_flag"])
    assert n >= MIN_TP, f"Only {n} true-positive entries (minimum {MIN_TP})"


def test_minimum_tn_count() -> None:
    n = sum(1 for e in CORPUS if not e["should_flag"])
    assert n >= MIN_TN, f"Only {n} true-negative entries (minimum {MIN_TN})"


def test_minimum_category_coverage() -> None:
    cats = {e["category"] for e in CORPUS}
    assert len(cats) >= MIN_CATEGORIES, (
        f"Only {len(cats)} categories (minimum {MIN_CATEGORIES}): {cats}"
    )


def test_minimum_language_coverage() -> None:
    langs = {e["language"] for e in CORPUS}
    assert len(langs) >= MIN_LANGUAGES, (
        f"Only {len(langs)} languages (minimum {MIN_LANGUAGES}): {langs}"
    )


# ── Summary (standalone) ───────────────────────────────────────────────────────

def _summary() -> None:
    tp   = sum(1 for e in CORPUS if e["should_flag"])
    tn   = len(CORPUS) - tp
    cats = {e["category"] for e in CORPUS}
    langs = {e["language"] for e in CORPUS}

    print(f"Corpus: {len(CORPUS)} entries  ({tp} TP, {tn} TN)")
    print(f"Categories ({len(cats)}): {', '.join(sorted(cats))}")
    print(f"Languages  ({len(langs)}): {', '.join(sorted(langs))}")


if __name__ == "__main__":
    _summary()
    result = pytest.main([__file__, "-v"])
    sys.exit(result)
