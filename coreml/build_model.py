#!/usr/bin/env python3
"""
Build and export the LocalForge CoreML security classifier.

Produces:
  coreml/LocalForgeModel.mlpackage  — CoreML model (CPU_AND_NE)
  coreml/tfidf_vectorizer.pkl       — TF-IDF vectorizer for the inference shim

Inference pipeline (used by coreml/infer.py and ane_bridge.rs):
  1. TF-IDF char n-gram vectorization  (Python, coreml/infer.py)
  2. Inner product + sigmoid           (CoreML → Apple Neural Engine)
  3. Threshold at 0.5                  (infer.py)  → risk_label 0 or 1
"""

import os
import pickle
import numpy as np
import coremltools as ct
from coremltools.models import MLModel
from coremltools.models.neural_network import NeuralNetworkBuilder
import coremltools.models.datatypes as datatypes
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(OUTPUT_DIR, "LocalForgeModel.mlpackage")
TFIDF_PATH = os.path.join(OUTPUT_DIR, "tfidf_vectorizer.pkl")
N_FEATURES = 512

# ── Training data ─────────────────────────────────────────────────────────────

SAMPLES = [
    # Risky: hardcoded credentials
    ("password = 'hunter2'",                                              1),
    ("db_password = 'supersecret123'",                                    1),
    ("PASSWORD = 'admin'",                                                1),
    ("passwd = '12345678'",                                               1),
    ("secret = 'mysecretvalue'",                                          1),
    ("api_key = 'hardcodedkeyvalue'",                                     1),
    ("credentials = {'user': 'admin', 'pass': 'letmein'}",               1),
    ("connection_string = 'Server=prod;Password=p@ssw0rd'",              1),
    ("auth_token = 'Bearer supersecrettoken123'",                         1),
    ("private_key_pem = open('id_rsa').read()",                           1),
    # Risky: insecure patterns
    ("subprocess.call(user_input, shell=True)",                           1),
    ("eval(request.GET['cmd'])",                                          1),
    ("os.system(f'rm -rf {path}')",                                       1),
    ("cursor.execute('SELECT * FROM users WHERE id=' + user_id)",         1),
    ("pickle.loads(untrusted_data)",                                      1),
    ("exec(compile(source, '<string>', 'exec'))",                         1),
    ("verify=False",                                                      1),
    ("ssl._create_unverified_context()",                                  1),
    ("hashlib.md5(password.encode())",                                    1),
    ("DES.new(key, DES.MODE_ECB)",                                        1),
    ("eval(user_input)",                                                  1),
    ("eval(request.args.get('code'))",                                    1),
    ("eval(data['expr'])",                                                1),
    ("__import__(user_module)",                                           1),
    ("globals()[func_name]()",                                            1),
    ("SECRET_KEY = 'change_me_in_production'",                            1),
    ("MASTER_PASSWORD = 'default'",                                       1),
    ("encryption_key = b'0000000000000000'",                              1),
    ("jwt_secret = 'not-very-secret'",                                    1),
    ("oauth_secret = 'oauth_hardcoded'",                                  1),
    # Clean: normal code
    ("def calculate_total(items): return sum(i.price for i in items)",    0),
    ("class UserService: def __init__(self, db): self.db = db",           0),
    ("import os; path = os.path.join(base, filename)",                    0),
    ("logger.info('Processing request %s', request_id)",                  0),
    ("result = [x * 2 for x in range(10)]",                              0),
    ("if user.is_authenticated: return redirect('dashboard')",           0),
    ("with open(filepath, 'r') as f: data = json.load(f)",               0),
    ("assert response.status_code == 200",                                0),
    ("def test_login(client): resp = client.post('/login', data={})",     0),
    ("return Response({'status': 'ok'}, status=200)",                     0),
    ("fn main() { println!(\"Hello, world!\"); }",                        0),
    ("let x: u32 = 42;",                                                  0),
    ("pub struct Config { pub port: u16, pub host: String }",             0),
    ("SELECT id, name FROM users WHERE active = true",                    0),
    ("def hash_password(p): return bcrypt.hashpw(p, bcrypt.gensalt())",  0),
    ("requests.get(url, verify=True, timeout=30)",                        0),
    ("password = os.environ.get('DB_PASSWORD')",                          0),
    ("secret_key = config['SECRET_KEY']",                                 0),
    ("api_key = os.getenv('API_KEY')",                                    0),
    ("CREATE TABLE sessions (id UUID PRIMARY KEY)",                       0),
]

texts  = [s for s, _ in SAMPLES]
labels = np.array([l for _, l in SAMPLES])

# ── Train sklearn pipeline ────────────────────────────────────────────────────

print("[build_model] Training TF-IDF + Logistic Regression ...")
sklearn_pipe = Pipeline([
    ("tfidf", TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        max_features=N_FEATURES,
        sublinear_tf=True,
    )),
    ("clf", LogisticRegression(
        C=1.0, max_iter=1000,
        class_weight="balanced",
        random_state=42,
    )),
])
sklearn_pipe.fit(texts, labels)

preds    = sklearn_pipe.predict(texts)
accuracy = np.mean(preds == labels)
print(f"[build_model] Training accuracy: {accuracy:.2%}  ({int(np.sum(preds == labels))}/{len(labels)})")

tfidf   = sklearn_pipe.named_steps["tfidf"]
clf     = sklearn_pipe.named_steps["clf"]
weights = clf.coef_.astype(np.float32)       # shape (1, N_FEATURES)
bias    = clf.intercept_.astype(np.float32)  # shape (1,)

# ── Build CoreML NeuralNetwork ────────────────────────────────────────────────
# Simple regression network: inner product → sigmoid → scalar risk score.
# No classifier mode needed — thresholding happens in the Python infer shim.

print("[build_model] Building CoreML NeuralNetwork ...")

input_features  = [("tfidf_features", datatypes.Array(N_FEATURES))]
output_features = [("risk_score",     datatypes.Array(1))]

builder = NeuralNetworkBuilder(input_features, output_features)

builder.add_inner_product(
    name            = "fc",
    W               = weights,
    b               = bias,
    input_channels  = N_FEATURES,
    output_channels = 1,
    has_bias        = True,
    input_name      = "tfidf_features",
    output_name     = "logit",
)

builder.add_activation(
    name            = "sigmoid",
    non_linearity   = "SIGMOID",
    input_name      = "logit",
    output_name     = "risk_score",
)

# ── Save model ────────────────────────────────────────────────────────────────

print(f"[build_model] Saving to {MODEL_PATH} ...")
model = MLModel(builder.spec)
model.author            = "LocalForge v2.0 — StalWrites"
model.short_description = "Security risk scorer for staged code diffs (0=clean, 1=risky)"
model.input_description["tfidf_features"] = \
    "TF-IDF char n-gram feature vector (dim=512)"
model.output_description["risk_score"] = \
    "Sigmoid risk score: >0.5 = risky, <=0.5 = clean"
model.save(MODEL_PATH)
print("[build_model] Model saved.")

with open(TFIDF_PATH, "wb") as f:
    pickle.dump(tfidf, f)
print(f"[build_model] Vectorizer saved to {TFIDF_PATH}")

# ── Verify round-trip ─────────────────────────────────────────────────────────

print("[build_model] Verifying saved model on ANE (CPU_AND_NE) ...")
loaded = MLModel(MODEL_PATH, compute_units=ct.ComputeUnit.CPU_AND_NE)
with open(TFIDF_PATH, "rb") as f:
    loaded_tfidf = pickle.load(f)

test_cases = [
    ("password = 'hunter2'",                1),
    ("def add(a, b): return a + b",         0),
    ("eval(request.GET['cmd'])",            1),
    ("api_key = os.getenv('API_KEY')",      0),
    ("verify=False",                        1),
    ("let x: u32 = 42;",                    0),
]

all_ok = True
for text, expected in test_cases:
    vec    = loaded_tfidf.transform([text]).toarray().astype(np.float32)[0]
    result = loaded.predict({"tfidf_features": vec})
    score  = float(np.array(result["risk_score"]).flatten()[0])
    got    = 1 if score > 0.5 else 0
    status = "PASS" if got == expected else "FAIL"
    if got != expected:
        all_ok = False
    print(f"  [{status}] score={score:.3f} label={got} expected={expected}  '{text[:55]}'")

print()
if all_ok:
    print("[build_model] All checks passed.")
else:
    print("[build_model] WARNING: some checks failed — model still saved.")

print(f"\n[build_model] Artifacts:")
print(f"  {MODEL_PATH}")
print(f"  {TFIDF_PATH}")
print(f"  Compute unit: CPU_AND_NE (Apple Neural Engine)")
