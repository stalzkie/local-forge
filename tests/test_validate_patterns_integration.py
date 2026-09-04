#!/usr/bin/env python3
"""
--validate-patterns binary integration tests.

`localforge --validate-patterns` compiles every rule in
.localforge/patterns.toml and runs its test_positive/test_negative cases
against it, exiting non-zero if anything fails — meant to be wired into a
team's CI so a bad custom pattern is caught before it's relied on.

Run via pytest (default in CI):
    pytest tests/test_validate_patterns_integration.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

_BINARY_CANDIDATES = [
    REPO_ROOT / "target" / "aarch64-apple-darwin" / "debug"   / "localforge",
    REPO_ROOT / "target" / "aarch64-apple-darwin" / "release" / "localforge",
    REPO_ROOT / "target" / "debug"                            / "localforge",
    REPO_ROOT / "target" / "release"                          / "localforge",
]


def _find_binary() -> Path:
    for p in _BINARY_CANDIDATES:
        if p.exists():
            return p
    pytest.skip(
        "localforge binary not found — run "
        "`cargo build --target aarch64-apple-darwin` first"
    )


@pytest.fixture(scope="session")
def binary() -> Path:
    return _find_binary()


def _run(binary: Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), "--validate-patterns"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_no_file_is_a_clean_noop(binary: Path, tmp_path: Path) -> None:
    r = _run(binary, tmp_path)
    assert r.returncode == 0
    assert "nothing to validate" in r.stdout


def test_empty_patterns_list_is_a_clean_noop(binary: Path, tmp_path: Path) -> None:
    (tmp_path / ".localforge").mkdir()
    (tmp_path / ".localforge" / "patterns.toml").write_text("patterns = []\n")
    r = _run(binary, tmp_path)
    assert r.returncode == 0
    assert "defines no patterns" in r.stdout


def test_valid_pattern_with_passing_tests(binary: Path, tmp_path: Path) -> None:
    (tmp_path / ".localforge").mkdir()
    (tmp_path / ".localforge" / "patterns.toml").write_text(
        '[[patterns]]\n'
        'pattern = "internal_[a-z]+_key_[0-9]{6}"\n'
        'label = "Internal Key Format"\n'
        'test_positive = ["internal_prod_key_123456"]\n'
        'test_negative = ["internal_key_abc"]\n'
    )
    r = _run(binary, tmp_path)
    assert r.returncode == 0
    assert "✓ Internal Key Format" in r.stdout
    assert "All custom patterns valid" in r.stdout


def test_broken_regex_fails_and_exits_nonzero(binary: Path, tmp_path: Path) -> None:
    (tmp_path / ".localforge").mkdir()
    (tmp_path / ".localforge" / "patterns.toml").write_text(
        '[[patterns]]\n'
        'pattern = "["\n'
        'label = "Broken Regex"\n'
    )
    r = _run(binary, tmp_path)
    assert r.returncode != 0
    assert "Broken Regex" in r.stdout
    assert "failed to compile" in r.stdout


def test_unmatched_positive_case_fails(binary: Path, tmp_path: Path) -> None:
    (tmp_path / ".localforge").mkdir()
    (tmp_path / ".localforge" / "patterns.toml").write_text(
        '[[patterns]]\n'
        'pattern = "always_wrong"\n'
        'label = "Bad Positive Case"\n'
        'test_positive = ["this will not match"]\n'
    )
    r = _run(binary, tmp_path)
    assert r.returncode != 0
    assert "Expected to match but did not" in r.stdout


def test_falsely_matched_negative_case_fails(binary: Path, tmp_path: Path) -> None:
    (tmp_path / ".localforge").mkdir()
    (tmp_path / ".localforge" / "patterns.toml").write_text(
        '[[patterns]]\n'
        'pattern = "always_wrong"\n'
        'label = "Bad Negative Case"\n'
        'test_negative = ["always_wrong matches this"]\n'
    )
    r = _run(binary, tmp_path)
    assert r.returncode != 0
    assert "Expected NOT to match but did" in r.stdout


def test_mixed_valid_and_invalid_reports_both(binary: Path, tmp_path: Path) -> None:
    (tmp_path / ".localforge").mkdir()
    (tmp_path / ".localforge" / "patterns.toml").write_text(
        '[[patterns]]\n'
        'pattern = "internal_[a-z]+_key_[0-9]{6}"\n'
        'label = "Valid Rule"\n'
        'test_positive = ["internal_prod_key_123456"]\n'
        '\n'
        '[[patterns]]\n'
        'pattern = "["\n'
        'label = "Invalid Rule"\n'
    )
    r = _run(binary, tmp_path)
    assert r.returncode != 0
    assert "✓ Valid Rule" in r.stdout
    assert "✗ Invalid Rule" in r.stdout
