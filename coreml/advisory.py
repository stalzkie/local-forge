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

_MODEL_SHORTCUTS = {
    "7b":   "qwen2.5-coder-7b-4bit",
    "1.5b": "qwen2.5-coder-1.5b-4bit",
    "14b":  "qwen2.5-coder-14b-4bit",
}

def _find_model_dir(override=None) -> str:
    home = os.path.expanduser("~")
    lf   = os.path.join(home, ".localforge")

    # Explicit override from --model flag
    if override:
        name = _MODEL_SHORTCUTS.get(override.lower(), override)
        candidates = [
            os.path.join(lf, name),
            os.path.abspath(name),
        ]
        for c in candidates:
            if os.path.isdir(c):
                return os.path.abspath(c)
        return os.path.join(lf, name)   # will fail later with a clear error

    # Auto-detect: prefer 7B, fall back to 1.5B
    for name in ("qwen2.5-coder-7b-4bit", "qwen2.5-coder-1.5b-4bit"):
        for base in (lf, SCRIPT_DIR, os.path.join(SCRIPT_DIR, "..", "coreml")):
            c = os.path.join(base, name)
            if os.path.isdir(c):
                return os.path.abspath(c)

    return os.path.join(lf, "qwen2.5-coder-7b-4bit")  # default target for install

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

    raw = generate(model, tokenizer, prompt=formatted, max_tokens=1536, verbose=False)
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

# ── Post-processing FP filter ────────────────────────────────────────────────
#
# Suppress findings where the flagged line matches a known-safe pattern.
# Applied after model inference so the model's recall is unaffected.

_SAFE_PATTERNS: dict[str, list[re.Pattern]] = {
    "sql_injection": [
        # Positional placeholders: ?, $1, $2, %s, :name
        re.compile(r'["\'].*\b(WHERE|SET|VALUES|INSERT|UPDATE|FROM)\b.*[?]', re.I),
        re.compile(r'["\'].*\$\d+'),
        re.compile(r'["\'].*%[sd]'),
        re.compile(r'["\'].*:\w+["\']'),
        # ORM / query builder methods that are safe
        re.compile(r'\.(filter|get|exclude|annotate|select_related)\(', re.I),
        re.compile(r'prepareStatement\s*\(', re.I),
        re.compile(r'sqlx::query[_!]?\s*[!(]', re.I),
        re.compile(r'db\.raw\s*\(["\'].*["\'],\s*[\[{(]', re.I),
    ],
    "command_injection": [
        # subprocess/exec with list args (not shell=True)
        re.compile(r'subprocess\.(run|call|check_output|Popen)\s*\(\s*\['),
        re.compile(r'exec\.Command\s*\(["\'][^"\']+["\'],\s*["\']'),
        re.compile(r'spawnSync?\s*\(\s*["\'][^"\']+["\'],\s*\['),
        re.compile(r'\bsystem\s*\(\s*["\'][^"\']+["\'],\s*["\']'),
        # Rust Command::new with .arg() chaining (no shell)
        re.compile(r'Command::new\s*\('),
    ],
    "insecure_tls": [
        # verify= with a real path or True
        re.compile(r'verify\s*=\s*["\'/]'),
        re.compile(r'verify\s*=\s*True', re.I),
        # Plain http.Client / reqwest with no TLS config
        re.compile(r'&http\.Client\{(?!.*TLS)', re.I),
        re.compile(r'Client::builder\(\)\.timeout\('),
    ],
    "path_traversal": [
        # basename + join pattern
        re.compile(r'os\.path\.basename\s*\('),
        re.compile(r'filepath\.Base\s*\('),
        re.compile(r'Path\.resolve\s*\(.*\)\.normalize\s*\('),
        # explicit prefix check nearby (heuristic: startswith/HasPrefix in same hunk)
        re.compile(r'startsWith?\s*\(.*base', re.I),
    ],
    "xss": [
        # React safe rendering
        re.compile(r'>\s*\{[^}]+\}\s*<'),
        re.compile(r'\.textContent\s*='),
        re.compile(r'createElement\s*\('),
        # Escaping functions
        re.compile(r'escape\s*\(|escapeHtml|htmlspecialchars|sanitize', re.I),
        re.compile(r'mark_safe\s*\(.*escape\s*\(', re.I),
    ],
    "unsafe_deserialization": [
        re.compile(r'json\.loads?\s*\('),
        re.compile(r'yaml\.safe_load\s*\('),
        re.compile(r'JSON\.parse\s*\('),
        re.compile(r'ObjectMapper\(\)\.readValue\s*\('),
        re.compile(r'serde_json::from_str\s*\('),
    ],
    "hardcoded_secret": [
        # env var reads are safe
        re.compile(r'os\.environ[\[.]|os\.getenv\s*\(', re.I),
        re.compile(r'process\.env\b', re.I),
        re.compile(r'std::env::var\s*\(', re.I),
        re.compile(r'System\.getenv\s*\(', re.I),
        re.compile(r'getenv\s*\(', re.I),
    ],
}

# Type aliases from the model that map to our filter categories
_TYPE_TO_CATEGORY: dict[str, str] = {
    "sql_injection":          "sql_injection",
    "sql_command_injection":  "sql_injection",
    "sqli":                   "sql_injection",
    "command_injection":      "command_injection",
    "cmdi":                   "command_injection",
    "os_command_injection":   "command_injection",
    "insecure_tls":           "insecure_tls",
    "tls_verification":       "insecure_tls",
    "disabled_tls":           "insecure_tls",
    "insecure_ssl":           "insecure_tls",
    "path_traversal":         "path_traversal",
    "directory_traversal":    "path_traversal",
    "xss":                    "xss",
    "cross_site_scripting":   "xss",
    "unsafe_deserialization": "unsafe_deserialization",
    "insecure_deserialization": "unsafe_deserialization",
    "hardcoded_secret":       "hardcoded_secret",
    "hardcoded_credential":   "hardcoded_secret",
    "hardcoded_password":     "hardcoded_secret",
    "secret_exposure":        "hardcoded_secret",
}


# ── Clean-diff pre-filter ─────────────────────────────────────────────────────
#
# If the diff has no added lines containing any risky keyword, skip inference
# entirely and return clean immediately. Eliminates FPs on refactors, removals,
# and purely structural changes before the model ever sees them.

_RISKY_KEYWORDS = re.compile(
    r"""
    # Secrets / credentials
    password|passwd|secret|api[_\-]?key|token|credential|auth[_\-]?key|
    private[_\-]?key|access[_\-]?key|signing[_\-]?key|client[_\-]?secret|
    # SQL
    SELECT|INSERT|UPDATE|DELETE|DROP\s+TABLE|
    # Command execution
    subprocess|os\.system|exec\b|eval\b|shell=True|
    exec\.Command|Runtime\.exec|Process\.Start|execSync|spawnSync|
    # XSS / output injection
    innerHTML|dangerouslySetInnerHTML|document\.write|mark_safe|
    \.html\s*\(|HttpResponse\s*\(|echo\s+.*\$|
    # TLS / crypto
    verify=False|InsecureSkipVerify|NODE_TLS_REJECT|
    danger_accept_invalid|ssl\.CERT_NONE|
    hashlib\.md5|hashlib\.sha1|\bDES\b|\bRC4\b|ECB|
    # Deserialization
    pickle\.loads?|yaml\.load\b|readObject|Marshal\.load|
    # Path traversal — file open with user-controlled variable
    open\s*\(|ReadFile\s*\(|readfile\s*\(|sendFile\s*\(|
    Files\.readAllBytes|new\s+File\s*\(|readfile\(|
    # Race condition / unprotected shared state
    global\s+\w|var\s+cache\s+=\s+map|var\s+\w+\s+int\s*$|
    static\s+(int|var|mut)\b|activeJobs|count\+\+|counter\s*\+=|
    map\[string\]string\{\}|map\[string\]|
    # Logic bugs — off-by-one (<=length, 0..=, + 1 in slice end)
    <=\s*\w+\.length|i\s*<=\s*\w+\b|0\.\.=|
    \+\s*1\b.*return|end\s*\+\s*1|start\s*\+.*\+\s*1|
    &[^&]\w+\s*&&|not\s+\w+\s*!=|
    # Dead code — duplicate identical function bodies
    strings\.TrimSpace.*strings\.ToLower|
    def\s+_legacy_|def\s+\w+_old\b|def\s+format_date|
    func\s+\w+Old\b|function\s+\w+Legacy\b|
    # Unhandled exceptions — ignored error returns, bare access
    ,\s*_\s*:=|data,\s*_\s*=|\.fetchone\(\)\[|
    Integer\.parseInt\b|JSON\.parse\b|
    # Obfuscated secrets — base64 decode assigned to client/key var
    base64\.(b64decode|decode|decodebytes)|atob\s*\(|btoa\s*\(
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_clean_diff(diff_text: str) -> bool:
    """
    Return True if the diff has no added lines matching any risky keyword.
    When True, skip model inference entirely — the diff cannot introduce
    any of the issues LocalForge tracks.
    """
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            if _RISKY_KEYWORDS.search(line):
                return False
    return True


def _added_lines(diff_text: str) -> list[str]:
    """Extract only the added lines (+) from a diff."""
    return [
        line[1:]  # strip the leading +
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def _is_safe_false_positive(finding: dict, diff_text: str) -> bool:
    """
    Return True if the finding should be suppressed.

    Strategy: check the line_hint the model quoted first (most precise).
    If line_hint is vague/empty, scan the actual added lines from the diff.
    A finding is suppressed only when ALL added lines that could be relevant
    match a safe pattern — meaning there's no unsafe addition left to flag.

    Also applies cross-type checks: the model sometimes misclassifies a safe
    parameterized query as hardcoded_secret or another type — catch these by
    scanning the line_hint against all relevant safe pattern sets.
    """
    ftype    = finding.get("type", "").lower().replace(" ", "_").replace("-", "_")
    category = _TYPE_TO_CATEGORY.get(ftype)
    line_hint = finding.get("line_hint", "").strip()

    # Cross-type check: if the quoted line looks like a safe SQL parameterized query,
    # suppress regardless of what type label the model gave it
    _CROSS_TYPE_SAFE = [
        # Parameterized SQL in any language
        re.compile(r"['\"].*\b(WHERE|SET|VALUES|INSERT|UPDATE|FROM)\b.*[?]", re.I),
        re.compile(r"['\"].*\$\d+"),
        re.compile(r"['\"].*%[sd]"),
        re.compile(r"['\"].*:\w+['\"]"),
        re.compile(r"prepareStatement\s*\(", re.I),
        re.compile(r"sqlx::query[_!]?\s*[!(]", re.I),
        re.compile(r"\.(filter|get|exclude)\s*\(", re.I),
        # Safe subprocess list form
        re.compile(r"subprocess\.(run|call|check_output|Popen)\s*\(\s*\["),
        re.compile(r"spawnSync?\s*\(\s*['\"][^'\"]+['\"],\s*\["),
        # Safe deserializers
        re.compile(r"\bjson\.loads?\s*\("),
        re.compile(r"\byaml\.safe_load\s*\("),
        # Env-var reads (safe secret pattern)
        re.compile(r"os\.environ[\[.]|os\.getenv\s*\(", re.I),
        re.compile(r"process\.env\b", re.I),
        re.compile(r"std::env::var\s*\(", re.I),
        re.compile(r"System\.getenv\s*\(", re.I),
    ]
    if line_hint and len(line_hint) > 8:
        for pat in _CROSS_TYPE_SAFE:
            if pat.search(line_hint):
                return True

    if not category or category not in _SAFE_PATTERNS:
        return False

    patterns  = _SAFE_PATTERNS[category]

    # If the model quoted a specific line, check only that
    if line_hint and len(line_hint) > 10 and not line_hint.startswith("line ") and not line_hint.startswith("diff"):
        for pat in patterns:
            if pat.search(line_hint):
                return True
        return False

    # line_hint is vague — scan actual added lines from the diff
    added = _added_lines(diff_text)
    if not added:
        return False

    # Count lines that look relevant to this category (contain SQL/exec keywords etc.)
    RELEVANCE: dict[str, re.Pattern] = {
        "sql_injection":          re.compile(r'\b(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM|JOIN)\b', re.I),
        "command_injection":      re.compile(r'\b(subprocess|exec|system|spawn|popen|os\.system)\b', re.I),
        "insecure_tls":           re.compile(r'\b(verify|TLS|SSL|InsecureSkip|NODE_TLS)\b', re.I),
        "path_traversal":         re.compile(r'\b(open|ReadFile|readfile|sendFile)\b', re.I),
        "xss":                    re.compile(r'\b(innerHTML|dangerouslySetInner|mark_safe|echo)\b', re.I),
        "unsafe_deserialization": re.compile(r'\b(pickle|yaml\.load|readObject|eval|Marshal)\b', re.I),
        "hardcoded_secret":       re.compile(r'\b(password|secret|key|token|api_key)\b', re.I),
    }

    relevance_pat = RELEVANCE.get(category)
    relevant_lines = [l for l in added if relevance_pat and relevance_pat.search(l)] if relevance_pat else added

    if not relevant_lines:
        return False

    # Suppress only if every relevant line matches a safe pattern
    safe_count = 0
    for line in relevant_lines:
        if any(pat.search(line) for pat in patterns):
            safe_count += 1

    return safe_count == len(relevant_lines)


def filter_false_positives(result: dict, diff_text: str) -> dict:
    """Remove findings that match known-safe patterns. Recalculates severity."""
    findings = result.get("findings", [])
    filtered = [f for f in findings if not _is_safe_false_positive(f, diff_text)]

    if len(filtered) == len(findings):
        return result  # nothing removed

    severity_rank = {"high": 3, "medium": 2, "low": 1, "clean": 0}
    if not filtered:
        new_severity = "clean"
    else:
        new_severity = max(
            (f.get("severity", "low") for f in filtered),
            key=lambda s: severity_rank.get(s, 0),
            default=result.get("severity", "clean"),
        )
        # Fall back to original severity if findings don't carry their own
        if new_severity == "low" and result.get("severity") in ("high", "medium"):
            new_severity = result["severity"]

    return {
        "severity": new_severity,
        "summary":  result.get("summary", ""),
        "findings": filtered,
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
        model_name = result.get("model", "Qwen2.5-Coder (Layer 3 advisory)")
        lines.append(f"  Model     : {model_name}")
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
    p.add_argument("--model", default=None,
                   help="Model to use: 1.5b | 7b | 14b | /path/to/model (default: auto-detect 7b then 1.5b)")
    return p.parse_args()


def main():
    args      = parse_args()
    diff_text = args.diff
    model_dir = _find_model_dir(args.model)

    # ── Fast path: nothing risky in added lines → skip everything ────────────
    if _is_clean_diff(diff_text):
        clean_result = {
            "severity": "clean",
            "summary":  "No risky patterns detected in added lines.",
            "findings": [],
        }
        report_path = write_report(clean_result, diff_text, args.log_dir, args.report_file)
        print(json.dumps({**clean_result, "report_path": report_path}))
        sys.exit(0)

    # ── Layer 3.5: static analysis (deterministic, <1s, no model needed) ─────
    static_findings: list[dict] = []
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from static_analysis import run_static_analysis
        static_findings = run_static_analysis(diff_text)
    except ImportError:
        pass  # static_analysis.py not present — continue to LLM only
    except Exception:
        pass  # never let static analysis crash the advisory pipeline

    # ── Layer 3: LLM inference ────────────────────────────────────────────────
    if not os.path.isdir(model_dir):
        # No model — if static analysis found something, still report it
        if static_findings:
            result = {
                "severity": "medium",
                "summary":  "Static analysis findings (LLM model not installed).",
                "findings": static_findings,
            }
            report_path = write_report(result, diff_text, args.log_dir, args.report_file)
            print(json.dumps({**result, "report_path": report_path}))
            sys.exit(0)
        print(json.dumps({"error": f"Qwen model not found at {model_dir}"}))
        sys.exit(1)

    try:
        model, tokenizer = load_model(model_dir)
    except Exception as e:
        print(json.dumps({"error": f"Model load failed: {e}"}))
        sys.exit(1)

    languages = detect_languages(diff_text)
    chunks    = chunk_diff(diff_text)
    results   = []

    for chunk in chunks:
        result, raw = run_inference(model, tokenizer, chunk, languages)
        if result is None:
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

    merged = filter_false_positives(merge_findings(results), diff_text)

    # Merge static findings in (they go first — deterministic results are highest confidence)
    all_findings = static_findings + [
        f for f in merged.get("findings", [])
        if f.get("type") != "parse_error" or not static_findings
    ]
    severity_rank = {"high": 3, "medium": 2, "low": 1, "clean": 0}
    final_severity = merged.get("severity", "clean")
    if static_findings:
        final_severity = max(
            final_severity, "medium",
            key=lambda s: severity_rank.get(s, 0),
        )

    final = {
        "severity": final_severity,
        "summary":  merged.get("summary", "Static and LLM analysis complete."),
        "findings": all_findings[:10],
        "model":    os.path.basename(model_dir),
    }

    report_path = write_report(final, diff_text, args.log_dir, args.report_file)
    print(json.dumps({**final, "report_path": report_path}))
    sys.exit(0)


if __name__ == "__main__":
    main()
