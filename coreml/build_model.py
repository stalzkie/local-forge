#!/usr/bin/env python3
"""
Build and export the LocalForge CoreML security classifier (Layer 2).

Produces:
  coreml/LocalForgeModel.mlpackage  — CoreML model (CPU_AND_NE)
  coreml/tfidf_vectorizer.pkl       — TF-IDF vectorizer for infer.py
  coreml/model_metadata.json        — accuracy, date, sample count, threshold
"""

import os
import json
import pickle
import datetime
import numpy as np
import coremltools as ct
from coremltools.models import MLModel
from coremltools.models.neural_network import NeuralNetworkBuilder
import coremltools.models.datatypes as datatypes
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(OUTPUT_DIR, "LocalForgeModel.mlpackage")
TFIDF_PATH = os.path.join(OUTPUT_DIR, "tfidf_vectorizer.pkl")
META_PATH  = os.path.join(OUTPUT_DIR, "model_metadata.json")
N_FEATURES = 512
THRESHOLD  = 0.5

# ── Training data ─────────────────────────────────────────────────────────────
# Label 1 = risky, 0 = clean.

SAMPLES = [
    # --- Hardcoded credentials ---
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
    ("token = 'abc123secrettoken'",                                       1),
    ("db_pass = 'root'",                                                  1),
    ("admin_password = 'Password1!'",                                     1),
    ("config['password'] = 'hardcoded_pw'",                               1),
    ("SECRET = 'do_not_commit_this'",                                     1),
    # --- Code injection / unsafe execution ---
    ("subprocess.call(user_input, shell=True)",                           1),
    ("eval(request.GET['cmd'])",                                          1),
    ("os.system(f'rm -rf {path}')",                                       1),
    ("cursor.execute('SELECT * FROM users WHERE id=' + user_id)",         1),
    ("pickle.loads(untrusted_data)",                                      1),
    ("exec(compile(source, '<string>', 'exec'))",                         1),
    ("eval(user_input)",                                                  1),
    ("eval(request.args.get('code'))",                                    1),
    ("eval(data['expr'])",                                                1),
    ("__import__(user_module)",                                           1),
    ("globals()[func_name]()",                                            1),
    ("os.popen(cmd).read()",                                              1),
    ("subprocess.check_output(cmd, shell=True)",                          1),
    ("commands.getoutput(user_cmd)",                                      1),
    ("Runtime.getRuntime().exec(userInput)",                              1),
    # --- Disabled security / weak crypto ---
    ("verify=False",                                                      1),
    ("ssl._create_unverified_context()",                                  1),
    ("hashlib.md5(password.encode())",                                    1),
    ("DES.new(key, DES.MODE_ECB)",                                        1),
    ("requests.get(url, verify=False)",                                   1),
    ("ssl_verify = False",                                                1),
    ("check_hostname = False",                                            1),
    ("MD5(password)",                                                     1),
    ("SHA1(data)",                                                        1),
    ("RC4.encrypt(key, plaintext)",                                       1),
    # --- Hardcoded secret-named assignments ---
    ("SECRET_KEY = 'change_me_in_production'",                            1),
    ("MASTER_PASSWORD = 'default'",                                       1),
    ("encryption_key = b'0000000000000000'",                              1),
    ("jwt_secret = 'not-very-secret'",                                    1),
    ("oauth_secret = 'oauth_hardcoded'",                                  1),
    ("DJANGO_SECRET_KEY = 'dev-only-key'",                                1),
    ("Flask.secret_key = 'dev'",                                          1),
    ("signing_secret = 'placeholder'",                                    1),
    ("webhook_secret = '1234567890'",                                     1),
    ("client_secret = 'mysecret'",                                        1),
    # --- Clean: normal application code ---
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
    ("jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])",      0),
    ("cipher = AES.new(key, AES.MODE_GCM)",                               0),
    ("hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()",        0),
    ("os.urandom(32)",                                                    0),
    ("secrets.token_hex(32)",                                             0),
    ("bcrypt.checkpw(password, hashed)",                                  0),
    ("parameterized query WHERE id = %s', (user_id,))",                   0),
    ("subprocess.run(['ls', '-la'], capture_output=True)",                0),
    ("shlex.split(user_command)",                                         0),
    ("ssl.create_default_context()",                                      0),
    ("certifi.where()",                                                   0),
]

texts  = [s for s, _ in SAMPLES]
labels = np.array([l for _, l in SAMPLES])

# ── Train ─────────────────────────────────────────────────────────────────────

print("[build_model] Training TF-IDF + Logistic Regression ...")
sklearn_pipe = Pipeline([
    ("tfidf", TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        max_features=N_FEATURES,
        sublinear_tf=True,
    )),
    ("clf", LogisticRegression(
        C=2.0, max_iter=2000,
        class_weight="balanced",
        random_state=42,
    )),
])
sklearn_pipe.fit(texts, labels)

train_preds    = sklearn_pipe.predict(texts)
train_accuracy = float(np.mean(train_preds == labels))

# 5-fold cross-validation for a honest accuracy estimate
cv_scores   = cross_val_score(sklearn_pipe, texts, labels, cv=5, scoring="f1")
cv_f1_mean  = float(cv_scores.mean())
cv_f1_std   = float(cv_scores.std())

print(f"[build_model] Train accuracy : {train_accuracy:.2%}  ({int(np.sum(train_preds==labels))}/{len(labels)})")
print(f"[build_model] CV F1 (5-fold) : {cv_f1_mean:.3f} ± {cv_f1_std:.3f}")

tfidf   = sklearn_pipe.named_steps["tfidf"]
clf     = sklearn_pipe.named_steps["clf"]
weights = clf.coef_.astype(np.float32)
bias    = clf.intercept_.astype(np.float32)

# ── Build CoreML NeuralNetwork ────────────────────────────────────────────────

print("[build_model] Building CoreML NeuralNetwork ...")
input_features  = [("tfidf_features", datatypes.Array(N_FEATURES))]
output_features = [("risk_score",     datatypes.Array(1))]
builder = NeuralNetworkBuilder(input_features, output_features)

builder.add_inner_product(
    name="fc", W=weights, b=bias,
    input_channels=N_FEATURES, output_channels=1,
    has_bias=True,
    input_name="tfidf_features", output_name="logit",
)
builder.add_activation(
    name="sigmoid", non_linearity="SIGMOID",
    input_name="logit", output_name="risk_score",
)

# ── Save model ────────────────────────────────────────────────────────────────

print(f"[build_model] Saving to {MODEL_PATH} ...")
model = MLModel(builder.spec)
model.author            = "LocalForge v2.0 — StalWrites"
model.short_description = "Layer 2 security risk scorer (0=clean, 1=risky)"
model.save(MODEL_PATH)

with open(TFIDF_PATH, "wb") as f:
    pickle.dump(tfidf, f)

# ── Verify ────────────────────────────────────────────────────────────────────

print("[build_model] Verifying on Apple Neural Engine ...")
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
    ("requests.get(url, verify=False)",     1),
    ("ssl.create_default_context()",        0),
    ("jwt_secret = 'not-very-secret'",      1),
    ("secrets.token_hex(32)",               0),
]

passed = 0
results_log = []
for text, expected in test_cases:
    vec    = loaded_tfidf.transform([text]).toarray().astype(np.float32)[0]
    result = loaded.predict({"tfidf_features": vec})
    score  = float(np.array(result["risk_score"]).flatten()[0])
    got    = 1 if score > THRESHOLD else 0
    ok     = got == expected
    if ok:
        passed += 1
    status = "PASS" if ok else "FAIL"
    results_log.append({"text": text, "score": round(score, 4), "label": got, "expected": expected, "pass": ok})
    print(f"  [{status}] score={score:.3f} label={got} expected={expected}  '{text[:55]}'")

verify_accuracy = passed / len(test_cases)
print(f"\n[build_model] Verification: {passed}/{len(test_cases)} passed ({verify_accuracy:.0%})")

# ── Persist metadata ──────────────────────────────────────────────────────────

metadata = {
    "built_at":           datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "model_version":      "2.0.0",
    "layer":              2,
    "architecture":       "TF-IDF (char_wb 3-5gram, 512 features) + Inner Product + Sigmoid (CoreML)",
    "compute_unit":       "CPU_AND_NE",
    "n_training_samples": len(texts),
    "n_risky":            int(np.sum(labels == 1)),
    "n_clean":            int(np.sum(labels == 0)),
    "train_accuracy":     round(train_accuracy, 4),
    "cv_f1_mean":         round(cv_f1_mean, 4),
    "cv_f1_std":          round(cv_f1_std, 4),
    "threshold":          THRESHOLD,
    "verification": {
        "n_cases":  len(test_cases),
        "passed":   passed,
        "accuracy": round(verify_accuracy, 4),
        "cases":    results_log,
    },
    "artifacts": {
        "model":      "LocalForgeModel.mlpackage",
        "vectorizer": "tfidf_vectorizer.pkl",
        "metadata":   "model_metadata.json",
    },
}

with open(META_PATH, "w") as f:
    json.dump(metadata, f, indent=2)

print(f"[build_model] Metadata saved to {META_PATH}")
print(f"\n[build_model] Summary:")
print(f"  Train accuracy : {train_accuracy:.2%}")
print(f"  CV F1 (5-fold) : {cv_f1_mean:.3f} ± {cv_f1_std:.3f}")
print(f"  Samples        : {len(texts)} ({int(np.sum(labels==1))} risky, {int(np.sum(labels==0))} clean)")
print(f"  Threshold      : {THRESHOLD}")
print(f"  Compute unit   : CPU_AND_NE (Apple Neural Engine)")
