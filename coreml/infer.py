#!/usr/bin/env python3
"""
LocalForge ANE inference shim.

Called by ane_bridge.rs as a subprocess:
  python3 coreml/infer.py "<diff text>"

Exits 0 (clean) or 2 (risky). Exit 1 = internal error.
Prints a single JSON line to stdout:
  {"risk_score": 0.72, "risk_label": 1, "advisory": "..."}
"""

import sys
import os
import json
import pickle
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _find_artifact(name):
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".localforge", name),
        os.path.join(SCRIPT_DIR, name),
        os.path.join(SCRIPT_DIR, "..", "coreml", name),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return os.path.join(home, ".localforge", name)

MODEL_PATH = _find_artifact("LocalForgeModel.mlpackage")
TFIDF_PATH = _find_artifact("tfidf_vectorizer.pkl")
THRESHOLD  = 0.5

def load_ane():
    """Load the CoreML model + TF-IDF vectorizer. Raises on missing artifacts.

    Kept separate from run_infer() so callers that want to hold the model
    resident across many diffs (the daemon) load it once and reuse it.
    """
    # Lazy imports — keep startup fast when model files are missing
    import coremltools as ct
    from coremltools.models import MLModel

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}. Run: python3 coreml/build_model.py")
    if not os.path.exists(TFIDF_PATH):
        raise FileNotFoundError(f"Vectorizer not found: {TFIDF_PATH}. Run: python3 coreml/build_model.py")

    with open(TFIDF_PATH, "rb") as f:
        tfidf = pickle.load(f)
    model = MLModel(MODEL_PATH, compute_units=ct.ComputeUnit.CPU_AND_NE)
    return model, tfidf

def run_infer(diff_text, model, tfidf):
    """Score one diff against an already-loaded model + vectorizer."""
    vec    = tfidf.transform([diff_text]).toarray().astype(np.float32)[0]
    result = model.predict({"tfidf_features": vec})
    score  = float(np.array(result["risk_score"]).flatten()[0])
    label  = 1 if score > THRESHOLD else 0

    advisory = None
    if label == 1:
        advisory = (
            f"ANE classifier flagged this diff as high-risk "
            f"(score={score:.3f}). Possible hardcoded credential, "
            f"insecure function call, or weak cryptography. "
            f"Review before committing."
        )

    output = {"risk_score": round(score, 4), "risk_label": label}
    if advisory:
        output["advisory"] = advisory
    return output, label

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No diff text provided"}))
        sys.exit(1)

    diff_text = sys.argv[1]

    try:
        model, tfidf = load_ane()
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    output, label = run_infer(diff_text, model, tfidf)
    print(json.dumps(output))
    sys.exit(2 if label == 1 else 0)

if __name__ == "__main__":
    main()
