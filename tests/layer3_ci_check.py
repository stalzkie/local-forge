#!/usr/bin/env python3
"""
Layer 3 CI regression check.

Runs a small, fixed subset of the Layer 3 eval corpus (tests/layer3_eval.py's
full corpus is too slow/expensive to run on every push — see IMPROVEMENTS.md)
and compares aggregate precision/recall/F1 against a checked-in baseline
(tests/layer3_baseline.json), failing if any metric regresses beyond
TOLERANCE. Catches prompt/model regressions the way the Layer 1 golden set
catches regex regressions.

Why aggregate metrics with tolerance, not exact per-item matches:
Qwen/MLX is deterministic here (mlx_lm's default sampler is argmax/greedy —
verified empirically: identical output across repeated runs on identical
weights/hardware), but CI runners can differ in Apple Silicon generation and
mlx/mlx_lm version from the machine that captured the baseline, both of
which can shift floating-point results at the margins. A tolerance band on
the aggregate score absorbs that residual drift without masking a real
regression (a broken prompt collapses precision/recall well past the band).

Why a fixed 20-entry subset, not the full corpus: the full corpus (145
entries) would take too long against a live model on every push. This
subset is hand-picked to cover every category in layer3_eval_corpus.py at
least once across 5 languages, with a mix of true- and true-negatives.

Usage:
    python3 tests/layer3_ci_check.py [--model-dir DIR]
    python3 tests/layer3_ci_check.py --update-baseline   # after an
        intentional prompt/model change, regenerate the checked-in baseline

Exit codes:
  0 — within tolerance of baseline (or baseline just written)
  1 — regressed beyond tolerance, or the model/advisory script isn't available
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from layer3_eval import ADVISORY_SCRIPT, call_advisory, advisory_flagged, compute_metrics
from layer3_eval_corpus import CORPUS

BASELINE_PATH = Path(__file__).parent / "layer3_baseline.json"
DEFAULT_MODEL = Path.home() / ".localforge" / "qwen2.5-coder-1.5b-4bit"

# Absolute-point tolerance: a metric may drop by at most this much from the
# baseline before the check fails. Loose enough to absorb minor cross-runner
# floating-point drift, tight enough to catch a genuinely broken prompt.
TOLERANCE = 0.15

# Hand-picked subset covering every category in layer3_eval_corpus.py at
# least once, across 5 languages, mixing true- and true-negatives. Fixed and
# explicit (not "first N of CORPUS") so growing the corpus never silently
# changes what this check runs.
SUBSET_IDS = [
    "edge_clean_py", "edge_clean_ts",
    "cmd_01", "cmd_03",
    "dead_02",
    "edge_removal_02",
    "secret_02",
    "tls_03",
    "edge_large_01",
    "logic_03",
    "edge_mixed_02",
    "edge_multifile_03",
    "edge_obfuscated_02",
    "path_03",
    "race_02",
    "edge_refactor_02",
    "sql_03",
    "exc_03",
    "deser_03",
    "xss_01",
]


def _subset() -> list[dict]:
    by_id = {e["id"]: e for e in CORPUS}
    missing = [i for i in SUBSET_IDS if i not in by_id]
    if missing:
        print(f"ERROR: SUBSET_IDS references entries no longer in the corpus: {missing}")
        sys.exit(1)
    return [by_id[i] for i in SUBSET_IDS]


def run_subset(model_dir: str) -> dict:
    entries = _subset()
    results = []
    start = time.time()
    for entry in entries:
        response = call_advisory(entry["diff"], model_dir, commit_hash=entry["id"])
        flagged = advisory_flagged(response)
        results.append({
            "id": entry["id"],
            "category": entry["category"],
            "language": entry["language"],
            "should_flag": entry["should_flag"],
            "flagged": flagged,
            "advisory_error": response.get("error"),
        })
    elapsed = time.time() - start
    metrics = compute_metrics(results)
    return {"metrics": metrics, "results": results, "elapsed_s": round(elapsed, 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description="LocalForge Layer 3 CI regression check")
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL))
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write tests/layer3_baseline.json from this run instead of comparing to it",
    )
    args = parser.parse_args()

    if not Path(args.model_dir).exists():
        print(f"ERROR: model not found at {args.model_dir}")
        print("Install it with: localforge --install  (or point --model-dir at one)")
        sys.exit(1)
    if not ADVISORY_SCRIPT.exists():
        print(f"ERROR: advisory script not found at {ADVISORY_SCRIPT}")
        sys.exit(1)

    print(f"Layer 3 CI check — {len(SUBSET_IDS)} diffs — model: {args.model_dir}")
    run = run_subset(args.model_dir)
    metrics = run["metrics"]

    print(f"  Precision : {metrics['precision']:.3f}")
    print(f"  Recall    : {metrics['recall']:.3f}")
    print(f"  F1        : {metrics['f1']:.3f}")
    print(f"  FPR       : {metrics['fpr']:.3f}")
    print(
        f"  TP={metrics['tp']} FP={metrics['fp']} "
        f"FN={metrics['fn']} TN={metrics['tn']}  "
        f"({run['elapsed_s']}s)"
    )

    errs = [r for r in run["results"] if r.get("advisory_error")]
    if errs:
        print(f"\n  Advisory errors ({len(errs)}):")
        for r in errs:
            print(f"    - {r['id']}: {r['advisory_error']}")

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps({"metrics": metrics}, indent=2) + "\n")
        print(f"\n  ✓ Baseline written → {BASELINE_PATH}")
        return

    if not BASELINE_PATH.exists():
        print(f"\nERROR: no baseline at {BASELINE_PATH}")
        print("Generate one with: python3 tests/layer3_ci_check.py --update-baseline")
        sys.exit(1)

    baseline = json.loads(BASELINE_PATH.read_text())["metrics"]

    print(f"\n  {'Metric':<10} {'Baseline':>9} {'Current':>9} {'Delta':>8}")
    regressed = []
    for key in ("precision", "recall", "f1"):
        delta = metrics[key] - baseline[key]
        flag = "  ⚠ REGRESSED" if delta < -TOLERANCE else ""
        print(f"  {key:<10} {baseline[key]:>9.3f} {metrics[key]:>9.3f} {delta:>+8.3f}{flag}")
        if delta < -TOLERANCE:
            regressed.append(key)

    if regressed:
        print(
            f"\nFAILED: {', '.join(regressed)} regressed by more than "
            f"{TOLERANCE:.2f} vs baseline."
        )
        print("If this is an intentional prompt/model change, update the baseline with:")
        print("  python3 tests/layer3_ci_check.py --update-baseline")
        sys.exit(1)

    print("\nOK — within tolerance of baseline.")


if __name__ == "__main__":
    main()
