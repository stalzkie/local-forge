#!/usr/bin/env python3
"""
--status binary integration tests.

`localforge --status` prints a scriptable summary (hook state, dry-run mode,
registered repo count, Layer 2/3 availability, recent scans) without
launching the TUI. Runs with a fake HOME per test so this never touches the
real machine's LocalForge state.

Run via pytest (default in CI):
    pytest tests/test_status_integration.py -v
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


@pytest.fixture()
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _run(binary: Path, home: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_runs_clean_with_no_state(binary: Path, fake_home: Path, tmp_path: Path) -> None:
    r = _run(binary, fake_home, tmp_path, "--status")
    assert r.returncode == 0
    assert "Dry-run mode:        OFF" in r.stdout
    assert "Registered repos:    0" in r.stdout
    assert "No scan reports yet." in r.stdout


def test_reflects_dry_run_on(binary: Path, fake_home: Path, tmp_path: Path) -> None:
    _run(binary, fake_home, tmp_path, "--dry-run", "on")
    r = _run(binary, fake_home, tmp_path, "--status")
    assert r.returncode == 0
    assert "Dry-run mode:        ON" in r.stdout


def test_reflects_registered_repo_count(binary: Path, fake_home: Path, tmp_path: Path) -> None:
    repos_file = fake_home / ".localforge" / "repos"
    repos_file.parent.mkdir(parents=True, exist_ok=True)
    repos_file.write_text("/some/repo\n/another/repo\n")

    r = _run(binary, fake_home, tmp_path, "--status")
    assert r.returncode == 0
    assert "Registered repos:    2" in r.stdout


def test_outside_git_repo_reports_it(binary: Path, fake_home: Path, tmp_path: Path) -> None:
    r = _run(binary, fake_home, tmp_path, "--status")
    assert r.returncode == 0
    assert "not inside a git repository" in r.stdout


def test_lists_recent_scan_reports(binary: Path, fake_home: Path, tmp_path: Path) -> None:
    reports_dir = fake_home / ".localforge" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = reports_dir / "commit_20260101_000000_abc123.txt"
    report.write_text(
        "  2026-01-01 00:00:00 UTC  |  diff: abc123def456  |  model: test\n"
        "  Severity : HIGH\n"
        "  Summary  : hardcoded secret found\n"
        "  [1] leaked API key\n"
    )

    r = _run(binary, fake_home, tmp_path, "--status")
    assert r.returncode == 0
    assert "Last 1 scan(s):" in r.stdout
    assert "abc123de" in r.stdout
    assert "HIGH" in r.stdout


def test_does_not_launch_tui(binary: Path, fake_home: Path, tmp_path: Path) -> None:
    r = _run(binary, fake_home, tmp_path, "--status")
    assert r.returncode == 0
    assert "[LocalForge] Status" in r.stdout
