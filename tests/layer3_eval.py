#!/usr/bin/env python3
"""
LocalForge Layer 3 Evaluation Runner
Runs each labeled diff through the advisory engine and computes
Precision, Recall, F1, and False Positive Rate — overall and by category/language.
Writes a timestamped JSON artifact and a text draft report.

Usage:
    python3 tests/layer3_eval.py [--model-dir DIR] [--out DIR] [--quick]

    --model-dir  Path to the Qwen model (default: ~/.localforge/qwen2.5-coder-1.5b-4bit)
    --out        Output directory (default: tests/benchmark_results/)
    --quick      Run only the first 20 entries (smoke-test mode)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

# ---------------------------------------------------------------------------
# Corpus import
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from layer3_eval_corpus import CORPUS

ADVISORY_SCRIPT = Path(__file__).parent.parent / "coreml" / "advisory.py"
DEFAULT_MODEL   = Path.home() / ".localforge" / "qwen2.5-coder-7b-4bit"
DEFAULT_OUT     = Path(__file__).parent / "benchmark_results"

# ---------------------------------------------------------------------------
# Advisory call
# ---------------------------------------------------------------------------

def call_advisory(diff: str, model_dir: str, commit_hash: str = "eval") -> dict:
    """
    Call coreml/advisory.py for a single diff.
    advisory.py takes the diff as a positional string arg and writes JSON to stdout.
    """
    env = os.environ.copy()

    try:
        result = subprocess.run(
            [sys.executable, str(ADVISORY_SCRIPT), diff, "--model", model_dir],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        stdout = result.stdout.strip()
        if not stdout:
            return {"error": "empty output", "stderr": result.stderr[:500]}
        # advisory.py emits one JSON line (possibly after urllib3 warnings on stderr)
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        return {"error": "no JSON in output", "raw": stdout[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except json.JSONDecodeError as e:
        return {"error": f"json parse: {e}"}


def advisory_flagged(response: dict) -> bool:
    """True if the advisory engine found at least one real finding."""
    if "error" in response:
        return False
    findings = response.get("findings", [])
    if not isinstance(findings, list) or len(findings) == 0:
        return False
    # A single parse_error finding from a chunk error doesn't count as a real flag
    if len(findings) == 1 and findings[0].get("type") == "parse_error":
        return False
    severity = response.get("severity", "clean")
    return severity != "clean"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(results: list[dict]) -> dict:
    tp = sum(1 for r in results if r["should_flag"] and r["flagged"])
    fp = sum(1 for r in results if not r["should_flag"] and r["flagged"])
    fn = sum(1 for r in results if r["should_flag"] and not r["flagged"])
    tn = sum(1 for r in results if not r["should_flag"] and not r["flagged"])

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr       = fp / (fp + tn) if (fp + tn) else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall":    round(recall,    4),
        "f1":        round(f1,        4),
        "fpr":       round(fpr,       4),
    }


def group_metrics(results: list[dict], key: str) -> dict:
    groups: dict[str, list] = defaultdict(list)
    for r in results:
        groups[r[key]].append(r)
    return {g: compute_metrics(items) for g, items in sorted(groups.items())}


# ---------------------------------------------------------------------------
# Terminal table
# ---------------------------------------------------------------------------

def print_table(title: str, breakdown: dict) -> None:
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")
    header = f"{'Group':<26} {'P':>6} {'R':>6} {'F1':>6} {'FPR':>6}  {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3}"
    print(header)
    print("─" * 70)
    for group, m in breakdown.items():
        print(
            f"{group:<26} {m['precision']:>6.3f} {m['recall']:>6.3f} "
            f"{m['f1']:>6.3f} {m['fpr']:>6.3f}  "
            f"{m['tp']:>3} {m['fp']:>3} {m['fn']:>3} {m['tn']:>3}"
        )


# ---------------------------------------------------------------------------
# Draft report
# ---------------------------------------------------------------------------

def write_draft_report(
    overall: dict,
    by_category: dict,
    by_language: dict,
    results: list[dict],
    elapsed: float,
    out_path: Path,
) -> None:
    lines = [
        "# LocalForge Layer 3 Evaluation Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Corpus size: {len(results)} diffs  |  Runtime: {elapsed:.1f}s",
        "",
        "## Overall",
        f"- Precision : {overall['precision']:.3f}",
        f"- Recall    : {overall['recall']:.3f}",
        f"- F1        : {overall['f1']:.3f}",
        f"- FPR       : {overall['fpr']:.3f}",
        f"- TP/FP/FN/TN: {overall['tp']} / {overall['fp']} / {overall['fn']} / {overall['tn']}",
        "",
        "## By Category",
    ]
    for cat, m in by_category.items():
        lines.append(
            f"- **{cat}**: P={m['precision']:.3f}  R={m['recall']:.3f}  "
            f"F1={m['f1']:.3f}  FPR={m['fpr']:.3f}  "
            f"(TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']})"
        )
    lines += ["", "## By Language"]
    for lang, m in by_language.items():
        lines.append(
            f"- **{lang}**: P={m['precision']:.3f}  R={m['recall']:.3f}  "
            f"F1={m['f1']:.3f}  FPR={m['fpr']:.3f}  "
            f"(TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']})"
        )
    lines += ["", "## False Positives"]
    fps = [r for r in results if not r["should_flag"] and r["flagged"]]
    if fps:
        for r in fps:
            lines.append(f"- `{r['id']}` [{r['language']}] {r['category']}")
    else:
        lines.append("- None")
    lines += ["", "## False Negatives"]
    fns = [r for r in results if r["should_flag"] and not r["flagged"]]
    if fns:
        for r in fns:
            lines.append(f"- `{r['id']}` [{r['language']}] {r['category']}")
    else:
        lines.append("- None")
    lines += ["", "## Errors"]
    errs = [r for r in results if r.get("advisory_error")]
    if errs:
        for r in errs:
            lines.append(f"- `{r['id']}`: {r['advisory_error']}")
    else:
        lines.append("- None")

    out_path.write_text("\n".join(lines) + "\n")
    print(f"\n  Draft report: {out_path}")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def generate_charts(
    overall: dict,
    by_category: dict,
    by_language: dict,
    results: list[dict],
    out_dir: Path,
    ts: str,
) -> list[Path]:
    if not _HAS_MPL:
        print("\n  [charts skipped — pip install matplotlib numpy]")
        return []

    saved: list[Path] = []

    # ── 1. Precision / Recall / F1 bar chart by category ─────────────────────
    cats   = list(by_category.keys())
    p_vals = [by_category[c]["precision"] for c in cats]
    r_vals = [by_category[c]["recall"]    for c in cats]
    f_vals = [by_category[c]["f1"]        for c in cats]

    x   = np.arange(len(cats))
    w   = 0.26
    fig, ax = plt.subplots(figsize=(max(12, len(cats) * 0.9), 5))
    ax.bar(x - w, p_vals, w, label="Precision", color="#4C9BE8")
    ax.bar(x,     r_vals, w, label="Recall",    color="#F5A623")
    ax.bar(x + w, f_vals, w, label="F1",        color="#7ED321")
    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=35, ha="right", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title("Layer 3  —  Precision / Recall / F1 by Category")
    ax.legend(loc="lower right")
    ax.axhline(overall["f1"], color="gray", linestyle="--", linewidth=0.8, label=f"Overall F1 {overall['f1']:.3f}")
    ax.legend(loc="lower right")
    fig.tight_layout()
    p1 = out_dir / f"layer3_eval_{ts}_cat_prf.png"
    fig.savefig(p1, dpi=150)
    plt.close(fig)
    saved.append(p1)

    # ── 2. TP / FP / FN stacked bar by category ───────────────────────────────
    tp_vals = [by_category[c]["tp"] for c in cats]
    fp_vals = [by_category[c]["fp"] for c in cats]
    fn_vals = [by_category[c]["fn"] for c in cats]

    fig, ax = plt.subplots(figsize=(max(12, len(cats) * 0.9), 5))
    ax.bar(cats, tp_vals, label="TP", color="#7ED321")
    ax.bar(cats, fp_vals, bottom=tp_vals, label="FP", color="#D0021B")
    bottoms = [a + b for a, b in zip(tp_vals, fp_vals)]
    ax.bar(cats, fn_vals, bottom=bottoms, label="FN", color="#F5A623")
    ax.set_xticklabels(cats, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Count")
    ax.set_title("Layer 3  —  TP / FP / FN by Category")
    ax.legend(loc="upper right")
    fig.tight_layout()
    p2 = out_dir / f"layer3_eval_{ts}_cat_counts.png"
    fig.savefig(p2, dpi=150)
    plt.close(fig)
    saved.append(p2)

    # ── 3. F1 heatmap: category × language ───────────────────────────────────
    # Build a per-(category, language) sub-corpus and compute F1
    lang_cat: dict[tuple, list] = defaultdict(list)
    for r in results:
        lang_cat[(r["language"], r["category"])].append(r)

    all_langs = sorted({r["language"] for r in results})
    all_cats  = sorted({r["category"] for r in results})

    matrix = np.full((len(all_langs), len(all_cats)), np.nan)
    for li, lang in enumerate(all_langs):
        for ci, cat in enumerate(all_cats):
            cell = lang_cat.get((lang, cat), [])
            if cell:
                m = compute_metrics(cell)
                matrix[li, ci] = m["f1"]

    fig, ax = plt.subplots(figsize=(max(10, len(all_cats) * 0.8), max(4, len(all_langs) * 0.6)))
    cmap = plt.cm.RdYlGn.copy()
    cmap.set_bad(color="#e0e0e0")
    im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(all_cats)))
    ax.set_yticks(range(len(all_langs)))
    ax.set_xticklabels(all_cats, rotation=40, ha="right", fontsize=7)
    ax.set_yticklabels(all_langs, fontsize=8)
    for li in range(len(all_langs)):
        for ci in range(len(all_cats)):
            v = matrix[li, ci]
            if not np.isnan(v):
                ax.text(ci, li, f"{v:.2f}", ha="center", va="center", fontsize=6,
                        color="black" if 0.25 < v < 0.85 else "white")
    fig.colorbar(im, ax=ax, label="F1")
    ax.set_title("Layer 3  —  F1 Heatmap (category × language)  — grey = no data")
    fig.tight_layout()
    p3 = out_dir / f"layer3_eval_{ts}_heatmap.png"
    fig.savefig(p3, dpi=150)
    plt.close(fig)
    saved.append(p3)

    # ── 4. FPR bar chart by language ──────────────────────────────────────────
    langs   = list(by_language.keys())
    fpr_vals = [by_language[l]["fpr"] for l in langs]
    colors   = ["#D0021B" if v > 0.2 else "#F5A623" if v > 0.05 else "#7ED321" for v in fpr_vals]

    fig, ax = plt.subplots(figsize=(max(7, len(langs) * 0.9), 4))
    ax.bar(langs, fpr_vals, color=colors)
    ax.axhline(0.1, color="gray", linestyle="--", linewidth=0.8)
    ax.set_ylabel("False Positive Rate")
    ax.set_title("Layer 3  —  False Positive Rate by Language")
    ax.set_ylim(0, max(fpr_vals + [0.25]) * 1.2)
    ax.set_xticklabels(langs, rotation=20, ha="right")
    fig.tight_layout()
    p4 = out_dir / f"layer3_eval_{ts}_fpr_lang.png"
    fig.savefig(p4, dpi=150)
    plt.close(fig)
    saved.append(p4)

    return saved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="LocalForge Layer 3 Eval")
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL))
    parser.add_argument("--out",       default=str(DEFAULT_OUT))
    parser.add_argument("--quick",     action="store_true")
    args = parser.parse_args()

    model_dir = args.model_dir
    out_dir   = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus = CORPUS[:20] if args.quick else CORPUS
    total  = len(corpus)

    if not Path(model_dir).exists():
        print(f"ERROR: model not found at {model_dir}")
        print("Install it with: mv ~/Desktop/qwen2.5-coder-1.5b-4bit ~/.localforge/")
        sys.exit(1)

    if not ADVISORY_SCRIPT.exists():
        print(f"ERROR: advisory script not found at {ADVISORY_SCRIPT}")
        sys.exit(1)

    print(f"LocalForge Layer 3 Eval  —  {total} diffs  —  model: {model_dir}")
    print(f"{'─' * 70}")

    results  : list[dict] = []
    start    = time.time()
    interval = max(1, total // 20)

    for i, entry in enumerate(corpus, 1):
        t0       = time.time()
        response = call_advisory(entry["diff"], model_dir, commit_hash=entry["id"])
        elapsed  = time.time() - t0
        flagged  = advisory_flagged(response)

        result = {
            "id":             entry["id"],
            "language":       entry["language"],
            "category":       entry["category"],
            "should_flag":    entry["should_flag"],
            "flagged":        flagged,
            "elapsed_s":      round(elapsed, 2),
            "advisory_error": response.get("error"),
            "response":       response,
        }
        results.append(result)

        label = "✓" if flagged == entry["should_flag"] else "✗"
        if i % interval == 0 or i == total:
            pct = i / total * 100
            print(f"  [{i:>3}/{total}] {pct:>5.1f}%  last={entry['id']} {label} ({elapsed:.1f}s)")

    total_elapsed = time.time() - start

    # ── Metrics ───────────────────────────────────────────────────────────────
    overall      = compute_metrics(results)
    by_category  = group_metrics(results, "category")
    by_language  = group_metrics(results, "language")

    print(f"\n{'═' * 70}")
    print("  OVERALL RESULTS")
    print(f"{'═' * 70}")
    print(f"  Precision : {overall['precision']:.3f}")
    print(f"  Recall    : {overall['recall']:.3f}")
    print(f"  F1        : {overall['f1']:.3f}")
    print(f"  FPR       : {overall['fpr']:.3f}")
    print(f"  TP={overall['tp']}  FP={overall['fp']}  FN={overall['fn']}  TN={overall['tn']}")
    print(f"  Runtime   : {total_elapsed:.1f}s  ({total_elapsed/total:.1f}s/diff avg)")

    print_table("BY CATEGORY", by_category)
    print_table("BY LANGUAGE", by_language)

    # ── FP / FN callout ───────────────────────────────────────────────────────
    fps = [r for r in results if not r["should_flag"] and r["flagged"]]
    fns = [r for r in results if r["should_flag"] and not r["flagged"]]
    errs = [r for r in results if r.get("advisory_error")]

    if fps:
        print(f"\n  False Positives ({len(fps)}):")
        for r in fps:
            print(f"    - {r['id']} [{r['language']}] {r['category']}")
    if fns:
        print(f"\n  False Negatives ({len(fns)}):")
        for r in fns:
            print(f"    - {r['id']} [{r['language']}] {r['category']}")
    if errs:
        print(f"\n  Advisory Errors ({len(errs)}):")
        for r in errs:
            print(f"    - {r['id']}: {r['advisory_error']}")

    # ── Save JSON artifact ────────────────────────────────────────────────────
    ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_out = out_dir / f"layer3_eval_{ts}.json"
    artifact = {
        "meta": {
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "corpus_size":  total,
            "model_dir":    model_dir,
            "runtime_s":    round(total_elapsed, 2),
            "quick_mode":   args.quick,
        },
        "overall":      overall,
        "by_category":  by_category,
        "by_language":  by_language,
        "results":      results,
    }
    json_out.write_text(json.dumps(artifact, indent=2))
    print(f"\n  JSON artifact: {json_out}")

    # ── Save draft report ─────────────────────────────────────────────────────
    report_out = out_dir / f"layer3_eval_{ts}_report.md"
    write_draft_report(overall, by_category, by_language, results, total_elapsed, report_out)

    # ── Generate charts ───────────────────────────────────────────────────────
    charts = generate_charts(overall, by_category, by_language, results, out_dir, ts)
    for c in charts:
        print(f"  Chart: {c}")

    print(f"\n{'═' * 70}\n")


if __name__ == "__main__":
    main()
