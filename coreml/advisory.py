#!/usr/bin/env python3
"""
LocalForge Layer 3 — Qwen2.5-Coder advisory engine.

Called by advisory_engine.rs as a non-blocking subprocess AFTER the commit
succeeds. Writes a JSON advisory report to a local log file and prints a
one-line summary to stdout.

Usage:
  python3 coreml/advisory.py "<diff text>" [--log-dir <path>]

Exit codes:
  0 — clean or advisory written successfully
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
MODEL_DIR   = os.path.join(SCRIPT_DIR, "qwen2.5-coder-1.5b-4bit")
DEFAULT_LOG = os.path.join(os.path.expanduser("~"), ".localforge", "advisory_log")

SYSTEM_PROMPT = """You are LocalForge, a senior application security engineer.
Your job is to review code diffs for security issues.
Be concise, precise, and developer-friendly.
Always respond in valid JSON with no extra text."""

REVIEW_PROMPT = """Review this code diff for security vulnerabilities.

DIFF:
{diff}

Respond ONLY with a JSON object in this exact format:
{{
  "severity": "high" | "medium" | "low" | "clean",
  "summary": "<one sentence describing the overall finding>",
  "findings": [
    {{
      "type": "<vulnerability type>",
      "line_hint": "<relevant code snippet>",
      "explanation": "<why this is a risk>",
      "remediation": "<specific fix>"
    }}
  ]
}}

If no issues found, use severity "clean", empty findings array, and summary "No security issues detected."
Limit to the top 3 most critical findings."""


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("diff", help="Staged diff text to analyse")
    p.add_argument("--log-dir", default=DEFAULT_LOG, help="Directory to write advisory reports")
    return p.parse_args()


def load_model(model_dir):
    from mlx_lm import load
    return load(model_dir)


def run_inference(model, tokenizer, diff_text):
    from mlx_lm import generate

    prompt_text = REVIEW_PROMPT.format(diff=diff_text[:3000])  # cap at 3000 chars
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt_text},
    ]
    formatted = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    raw = generate(model, tokenizer, prompt=formatted, max_tokens=512, verbose=False)

    # Strip chat end token if present
    raw = raw.replace("<|im_end|>", "").strip()

    # Extract JSON — find first { to last }
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None, raw

    try:
        return json.loads(raw[start:end]), None
    except json.JSONDecodeError:
        return None, raw


def write_report(result, diff_text, log_dir):
    os.makedirs(log_dir, exist_ok=True)
    diff_hash  = hashlib.sha1(diff_text.encode()).hexdigest()[:10]
    timestamp  = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename   = f"advisory_{timestamp}_{diff_hash}.json"
    report_path = os.path.join(log_dir, filename)

    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model":        "Qwen2.5-Coder-1.5B-Instruct-4bit",
        "layer":        3,
        "diff_hash":    diff_hash,
        "diff_preview": diff_text[:200] + ("..." if len(diff_text) > 200 else ""),
        "analysis":     result,
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return report_path


def main():
    args = parse_args()
    diff_text = args.diff

    if not os.path.isdir(MODEL_DIR):
        error = {"error": f"Qwen model not found at {MODEL_DIR}. Run: python3 coreml/advisory.py to download."}
        print(json.dumps(error))
        sys.exit(1)

    try:
        model, tokenizer = load_model(MODEL_DIR)
    except Exception as e:
        print(json.dumps({"error": f"Model load failed: {e}"}))
        sys.exit(1)

    result, raw = run_inference(model, tokenizer, diff_text)

    if result is None:
        # Model returned non-JSON — wrap it as a low-severity finding
        result = {
            "severity": "low",
            "summary":  "Advisory engine returned unstructured output.",
            "findings": [{"type": "parse_error", "line_hint": "", "explanation": raw or "empty", "remediation": "Review diff manually."}],
        }

    report_path = write_report(result, diff_text, args.log_dir)

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
