#!/usr/bin/env python3
"""
LocalForge Layer 3 — Qwen2.5-Coder advisory engine.

Performs a full code review on every commit diff covering:
  - Security vulnerabilities (secrets, injection, insecure crypto, path traversal)
  - Code quality (dead/orphan functions, unused vars, complexity, duplicate code)
  - Bug risks (off-by-one, null dereference, unhandled errors, logic flaws)

Never blocks a commit. All findings for a single run are written to ONE shared
report file (--report-file), with a clear header and separator between sections.

Usage:
  python3 coreml/advisory.py "<diff text>" [--log-dir <path>] [--report-file <path>]

Exit codes:
  0 — report written (or clean)
  1 — internal error
"""

import sys
import os
import re
import json
import argparse
import datetime
import hashlib

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG = os.path.join(os.path.expanduser("~"), ".localforge", "reports")

def _find_model_dir():
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".localforge", "qwen2.5-coder-1.5b-4bit"),
        os.path.join(SCRIPT_DIR, "qwen2.5-coder-1.5b-4bit"),
        os.path.join(SCRIPT_DIR, "..", "coreml", "qwen2.5-coder-1.5b-4bit"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return os.path.abspath(c)
    return candidates[0]

MODEL_DIR = _find_model_dir()

# ── Language detection ────────────────────────────────────────────────────────

LANG_PATTERNS = [
    (r'\.py\b',              "Python"),
    (r'\.tsx?\b',            "TypeScript/JavaScript"),
    (r'\.jsx?\b',            "JavaScript"),
    (r'\.java\b',            "Java"),
    (r'\.go\b',              "Go"),
    (r'\.rs\b',              "Rust"),
    (r'\.cs\b',              "C#"),
    (r'\.php\b',             "PHP"),
    (r'\.rb\b',              "Ruby"),
    (r'\.swift\b',           "Swift"),
    (r'\.kt\b',              "Kotlin"),
    (r'\.(sql|psql)\b',      "SQL"),
    (r'\.(sh|bash|zsh)\b',   "Shell"),
    (r'\.(yaml|yml)\b',      "YAML"),
    (r'\.tf\b',              "Terraform"),
    (r'\.(c|cpp|h|hpp)\b',   "C/C++"),
]

def detect_languages(diff_text):
    found = []
    for pat, lang in LANG_PATTERNS:
        if re.search(r'diff --git.*' + pat, diff_text):
            if lang not in found:
                found.append(lang)
    return found or ["unknown"]

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are LocalForge, an expert security-focused code reviewer embedded in a developer's git pre-commit hook.
You receive git diffs where lines starting with '+' are ADDITIONS and lines starting with '-' are DELETIONS.
Only additions can introduce new issues — do NOT flag lines that are being removed.

Review diffs for THREE categories only:
1. SECURITY — hardcoded secrets/credentials, SQL/command/XSS injection, insecure crypto (MD5/SHA1/DES/RC4), unsafe deserialization, disabled TLS verification, path traversal, SSRF
2. QUALITY — dead or unreachable functions never called in the diff, unused variables/imports, duplicate logic blocks, overly complex conditionals
3. BUG_RISK — off-by-one errors, unhandled None/null/error returns, logic inversions (wrong boolean), integer overflow/underflow, race conditions on shared state

Rules:
- ONLY flag lines beginning with '+' (additions). Never flag '-' lines.
- Be specific: quote the exact added line or snippet.
- If nothing is wrong, return severity "clean" and empty findings array.
- Do NOT invent issues not present in the diff.
- Always respond with valid JSON only — no markdown, no prose outside the JSON."""

REVIEW_PROMPT = """You are reviewing a git diff. Language(s): {languages}.

Each line starting with '+' is a NEW addition. Lines starting with '-' are being DELETED (ignore them for finding new issues).

Example of correct behavior:
- diff line: `-password = "old_secret"` → IGNORE (being removed)
- diff line: `+password = "new_hardcoded"` → FLAG as security issue

DIFF TO REVIEW:
{diff}

Respond ONLY with this exact JSON structure:
{{
  "severity": "high",
  "summary": "One sentence: what this diff does and the most critical issue found.",
  "findings": [
    {{
      "category": "security",
      "type": "hardcoded_secret",
      "line_hint": "exact added line from diff",
      "explanation": "why this is a problem",
      "remediation": "concrete one-line fix"
    }}
  ]
}}

Severity levels: "high" (exploitable/crash), "medium" (likely bug/security concern), "low" (quality/minor risk), "clean" (no issues).
List at most 5 findings, highest severity first. Empty findings array if clean."""

# ── Diff chunking ─────────────────────────────────────────────────────────────

def extract_added_lines(diff_text):
    """Return only the added lines from the diff, preserving file context headers."""
    lines = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git") or line.startswith("@@") or line.startswith("+++"):
            lines.append(line)
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append(line)
    return "\n".join(lines)

def chunk_diff(diff_text, max_chars=3500):
    """Split large diffs into chunks at file boundaries."""
    if len(diff_text) <= max_chars:
        return [diff_text]
    chunks, current = [], []
    current_len = 0
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git") and current_len > max_chars // 2:
            chunks.append("".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks

# ── Inference ─────────────────────────────────────────────────────────────────

def load_model(model_dir):
    from mlx_lm import load
    return load(model_dir)

def run_inference(model, tokenizer, diff_text, languages):
    from mlx_lm import generate

    # Focus on added lines to reduce noise and stay within token budget
    focused = extract_added_lines(diff_text)
    if len(focused) < 50:
        focused = diff_text  # too short after filtering; use full diff

    prompt_text = REVIEW_PROMPT.format(
        languages=", ".join(languages),
        diff=focused[:3800],
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_text},
    ]
    formatted = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    # Increased token budget: 1024 covers ~5 findings cleanly
    raw = generate(model, tokenizer, prompt=formatted, max_tokens=1024, verbose=False)
    raw = raw.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()

    # Strip markdown fences if model wraps output
    if "```" in raw:
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip()

    # Extract outermost {...} with brace-depth tracking
    start = raw.find("{")
    if start == -1:
        return None, raw

    depth, end = 0, -1
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        # Model truncated — try to recover by closing open braces
        open_braces = depth
        recovered = raw[start:] + ("}" * open_braces)
        try:
            return json.loads(recovered), None
        except json.JSONDecodeError:
            return None, raw[start:]

    try:
        return json.loads(raw[start:end]), None
    except json.JSONDecodeError:
        return None, raw[start:end]

def merge_findings(chunk_results):
    """Merge findings from multiple diff chunks into one result, deduplicating."""
    all_findings = []
    seen = set()
    highest_severity = "clean"
    severity_rank = {"high": 3, "medium": 2, "low": 1, "clean": 0}
    summaries = []

    for result in chunk_results:
        if not result:
            continue
        sev = result.get("severity", "clean")
        if severity_rank.get(sev, 0) > severity_rank.get(highest_severity, 0):
            highest_severity = sev
        summaries.append(result.get("summary", ""))
        for f in result.get("findings", []):
            key = f.get("type", "") + f.get("line_hint", "")[:40]
            if key not in seen:
                seen.add(key)
                all_findings.append(f)

    # Sort: security > bug_risk > quality, cap at 7 findings across all chunks
    cat_rank = {"security": 3, "bug_risk": 2, "quality": 1}
    all_findings.sort(key=lambda f: cat_rank.get(f.get("category", ""), 0), reverse=True)
    all_findings = all_findings[:7]

    summary = summaries[0] if summaries else "No issues detected."
    return {
        "severity": highest_severity,
        "summary":  summary,
        "findings": all_findings,
    }

# ── Report writing — ONE file per commit run ──────────────────────────────────

def write_report(result, diff_text, log_dir, report_file=None):
    """
    All findings for one commit run go into a single file.
    If --report-file is given, append to that file (the hook pre-creates it with a header).
    Otherwise create a new timestamped file.
    """
    os.makedirs(log_dir, exist_ok=True)
    diff_hash = hashlib.sha1(diff_text.encode()).hexdigest()[:10]
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if report_file:
        report_path = report_file
        is_new = not os.path.exists(report_path)
    else:
        ts_file = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = os.path.join(log_dir, f"commit_{ts_file}_{diff_hash}.txt")
        is_new = True

    severity = result.get("severity", "unknown").upper()
    summary  = result.get("summary", "")
    findings = result.get("findings", [])

    lines = []

    if is_new:
        lines.append("=" * 70)
        lines.append("  LocalForge Security & Code Assessment")
        lines.append(f"  {timestamp}")
        lines.append(f"  Diff hash : {diff_hash}")
        lines.append(f"  Model     : Qwen2.5-Coder-1.5B (Layer 3 advisory)")
        lines.append("=" * 70)
        lines.append("")

    lines.append(f"  Severity : {severity}")
    lines.append(f"  Summary  : {summary}")
    lines.append("")

    if findings:
        lines.append(f"  Findings ({len(findings)}):")
        lines.append("")
        for i, f in enumerate(findings, 1):
            cat         = f.get("category", "general").upper()
            ftype       = f.get("type", "unknown")
            line_hint   = f.get("line_hint", "").strip()
            explanation = f.get("explanation", "")
            remediation = f.get("remediation", "")

            lines.append(f"  [{i}] [{cat}] {ftype}")
            if line_hint:
                lines.append(f"      Code    : {line_hint}")
            lines.append(f"      Issue   : {explanation}")
            lines.append(f"      Fix     : {remediation}")
            lines.append("")
    else:
        lines.append("  No issues found.")
        lines.append("")

    lines.append("─" * 70)
    lines.append("")

    with open(report_path, "a") as fh:
        fh.write("\n".join(lines) + "\n")

    return report_path

# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("diff", help="Staged diff text to analyse")
    p.add_argument("--log-dir", default=DEFAULT_LOG)
    p.add_argument("--report-file", default=None,
                   help="Append all findings to this single .txt file (one file per commit)")
    return p.parse_args()


def main():
    args = parse_args()
    diff_text = args.diff

    if not os.path.isdir(MODEL_DIR):
        print(json.dumps({"error": f"Qwen model not found at {MODEL_DIR}"}))
        sys.exit(1)

    try:
        model, tokenizer = load_model(MODEL_DIR)
    except Exception as e:
        print(json.dumps({"error": f"Model load failed: {e}"}))
        sys.exit(1)

    languages = detect_languages(diff_text)
    chunks    = chunk_diff(diff_text)
    results   = []

    for chunk in chunks:
        result, raw = run_inference(model, tokenizer, chunk, languages)
        if result is None:
            # Non-fatal: use a fallback parse-error finding
            result = {
                "severity": "low",
                "summary":  "Advisory engine returned unstructured output for this chunk.",
                "findings": [{
                    "category": "quality", "type": "parse_error",
                    "line_hint": "", "explanation": (raw or "empty")[:200],
                    "remediation": "Review this diff chunk manually.",
                }],
            }
        results.append(result)

    merged      = merge_findings(results)
    report_path = write_report(merged, diff_text, args.log_dir, args.report_file)

    output = {
        "severity":    merged.get("severity", "unknown"),
        "summary":     merged.get("summary", ""),
        "findings":    merged.get("findings", []),
        "report_path": report_path,
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
