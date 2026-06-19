#!/usr/bin/env python3
"""
LocalForge Layer 3 — Qwen2.5-Coder advisory engine.

Performs a full code review on every commit diff covering:
  - Security vulnerabilities (secrets, injection, insecure patterns)
  - Code quality (dead/orphan functions, unused vars, complexity)
  - Bug risks (off-by-one, null dereference, unhandled errors, logic flaws)

Never blocks a commit. Writes a JSON report and prints a one-line summary.

Usage:
  python3 coreml/advisory.py "<diff text>" [--log-dir <path>]

Exit codes:
  0 — report written (or clean)
  1 — internal error

Output (stdout, one JSON line):
  {"severity": "high|medium|low|clean", "summary": "...", "findings": [...], "report_path": "..."}
"""

import sys
import os
import json
import argparse
import datetime
import hashlib

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG = os.path.join(os.path.expanduser("~"), ".localforge", "reports")

def _find_model_dir():
    home = os.path.expanduser("~")
    candidates = [
        # 1. ~/.localforge/qwen2.5-coder-1.5b-4bit  (installed via --install)
        os.path.join(home, ".localforge", "qwen2.5-coder-1.5b-4bit"),
        # 2. Next to this script (repo coreml/ or bundle Resources/coreml/)
        os.path.join(SCRIPT_DIR, "qwen2.5-coder-1.5b-4bit"),
        # 3. Repo root coreml/ when called from two levels up
        os.path.join(SCRIPT_DIR, "..", "coreml", "qwen2.5-coder-1.5b-4bit"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return os.path.abspath(c)
    return candidates[0]  # return preferred install path for the error message

MODEL_DIR = _find_model_dir()

SYSTEM_PROMPT = """You are LocalForge, an expert code reviewer embedded in a developer's git workflow.
You review staged diffs for three categories of issues:
1. SECURITY — hardcoded secrets, injection risks, insecure crypto, unsafe deserialization, path traversal, etc.
2. QUALITY — dead/orphan functions never called, unused variables, overly complex logic, poor naming, duplicate code.
3. BUG_RISK — off-by-one errors, unhandled error/exception paths, null/None dereferences, logic inversions, race conditions.

Be concise, specific, and actionable. Reference exact function names or line snippets when possible.
Always respond in valid JSON with no extra text outside the JSON object."""

REVIEW_PROMPT = """Review this staged git diff and identify issues across all three categories.

DIFF:
{diff}

Respond ONLY with this JSON object (no markdown, no extra text):
{{
  "severity": "high" | "medium" | "low" | "clean",
  "summary": "<one sentence overall assessment>",
  "findings": [
    {{
      "category": "security" | "quality" | "bug_risk",
      "type": "<specific issue type, e.g. hardcoded_secret / dead_function / unhandled_exception>",
      "line_hint": "<the relevant code snippet from the diff>",
      "explanation": "<why this is a problem>",
      "remediation": "<concrete fix>"
    }}
  ]
}}

Rules:
- severity is the highest severity across all findings
- "high": exploitable security issue or near-certain crash
- "medium": likely bug or meaningful security concern
- "low": code quality issue or minor risk
- "clean": no issues found
- List at most 5 findings, prioritised by severity
- If no issues found: severity "clean", empty findings array, summary "No issues detected."
- Do NOT invent issues that aren't in the diff"""


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("diff", help="Staged diff text to analyse")
    p.add_argument("--log-dir", default=DEFAULT_LOG)
    p.add_argument("--report-file", default=None,
                   help="Write report to this specific .txt path (shared across layers for one commit)")
    return p.parse_args()


def load_model(model_dir):
    from mlx_lm import load
    return load(model_dir)


def run_inference(model, tokenizer, diff_text):
    from mlx_lm import generate

    prompt_text = REVIEW_PROMPT.format(diff=diff_text[:4000])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_text},
    ]
    formatted = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    raw = generate(model, tokenizer, prompt=formatted, max_tokens=768, verbose=False)
    raw = raw.replace("<|im_end|>", "").strip()

    # Strip markdown code fences if present
    if "```" in raw:
        lines = raw.split("\n")
        raw = "\n".join(
            l for l in lines
            if not l.strip().startswith("```")
        ).strip()

    # Find outermost { ... } with brace matching
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
        return None, raw

    try:
        return json.loads(raw[start:end]), None
    except json.JSONDecodeError:
        return None, raw[start:end]


def write_report(result, diff_text, log_dir, report_file=None):
    os.makedirs(log_dir, exist_ok=True)
    diff_hash = hashlib.sha1(diff_text.encode()).hexdigest()[:10]
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if report_file:
        report_path = report_file
    else:
        ts_file = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = os.path.join(log_dir, f"commit_{ts_file}_{diff_hash}.txt")

    severity  = result.get("severity", "unknown").upper()
    summary   = result.get("summary", "")
    findings  = result.get("findings", [])

    lines = []
    lines.append("=" * 70)
    lines.append(f"  LocalForge Code Assessment")
    lines.append(f"  {timestamp}  |  diff: {diff_hash}  |  model: Qwen2.5-Coder-1.5B")
    lines.append("=" * 70)
    lines.append(f"  Severity : {severity}")
    lines.append(f"  Summary  : {summary}")
    lines.append("")

    if findings:
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

    lines.append("-" * 70)
    lines.append("")

    # Append so multiple layer runs in one commit accumulate in the same file
    with open(report_path, "a") as f:
        f.write("\n".join(lines) + "\n")

    return report_path


def main():
    args = parse_args()
    diff_text = args.diff

    if not os.path.isdir(MODEL_DIR):
        error = {"error": f"Qwen model not found at {MODEL_DIR}"}
        print(json.dumps(error))
        sys.exit(1)

    try:
        model, tokenizer = load_model(MODEL_DIR)
    except Exception as e:
        print(json.dumps({"error": f"Model load failed: {e}"}))
        sys.exit(1)

    result, raw = run_inference(model, tokenizer, diff_text)

    if result is None:
        result = {
            "severity": "low",
            "summary":  "Advisory engine returned unstructured output.",
            "findings": [{"category": "quality", "type": "parse_error", "line_hint": "",
                          "explanation": raw or "empty", "remediation": "Review diff manually."}],
        }

    report_path = write_report(result, diff_text, args.log_dir, args.report_file)

    output = {
        "severity":    result.get("severity", "unknown"),
        "summary":     result.get("summary", ""),
        "findings":    result.get("findings", []),
        "report_path": report_path,
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
