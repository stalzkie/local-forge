#!/usr/bin/env python3
"""
--scan-pr binary integration tests.

Exercises the actual `localforge --scan-pr BASE HEAD` CLI path end-to-end.
Unlike `--scan`, which reads a diff from stdin, `--scan-pr` shells out to
`git diff` itself, so these tests drive it against a real (throwaway) git
repository rather than synthetic diff text.

Run via pytest (default in CI):
    pytest tests/test_scan_pr_integration.py -v
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

# Binary locations tried in order (debug preferred in CI; release also accepted)
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


def _scan_pr(binary: Path, repo: Path, base: str, head: str) -> tuple[int, str]:
    r = subprocess.run(
        [str(binary), "--scan-pr", base, head],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return r.returncode, r.stdout


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

def test_no_diff_passes(binary: Path, tmp_repo: Path) -> None:
    """Identical base and head must not block, with empty findings/stats."""
    code, stdout = _scan_pr(binary, tmp_repo, "main", "main")
    result = json.loads(stdout)

    assert code == 0
    assert result["blocked"] is False
    assert result["blocked_by"] is None
    assert result["findings"] == []
    assert result["diff_stats"]["added_lines"] == 0


def test_secret_in_head_blocks(binary: Path, tmp_repo: Path) -> None:
    """A secret introduced on head must block with exit 1 and a Layer 1 finding."""
    _git(tmp_repo, "checkout", "-q", "-b", "feature")
    (tmp_repo / "config.py").write_text(
        'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n'
    )
    _git(tmp_repo, "add", "config.py")
    _git(tmp_repo, "commit", "-q", "-m", "add secret")

    code, stdout = _scan_pr(binary, tmp_repo, "main", "feature")
    result = json.loads(stdout)

    assert code == 1
    assert result["blocked"] is True
    assert result["blocked_by"] == "layer1"
    assert result["files_scanned"] == ["config.py"]
    assert any("AWS" in f["label"] for f in result["findings"])


def test_clean_feature_branch_passes(binary: Path, tmp_repo: Path) -> None:
    """Ordinary code changes with no secrets must pass."""
    _git(tmp_repo, "checkout", "-q", "-b", "feature-clean")
    (tmp_repo / "app.py").write_text("def add(a, b):\n    return a + b\n")
    _git(tmp_repo, "add", "app.py")
    _git(tmp_repo, "commit", "-q", "-m", "add helper")

    code, stdout = _scan_pr(binary, tmp_repo, "main", "feature-clean")
    result = json.loads(stdout)

    assert code == 0
    assert result["blocked"] is False
    assert result["files_scanned"] == ["app.py"]


def test_localforgeignore_respected(binary: Path, tmp_repo: Path) -> None:
    """A file matching a .localforgeignore pattern must be excluded from scanning."""
    _git(tmp_repo, "checkout", "-q", "-b", "feature-ignored")
    (tmp_repo / ".localforgeignore").write_text("fixtures/\n")
    (tmp_repo / "fixtures").mkdir()
    (tmp_repo / "fixtures" / "fake_key.py").write_text(
        'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n'
    )
    _git(tmp_repo, "add", "-A")
    _git(tmp_repo, "commit", "-q", "-m", "add ignored secret fixture")

    code, stdout = _scan_pr(binary, tmp_repo, "main", "feature-ignored")
    result = json.loads(stdout)

    assert code == 0
    assert result["blocked"] is False
    assert "fixtures/fake_key.py" in result["files_ignored"]
    assert "fixtures/fake_key.py" not in result["files_scanned"]


def test_invalid_ref_errors(binary: Path, tmp_repo: Path) -> None:
    """An unknown base/head ref must fail loudly, not silently pass."""
    r = subprocess.run(
        [str(binary), "--scan-pr", "main", "does-not-exist"],
        cwd=tmp_repo,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert r.stdout.strip() == ""  # no JSON success output on a git error
