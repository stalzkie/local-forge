#!/usr/bin/env python3
"""
Layer 1 binary integration tests — golden TP/FP set + latency gate.

Exercises the *actual* `localforge --scan` binary (not the Rust unit tests,
which call `scan()` directly without the CLI layer).  Pipes git diffs through
stdin and asserts:
  - exit 1 for every true-positive (secret in a + line)  → commit must block
  - exit 0 for every false-positive case                  → commit must pass
  - wall time per scan < LATENCY_LIMIT_MS                 → no perf regression

Run standalone:
    python3 tests/test_l1_integration.py [--binary PATH]

Run via pytest (default in CI):
    pytest tests/test_l1_integration.py -v
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
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

# Per-scan wall-time limit including binary startup.  Pure regex is µs-fast;
# the limit covers process spawn overhead and gives plenty of headroom.
LATENCY_LIMIT_MS = 500


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_binary() -> Path:
    for p in _BINARY_CANDIDATES:
        if p.exists():
            return p
    pytest.skip(
        "localforge binary not found — run "
        "`cargo build --target aarch64-apple-darwin` first"
    )


def _make_diff(filename: str, added: list[str], removed: list[str] | None = None) -> str:
    """Minimal unified diff with proper + / - lines."""
    plus  = "\n".join(f"+{l}" for l in added)
    minus = "\n".join(f"-{l}" for l in (removed or []))
    n_add = len(added)
    n_rem = len(removed) if removed else 0
    return (
        f"diff --git a/{filename} b/{filename}\n"
        f"--- a/{filename}\n"
        f"+++ b/{filename}\n"
        f"@@ -{n_rem},0 +1,{n_add} @@\n"
        f"{minus}\n{plus}\n"
    )


def _scan(binary: Path, diff: str) -> tuple[int, float]:
    """Return (exit_code, wall_time_ms)."""
    t0 = time.perf_counter()
    r  = subprocess.run(
        [str(binary), "--scan"],
        input=diff,
        capture_output=True,
        text=True,
    )
    ms = (time.perf_counter() - t0) * 1000
    return r.returncode, ms


# ── True-positive fixtures — binary MUST exit 1 ───────────────────────────────
#
# Patterns mirror ast_validator.rs test helpers.  All values are fake/example
# keys that match the format but are not real credentials.

TP_CASES: list[tuple[str, str, list[str]]] = [
    ("aws_access_key",       "config.py",         ['AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"']),
    ("aws_secret_key",       "config.py",         ['AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"']),
    ("gcp_api_key",          "app.js",            ['const GCP_KEY = "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXyz12345"']),
    ("stripe_live_key",      "payments.py",       ['STRIPE_SECRET = "sk_live_51ABCDEFGHIJKLMNOPQRSTUVWXyz0123"']),
    ("stripe_restricted_key","billing.py",        ['key = "rk_live_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab"']),
    ("github_pat_classic",   "deploy.sh",         ['GITHUB_TOKEN="ghp_R8mxK2VqJzL9WnP4sT6uY1cB3dA0eF5gHi"']),
    ("github_fine_grained",  "ci.env",            ['GH_TOKEN="github_pat_11AABBCCDD_xYzABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop"']),
    ("github_actions_token", "workflow.yml",      ['token: gha_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd']),
    ("slack_bot_token",      "notify.py",         ['SLACK_TOKEN = "xoxb-123456789012-123456789012-ABCDEFabcdefABCDEFabcdef"']),
    ("sendgrid_key",         "mailer.py",         ['SG_KEY = "SG.ABCDEFGHIJKLMNOPQRSTUVWX.YZabcdefghijklmnopqrstuvwxyz0123456789ABCD"']),
    ("npm_token",            ".npmrc",            ['//registry.npmjs.org/:_authToken=npm_ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567890abc']),
    ("pypi_token",           "publish.sh",        ['PYPI_TOKEN="pypi-AgEIcHlwaS5vcmcABCDEFGHIJKLMNOPQRSTUVWXyz"']),
    ("huggingface_token",    "train.py",          ['HF_TOKEN = "hf_ABCDEFGHIJKLMNOPQRSTUVWXyz123456789"']),
    ("anthropic_key",        "llm.py",            ['client = Anthropic(api_key="sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijkl-XXXXXXXX")']),
    ("openai_key",           "gpt.ts",            ['const openai = new OpenAI({ apiKey: "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnop" })']),
    ("shopify_secret",       "webhook.rb",        ['SHOPIFY_SECRET = "shpss_ABCDEF1234567890abcdef1234567890"']),
    ("twilio_sid",           "sms.py",            ['ACCOUNT_SID = "ACabcdef1234567890abcdef1234567890ab"']),
    ("rsa_private_key",      "server.pem",        ["-----BEGIN RSA PRIVATE KEY-----",
                                                   "MIIEowIBAAKCAQEA2a2rwplBQLzZB/FAKE==",
                                                   "-----END RSA PRIVATE KEY-----"]),
    ("openssh_private_key",  "id_rsa",            ["-----BEGIN OPENSSH PRIVATE KEY-----",
                                                   "b3BlbnNzaC1rZXktdjEAAAAA",
                                                   "-----END OPENSSH PRIVATE KEY-----"]),
    ("high_entropy_bearer",  "api_client.py",     ["Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIn0.FAKE"]),
    ("gcp_service_account",  "credentials.json",  ['{ "type": "service_account", "project_id": "my-proj", "private_key_id": "abc123" }']),
    ("db_password_inline",   "settings.py",       ['+DATABASE_PASSWORD=supersecretvalue123abc']),
]


# ── False-positive fixtures — binary MUST exit 0 ──────────────────────────────

FP_CASES: list[tuple[str, str, list[str], list[str] | None]] = [
    # (label, filename, added_lines, removed_lines)

    # Stripe test keys are explicitly allowed
    ("stripe_test_key",      "test_payments.py",  ['STRIPE_SK = "sk_test_ABC123"'],                  None),

    # Environment-variable references — value never appears in the diff
    ("env_var_os_getenv",    "config.py",         ['API_KEY = os.getenv("API_KEY")'],                None),
    ("env_var_os_environ",   "config.py",         ['SECRET = os.environ["SECRET"]'],                 None),
    ("env_var_shell_ref",    "deploy.sh",         ['API_KEY=$MY_API_KEY'],                           None),

    # Short bearer — below entropy threshold
    ("short_bearer",         "api.py",            ["Authorization: Bearer short"],                   None),

    # Placeholder / template values
    ("placeholder_yaml",     "config.example.yml",["api_key: YOUR_API_KEY_HERE"],                   None),
    ("placeholder_brackets", "README.md",         ["token: <REPLACE_WITH_YOUR_TOKEN>"],             None),

    # Secrets appearing only in removed lines (- lines) — L1 must not scan these
    ("secret_on_minus_line", "old.py",            ["# line was removed"],
                                                  ['GITHUB_TOKEN="ghp_R8mxK2VqJzL9WnP4sT6uY1cB3dA0eF5gHi"']),

    # Clean code, no secrets
    ("clean_rust",           "main.rs",           ['fn main() { println!("hello"); }'],             None),
    ("clean_python",         "app.py",            ["def greet(name: str) -> str:",
                                                   '    return f"Hello, {name}"'],                  None),
    ("clean_typescript",     "util.ts",           ["const add = (a: number, b: number) => a + b;"], None),
    ("clean_go",             'main.go',           ['func main() { fmt.Println("hello") }'],         None),
    ("clean_swift",          "App.swift",         ['func greet(_ name: String) -> String { return "Hello \\(name)" }'], None),
]


# ── Pytest parametrized tests ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def binary() -> Path:
    return _find_binary()


@pytest.mark.parametrize("label,filename,lines", TP_CASES, ids=[t[0] for t in TP_CASES])
def test_true_positive(binary: Path, label: str, filename: str, lines: list[str]) -> None:
    """Secrets in + lines must cause exit 1 (blocked)."""
    diff = _make_diff(filename, lines)
    code, ms = _scan(binary, diff)
    assert ms < LATENCY_LIMIT_MS, f"{label}: scan took {ms:.0f}ms (limit {LATENCY_LIMIT_MS}ms)"
    assert code == 1, f"{label}: expected exit 1 (blocked), got {code}"


@pytest.mark.parametrize("label,filename,added,removed", FP_CASES, ids=[f[0] for f in FP_CASES])
def test_false_positive(binary: Path, label: str, filename: str,
                        added: list[str], removed: list[str] | None) -> None:
    """Clean diffs and env-var references must cause exit 0 (pass)."""
    diff = _make_diff(filename, added, removed)
    code, ms = _scan(binary, diff)
    assert ms < LATENCY_LIMIT_MS, f"{label}: scan took {ms:.0f}ms (limit {LATENCY_LIMIT_MS}ms)"
    assert code == 0, f"{label}: expected exit 0 (pass), got {code}"


# ── Standalone entry point ─────────────────────────────────────────────────────

def _run_standalone(binary: Path) -> bool:
    failures: list[str] = []

    def check(label: str, diff: str, want: int) -> None:
        code, ms = _scan(binary, diff)
        tag = "PASS" if (code == want and ms < LATENCY_LIMIT_MS) else "FAIL"
        note = f"{ms:.0f}ms"
        if code != want:
            note += f"  expected exit {want}, got {code}"
            failures.append(f"{label}: expected exit {want}, got {code}")
        if ms >= LATENCY_LIMIT_MS:
            note += f"  SLOW (>{LATENCY_LIMIT_MS}ms)"
            failures.append(f"{label}: {ms:.0f}ms >= {LATENCY_LIMIT_MS}ms limit")
        print(f"  [{tag}] {label:<40} {note}")

    print(f"\nBinary: {binary}\n")

    print("── True positives (must exit 1) " + "─" * 38)
    for label, filename, lines in TP_CASES:
        check(label, _make_diff(filename, lines), 1)

    print("\n── False positives (must exit 0) " + "─" * 37)
    for label, filename, added, removed in FP_CASES:
        check(label, _make_diff(filename, added, removed), 0)

    total = len(TP_CASES) + len(FP_CASES)
    if failures:
        print(f"\nFAILED — {len(failures)}/{total}:")
        for f in failures:
            print(f"  • {f}")
        return False
    print(f"\nPASSED — {total}/{total}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, default=None)
    args = parser.parse_args()

    b = args.binary or next(
        (p for p in _BINARY_CANDIDATES if p.exists()), None
    )
    if b is None or not b.exists():
        print("ERROR: binary not found. Run: cargo build --target aarch64-apple-darwin")
        sys.exit(2)

    sys.exit(0 if _run_standalone(b) else 1)
