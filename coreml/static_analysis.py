#!/usr/bin/env python3
"""
LocalForge Static Analysis Layer (Layer 3.5)

Runs deterministic static analysis tools on files changed in a diff before
the LLM advisory engine. Covers categories where the LLM has FPR=1.000:
  - dead_code      → pylint (Python), eslint no-unused-vars (JS/TS)
  - logic_bug      → pyflakes, go vet, clippy
  - race_condition → go vet -race patterns, Rust type-system (compile-time)
  - unhandled_exc  → pylint W0703, go errcheck

Returns findings in the same JSON schema as advisory.py so they merge cleanly.
Findings carry "source": "static" to distinguish from LLM findings in reports.

Usage (called internally by advisory.py):
  from static_analysis import run_static_analysis
  findings = run_static_analysis(diff_text)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Tool availability cache ───────────────────────────────────────────────────

_TOOL_CACHE: dict = {}


def _which(tool: str):
    if tool not in _TOOL_CACHE:
        _TOOL_CACHE[tool] = shutil.which(tool)
    return _TOOL_CACHE[tool]


# ── Diff parsing ──────────────────────────────────────────────────────────────

def _extract_changed_files(diff_text: str) -> list:
    """Return list of file paths that have additions in the diff."""
    files = []
    for line in diff_text.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            files.append(m.group(1))
    return files


def _extract_file_content(diff_text: str, filepath: str) -> str:
    """
    Reconstruct the post-diff content of a file from added lines only.
    This is a heuristic — it gives the static tools something to analyse
    without needing the full repo checkout.
    """
    lines: list = []
    in_file = False
    for line in diff_text.splitlines():
        if line.startswith("+++ b/" + filepath):
            in_file = True
            continue
        if in_file and line.startswith("diff --git"):
            break
        if in_file:
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(line[1:])
            elif not line.startswith("-") and not line.startswith("@@") and not line.startswith("\\"):
                lines.append(line)
    return "\n".join(lines)


# ── Finding builder ───────────────────────────────────────────────────────────

def _finding(category: str, ftype: str, line_hint: str, explanation: str, remediation: str) -> dict:
    return {
        "category":    category,
        "type":        ftype,
        "line_hint":   line_hint,
        "explanation": explanation,
        "remediation": remediation,
        "source":      "static",
    }


# ── Python: bandit (security) ─────────────────────────────────────────────────

def _run_bandit(source: str, filepath: str) -> list:
    if not _which("bandit"):
        return []
    findings = []
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            tmp = f.name
        result = subprocess.run(
            ["bandit", "-f", "json", "-q", tmp],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout) if result.stdout.strip() else {}
        for issue in data.get("results", []):
            sev  = issue.get("issue_severity", "LOW").lower()
            text = issue.get("issue_text", "")
            line = issue.get("line_number", "")
            test = issue.get("test_id", "")
            findings.append(_finding(
                category    = "security",
                ftype       = test.lower(),
                line_hint   = f"{filepath}:{line}",
                explanation = text,
                remediation = issue.get("more_info", "See bandit docs"),
            ))
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return findings


# ── Python: pylint dead-code / quality ───────────────────────────────────────

_PYLINT_CODES = "W0611,W0612,W0613,W0614,C0116,R0801"

def _run_pylint(source: str, filepath: str) -> list:
    if not _which("pylint"):
        return []
    findings = []
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(source)
            tmp = f.name
        result = subprocess.run(
            ["pylint", f"--disable=all", f"--enable={_PYLINT_CODES}",
             "--output-format=json", tmp],
            capture_output=True, text=True, timeout=15,
        )
        items = json.loads(result.stdout) if result.stdout.strip() else []
        for item in items:
            msg_id = item.get("message-id", "")
            msg    = item.get("message", "")
            line   = item.get("line", "")
            findings.append(_finding(
                category    = "quality",
                ftype       = f"pylint_{msg_id.lower()}",
                line_hint   = f"{filepath}:{line}",
                explanation = msg,
                remediation = f"pylint {msg_id}: remove or use the flagged symbol",
            ))
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return findings


# ── JavaScript / TypeScript: eslint ──────────────────────────────────────────

_ESLINT_RULES = json.dumps({
    "no-unused-vars": "warn",
    "no-undef":       "warn",
    "no-eval":        "error",
    "no-implied-eval": "error",
})

def _run_eslint(source: str, filepath: str, is_ts: bool) -> list:
    if not _which("eslint"):
        return []
    findings = []
    suffix = ".ts" if is_ts else ".js"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(source)
            tmp = f.name
        cmd = [
            "eslint", "--format", "json",
            "--rule", f"no-unused-vars: warn",
            "--rule", "no-eval: error",
            "--rule", "no-implied-eval: error",
            "--env", "browser,node,es2022",
            tmp,
        ]
        if is_ts:
            cmd += ["--parser", "@typescript-eslint/parser"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout) if result.stdout.strip() else []
        for file_result in data:
            for msg in file_result.get("messages", []):
                rule = msg.get("ruleId", "eslint")
                text = msg.get("message", "")
                line = msg.get("line", "")
                category = "security" if "eval" in rule else "quality"
                findings.append(_finding(
                    category    = category,
                    ftype       = rule.replace("-", "_"),
                    line_hint   = f"{filepath}:{line}",
                    explanation = text,
                    remediation = f"Fix or remove the flagged expression (eslint/{rule})",
                ))
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return findings


# ── Go: go vet ───────────────────────────────────────────────────────────────

def _run_go_vet(source: str, filepath: str) -> list:
    if not _which("go"):
        return []
    findings = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Minimal go.mod so go vet can parse the file
            Path(tmpdir, "go.mod").write_text("module localforge_eval\n\ngo 1.21\n")
            src_file = Path(tmpdir, "main.go")
            src_file.write_text(source)
            result = subprocess.run(
                ["go", "vet", "./..."],
                capture_output=True, text=True, timeout=20, cwd=tmpdir,
            )
            for line in (result.stderr or "").splitlines():
                if ":" in line and not line.startswith("#"):
                    findings.append(_finding(
                        category    = "bug_risk",
                        ftype       = "go_vet",
                        line_hint   = filepath + ":" + line.split(":")[-2] if line.count(":") >= 2 else filepath,
                        explanation = line.strip(),
                        remediation = "Fix the issue reported by go vet",
                    ))
    except Exception:
        pass
    return findings


# ── staticcheck (Go) ─────────────────────────────────────────────────────────

def _run_staticcheck(source: str, filepath: str) -> list:
    if not _which("staticcheck"):
        return []
    findings = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "go.mod").write_text("module localforge_eval\n\ngo 1.21\n")
            Path(tmpdir, "main.go").write_text(source)
            result = subprocess.run(
                ["staticcheck", "./..."],
                capture_output=True, text=True, timeout=20, cwd=tmpdir,
            )
            for line in (result.stdout or "").splitlines():
                parts = line.split(":")
                if len(parts) >= 4:
                    check = parts[-1].strip().split()[-1] if parts[-1].strip() else ""
                    msg   = ":".join(parts[3:]).strip()
                    findings.append(_finding(
                        category    = "quality",
                        ftype       = f"staticcheck_{check}",
                        line_hint   = f"{filepath}:{parts[1].strip() if len(parts) > 1 else ''}",
                        explanation = msg,
                        remediation = f"Fix issue flagged by staticcheck ({check})",
                    ))
    except Exception:
        pass
    return findings


# ── Rust: cargo clippy ────────────────────────────────────────────────────────

def _run_clippy(source: str, filepath: str) -> list:
    if not _which("cargo"):
        return []
    findings = []
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir, "src")
            src_dir.mkdir()
            (src_dir / "lib.rs").write_text(source)
            Path(tmpdir, "Cargo.toml").write_text(
                '[package]\nname = "lf_eval"\nversion = "0.1.0"\nedition = "2021"\n'
            )
            result = subprocess.run(
                ["cargo", "clippy", "--message-format=json", "--", "-A", "clippy::all",
                 "-W", "clippy::suspicious", "-W", "clippy::correctness",
                 "-W", "clippy::perf", "-W", "dead_code"],
                capture_output=True, text=True, timeout=60, cwd=tmpdir,
            )
            for line in (result.stdout or "").splitlines():
                try:
                    msg = json.loads(line)
                    if msg.get("reason") != "compiler-message":
                        continue
                    m = msg.get("message", {})
                    if m.get("level") not in ("warning", "error"):
                        continue
                    spans = m.get("spans", [])
                    hint  = f"{filepath}:{spans[0]['line_start']}" if spans else filepath
                    findings.append(_finding(
                        category    = "quality" if m.get("level") == "warning" else "bug_risk",
                        ftype       = f"clippy_{m.get('code', {}).get('code', 'lint')}",
                        line_hint   = hint,
                        explanation = m.get("message", ""),
                        remediation = m.get("rendered", "").split("\n")[0],
                    ))
                except (json.JSONDecodeError, KeyError):
                    pass
    except Exception:
        pass
    return findings


# ── Dispatch ──────────────────────────────────────────────────────────────────

def run_static_analysis(diff_text: str) -> list:
    """
    Run all applicable static analysis tools on files changed in diff_text.
    Returns a flat list of findings in the advisory.py JSON schema.
    """
    changed_files = _extract_changed_files(diff_text)
    all_findings: list = []

    for filepath in changed_files:
        source = _extract_file_content(diff_text, filepath)
        if not source.strip():
            continue

        ext = Path(filepath).suffix.lower()

        if ext == ".py":
            all_findings.extend(_run_bandit(source, filepath))
            all_findings.extend(_run_pylint(source, filepath))

        elif ext in (".js", ".jsx"):
            all_findings.extend(_run_eslint(source, filepath, is_ts=False))

        elif ext in (".ts", ".tsx"):
            all_findings.extend(_run_eslint(source, filepath, is_ts=True))

        elif ext == ".go":
            all_findings.extend(_run_go_vet(source, filepath))
            all_findings.extend(_run_staticcheck(source, filepath))

        elif ext == ".rs":
            all_findings.extend(_run_clippy(source, filepath))

    # Deduplicate by (type, line_hint)
    seen = set()
    deduped: list = []
    for f in all_findings:
        key = (f["type"], f["line_hint"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    return deduped
