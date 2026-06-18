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
MODEL_PATH = os.path.join(SCRIPT_DIR, "LocalForgeModel.mlpackage")
TFIDF_PATH = os.path.join(SCRIPT_DIR, "tfidf_vectorizer.pkl")
THRESHOLD  = 0.5

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No diff text provided"}))
        sys.exit(1)

    diff_text = sys.argv[1]

    if not os.path.exists(MODEL_PATH):
        print(json.dumps({"error": f"Model not found: {MODEL_PATH}. Run: python3 coreml/build_model.py"}))
        sys.exit(1)

    if not os.path.exists(TFIDF_PATH):
        print(json.dumps({"error": f"Vectorizer not found: {TFIDF_PATH}. Run: python3 coreml/build_model.py"}))
        sys.exit(1)

    # Lazy imports — keep startup fast when model files are missing
    import coremltools as ct
    from coremltools.models import MLModel

    with open(TFIDF_PATH, "rb") as f:
        tfidf = pickle.load(f)

    model = MLModel(MODEL_PATH, compute_units=ct.ComputeUnit.CPU_AND_NE)

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

    print(json.dumps(output))
    sys.exit(2 if label == 1 else 0)

if __name__ == "__main__":
    main()
