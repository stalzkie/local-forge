#!/usr/bin/env python3
"""
--daemon binary integration tests, plus a direct check of coreml/daemon.py's
socket protocol.

`localforge --daemon start|stop` controls the warm-model daemon at
$HOME/.localforge/daemon.sock. Runs with a fake HOME per test so this never
touches the real machine's LocalForge state or a real daemon instance.

Run via pytest (default in CI):
    pytest tests/test_daemon_integration.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DAEMON_SCRIPT = REPO_ROOT / "coreml" / "daemon.py"

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
def fake_home() -> Path:
    # Deliberately NOT pytest's tmp_path: it nests under
    # /private/var/folders/.../pytest-of-<user>/pytest-N/<test-name>0/,
    # routinely 120+ chars deep. A Unix domain socket path is capped at
    # ~104 bytes (sockaddr_un.sun_path on macOS/BSD) — over that, bind()
    # fails with OSError, which the daemon swallows and exits silently
    # (correct behavior for a real too-long path, but it means every test
    # here would see "daemon never starts" for a reason with nothing to do
    # with the code under test). A short /tmp dir keeps the path bindable.
    home = Path(tempfile.mkdtemp(prefix="lf-", dir="/tmp"))
    (home / ".localforge" / "coreml").mkdir(parents=True)
    # Point the fake install at the real daemon.py so it can actually bind
    # a socket and respond to ping, without any ML deps being present.
    (home / ".localforge" / "coreml" / "daemon.py").write_text(DAEMON_SCRIPT.read_text())
    try:
        yield home
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _run(binary: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )


def _socket_path(home: Path) -> Path:
    return home / ".localforge" / "daemon.sock"


def _wait_for(predicate, timeout=5.0, interval=0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ── CLI tests ─────────────────────────────────────────────────────────────────

def test_status_when_not_running(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--daemon")
    assert r.returncode == 0
    assert "not running" in r.stdout


def test_start_then_status_running(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--daemon", "start")
    assert r.returncode == 0
    assert _wait_for(lambda: _socket_path(fake_home).exists())

    r2 = _run(binary, fake_home, "--daemon")
    assert "running" in r2.stdout and "not running" not in r2.stdout

    _run(binary, fake_home, "--daemon", "stop")


def test_stop_when_not_running_is_a_noop(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--daemon", "stop")
    assert r.returncode == 0
    assert "was not running" in r.stdout


def test_start_then_stop_removes_socket(binary: Path, fake_home: Path) -> None:
    _run(binary, fake_home, "--daemon", "start")
    assert _wait_for(lambda: _socket_path(fake_home).exists())

    r = _run(binary, fake_home, "--daemon", "stop")
    assert r.returncode == 0
    assert _wait_for(lambda: not _socket_path(fake_home).exists())


def test_invalid_value_errors(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--daemon", "sideways")
    assert r.returncode != 0


def test_status_reports_daemon_line(binary: Path, fake_home: Path) -> None:
    r = _run(binary, fake_home, "--status")
    assert r.returncode == 0
    assert "Warm-model daemon:" in r.stdout


# ── Direct socket protocol tests ────────────────────────────────────────────────

def _request(sock_path: Path, payload: dict, timeout: float = 5.0) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(str(sock_path))
    s.sendall((json.dumps(payload) + "\n").encode())
    s.shutdown(socket.SHUT_WR)
    chunks = []
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    return json.loads(b"".join(chunks).decode())


def test_ping_responds_ok(binary: Path, fake_home: Path) -> None:
    _run(binary, fake_home, "--daemon", "start")
    assert _wait_for(lambda: _socket_path(fake_home).exists())

    resp = _request(_socket_path(fake_home), {"cmd": "ping"})
    assert resp == {"ok": True}

    _run(binary, fake_home, "--daemon", "stop")


def test_infer_degrades_gracefully_without_model(binary: Path, fake_home: Path) -> None:
    _run(binary, fake_home, "--daemon", "start")
    assert _wait_for(lambda: _socket_path(fake_home).exists())

    resp = _request(_socket_path(fake_home), {"cmd": "infer", "diff": "password = 'x'"})
    # No CoreML model installed under fake_home — daemon must report an
    # error, never crash or hang the connection.
    assert "error" in resp

    _run(binary, fake_home, "--daemon", "stop")


def test_unknown_cmd_returns_error(binary: Path, fake_home: Path) -> None:
    _run(binary, fake_home, "--daemon", "start")
    assert _wait_for(lambda: _socket_path(fake_home).exists())

    resp = _request(_socket_path(fake_home), {"cmd": "not_a_real_command"})
    assert "error" in resp

    _run(binary, fake_home, "--daemon", "stop")
