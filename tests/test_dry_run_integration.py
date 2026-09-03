#!/usr/bin/env python3
"""
--dry-run binary integration tests.

`localforge --dry-run on|off` toggles a marker file at
$HOME/.localforge/dry_run. Runs with a fake HOME per test so this never
touches the real machine's LocalForge state.

Run via pytest (default in CI):
    pytest tests/test_dry_run_integration.py -v
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


def _run(binary: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
    )


def _marker(home: Path) -> Path:
    return home / ".localforge" / "dry_run"


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_default_is_off(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--dry-run")
    assert r.returncode == 0
    assert "OFF" in r.stdout
    assert not _marker(fake_home).exists()


def test_on_creates_marker(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--dry-run", "on")
    assert r.returncode == 0
    assert "ON" in r.stdout
    assert _marker(fake_home).exists()


def test_off_removes_marker(binary: Path, fake_home: Path) -> None:
    _run(binary, fake_home, "--dry-run", "on")
    assert _marker(fake_home).exists()

    r = _run(binary, fake_home, "--dry-run", "off")
    assert r.returncode == 0
    assert "OFF" in r.stdout
    assert not _marker(fake_home).exists()


def test_off_when_already_off_is_a_noop(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--dry-run", "off")
    assert r.returncode == 0
    assert not _marker(fake_home).exists()


def test_status_reflects_current_state(binary: Path, fake_home: Path) -> None:
    _run(binary, fake_home, "--dry-run", "on")
    r = _run(binary, fake_home, "--dry-run")
    assert "ON" in r.stdout


def test_invalid_value_errors(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--dry-run", "sideways")
    assert r.returncode != 0
