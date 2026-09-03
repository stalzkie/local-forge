#!/usr/bin/env python3
"""
--allow binary integration tests.

`localforge --allow PATH` is a convenience wrapper that appends PATH to
.localforgeignore at the repo root, so a developer who just got blocked for a
known false positive doesn't have to go find and hand-edit the file. Exercises
the actual binary against a real (throwaway) git repository.

Run via pytest (default in CI):
    pytest tests/test_allow_integration.py -v
"""

from __future__ import annotations

import json
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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _run(binary: Path, repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), *args], cwd=repo, capture_output=True, text=True
    )


@pytest.fixture(scope="session")
def binary() -> Path:
    return _find_binary()


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with a single clean commit on main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@localforge.dev")
    _git(repo, "config", "user.name", "LocalForge Test")
    (repo / "README.md").write_text("hello\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_creates_ignore_file(binary: Path, tmp_repo: Path) -> None:
    """A fresh repo with no .localforgeignore gets one created."""
    assert not (tmp_repo / ".localforgeignore").exists()

    r = _run(binary, tmp_repo, "--allow", "tests/fake_key.py")

    assert r.returncode == 0
    ignore_file = tmp_repo / ".localforgeignore"
    assert ignore_file.exists()
    assert "tests/fake_key.py" in ignore_file.read_text().splitlines()


def test_appends_without_clobbering(binary: Path, tmp_repo: Path) -> None:
    """A second --allow call appends rather than overwriting existing entries."""
    (tmp_repo / ".localforgeignore").write_text("existing/entry.py\n")

    r = _run(binary, tmp_repo, "--allow", "new/entry.py")

    assert r.returncode == 0
    lines = (tmp_repo / ".localforgeignore").read_text().splitlines()
    assert "existing/entry.py" in lines
    assert "new/entry.py" in lines


def test_idempotent_on_repeat(binary: Path, tmp_repo: Path) -> None:
    """Calling --allow twice with the same path must not duplicate the entry."""
    _run(binary, tmp_repo, "--allow", "tests/fake_key.py")
    r2 = _run(binary, tmp_repo, "--allow", "tests/fake_key.py")

    assert r2.returncode == 0
    lines = (tmp_repo / ".localforgeignore").read_text().splitlines()
    assert lines.count("tests/fake_key.py") == 1


def test_outside_git_repo_errors(binary: Path, tmp_path: Path) -> None:
    """--allow outside a git repo must fail loudly, not silently no-op."""
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    r = _run(binary, non_repo, "--allow", "foo.py")
    assert r.returncode != 0


def test_allow_unblocks_scan_pr(binary: Path, tmp_repo: Path) -> None:
    """End-to-end: a secret that blocks --scan-pr must pass after --allow."""
    _git(tmp_repo, "checkout", "-q", "-b", "feature")
    (tmp_repo / "config.py").write_text(
        'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n'
    )
    _git(tmp_repo, "add", "config.py")
    _git(tmp_repo, "commit", "-q", "-m", "add secret")

    blocked = _run(binary, tmp_repo, "--scan-pr", "main", "feature")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["blocked"] is True

    allow = _run(binary, tmp_repo, "--allow", "config.py")
    assert allow.returncode == 0
    _git(tmp_repo, "add", ".localforgeignore")
    _git(tmp_repo, "commit", "-q", "-m", "allow config.py")

    passed = _run(binary, tmp_repo, "--scan-pr", "main", "feature")
    assert passed.returncode == 0
    assert json.loads(passed.stdout)["blocked"] is False
