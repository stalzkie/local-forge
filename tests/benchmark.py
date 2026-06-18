#!/usr/bin/env python3
"""
LocalForge v2.0 — Comprehensive Performance Benchmark
Generates 6 matplotlib visualizations across all 3 pipeline layers.

80 labeled samples:
  - 20 clean         (ground truth: no issues)
  - 20 security      (ground truth: security finding)
  - 20 bug_risk      (ground truth: bug risk)
  - 20 quality       (ground truth: code quality)

Usage:
  python3 tests/benchmark.py
  python3 tests/benchmark.py --skip-qwen   # fast run, L1+L2 only
"""

import subprocess
import time
import json
import sys
import os
import argparse
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BINARY    = REPO_ROOT / "target" / "release" / "localforge"
INFER_PY  = REPO_ROOT / "coreml" / "infer.py"
ADV_PY    = REPO_ROOT / "coreml" / "advisory.py"
OUT_DIR   = REPO_ROOT / "tests" / "benchmark_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Color palette ──────────────────────────────────────────────────────────────
C = {
    "bg":       "#0d0d0f",
    "panel":    "#141418",
    "border":   "#2a2a35",
    "cyan":     "#00d4ff",
    "blue":     "#4488ff",
    "purple":   "#cc66ff",
    "green":    "#00ff88",
    "red":      "#ff4444",
    "yellow":   "#ffcc00",
    "gray":     "#888899",
    "white":    "#e8e8f0",
}

def style_fig(fig, ax_list):
    fig.patch.set_facecolor(C["bg"])
    for ax in (ax_list if isinstance(ax_list, list) else [ax_list]):
        ax.set_facecolor(C["panel"])
        ax.tick_params(colors=C["white"], labelsize=8)
        ax.xaxis.label.set_color(C["white"])
        ax.yaxis.label.set_color(C["white"])
        ax.title.set_color(C["white"])
        for spine in ax.spines.values():
            spine.set_edgecolor(C["border"])

def save(fig, name):
    path = OUT_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print(f"  Saved → {path}")


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE CORPUS — 80 labeled diffs
# ══════════════════════════════════════════════════════════════════════════════

SAMPLES = [
    # ── CLEAN (20) ────────────────────────────────────────────────────────────
    {"label": "clean", "lang": "python", "code": "def add(a, b):\n    return a + b\n"},
    {"label": "clean", "lang": "rust",   "code": "fn main() {\n    println!(\"hello world\");\n}\n"},
    {"label": "clean", "lang": "python", "code": "import os\npath = os.path.join('/tmp', 'output.txt')\nwith open(path, 'w') as f:\n    f.write('done')\n"},
    {"label": "clean", "lang": "js",     "code": "const greet = (name) => `Hello, ${name}`;\nmodule.exports = { greet };\n"},
    {"label": "clean", "lang": "python", "code": "class Config:\n    DEBUG = False\n    HOST = 'localhost'\n    PORT = 8080\n"},
    {"label": "clean", "lang": "rust",   "code": "pub fn fibonacci(n: u32) -> u64 {\n    if n <= 1 { return n as u64; }\n    let (mut a, mut b) = (0u64, 1u64);\n    for _ in 2..=n { let c = a + b; a = b; b = c; }\n    b\n}\n"},
    {"label": "clean", "lang": "python", "code": "def parse_config(path: str) -> dict:\n    import json\n    with open(path) as f:\n        return json.load(f)\n"},
    {"label": "clean", "lang": "js",     "code": "async function fetchData(url) {\n    const res = await fetch(url);\n    if (!res.ok) throw new Error(`HTTP ${res.status}`);\n    return res.json();\n}\n"},
    {"label": "clean", "lang": "python", "code": "from pathlib import Path\ndef list_files(directory: str):\n    return list(Path(directory).glob('*.py'))\n"},
    {"label": "clean", "lang": "rust",   "code": "use std::collections::HashMap;\nfn word_count(s: &str) -> HashMap<&str, usize> {\n    let mut map = HashMap::new();\n    for w in s.split_whitespace() { *map.entry(w).or_insert(0) += 1; }\n    map\n}\n"},
    {"label": "clean", "lang": "python", "code": "import hashlib\ndef hash_password(password: str, salt: str) -> str:\n    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()\n"},
    {"label": "clean", "lang": "js",     "code": "function debounce(fn, delay) {\n    let timer;\n    return (...args) => {\n        clearTimeout(timer);\n        timer = setTimeout(() => fn(...args), delay);\n    };\n}\n"},
    {"label": "clean", "lang": "python", "code": "def retry(fn, attempts=3, delay=1.0):\n    import time\n    for i in range(attempts):\n        try:\n            return fn()\n        except Exception:\n            if i == attempts - 1:\n                raise\n            time.sleep(delay)\n"},
    {"label": "clean", "lang": "rust",   "code": "pub struct Cache<T> {\n    data: std::collections::HashMap<String, T>,\n    capacity: usize,\n}\nimpl<T> Cache<T> {\n    pub fn new(capacity: usize) -> Self {\n        Self { data: Default::default(), capacity }\n    }\n}\n"},
    {"label": "clean", "lang": "python", "code": "import logging\nlogger = logging.getLogger(__name__)\ndef process(items):\n    for item in items:\n        logger.debug('processing %s', item)\n"},
    {"label": "clean", "lang": "js",     "code": "class EventEmitter {\n    constructor() { this.listeners = {}; }\n    on(event, fn) { (this.listeners[event] ||= []).push(fn); }\n    emit(event, ...args) { (this.listeners[event] || []).forEach(fn => fn(...args)); }\n}\n"},
    {"label": "clean", "lang": "python", "code": "def paginate(items, page_size=20):\n    for i in range(0, len(items), page_size):\n        yield items[i:i + page_size]\n"},
    {"label": "clean", "lang": "rust",   "code": "pub fn clamp(value: f32, min: f32, max: f32) -> f32 {\n    value.max(min).min(max)\n}\n"},
    {"label": "clean", "lang": "python", "code": "from typing import Optional\ndef find_user(users: list, user_id: int) -> Optional[dict]:\n    return next((u for u in users if u['id'] == user_id), None)\n"},
    {"label": "clean", "lang": "js",     "code": "const sanitize = (str) => str.replace(/[<>&\"']/g, c => ({\n    '<':'&lt;','>':'&gt;','&':'&amp;','\"':'&quot;',\"'\":'&#x27;'\n})[c]);\n"},

    # ── SECURITY (20) ─────────────────────────────────────────────────────────
    {"label": "security", "lang": "python", "code": "import boto3\nAWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\nAWS_SECRET = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'\nclient = boto3.client('s3', aws_access_key_id=AWS_KEY, aws_secret_access_key=AWS_SECRET)\n"},
    {"label": "security", "lang": "python", "code": "def get_user(user_id):\n    query = 'SELECT * FROM users WHERE id = ' + user_id\n    return db.execute(query)\n"},
    {"label": "security", "lang": "python", "code": "import subprocess\ndef run_command(user_input):\n    result = subprocess.run(user_input, shell=True, capture_output=True)\n    return result.stdout\n"},
    {"label": "security", "lang": "js",     "code": "app.get('/page', (req, res) => {\n    const name = req.query.name;\n    res.send(`<h1>Hello ${name}</h1>`);\n});\n"},
    {"label": "security", "lang": "python", "code": "import pickle\ndef load_session(data: bytes):\n    return pickle.loads(data)\n"},
    {"label": "security", "lang": "python", "code": "STRIPE_KEY = 'sk_live_' + 'abcdefghijklmnopqrstuvwx'\npayment = stripe.PaymentIntent.create(amount=1000, currency='usd', api_key=STRIPE_KEY)\n"},
    {"label": "security", "lang": "js",     "code": "const token = 'ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';\nfetch('https://api.github.com/user', { headers: { Authorization: `token ${token}` } });\n"},
    {"label": "security", "lang": "python", "code": "def render_template(user_input):\n    from jinja2 import Template\n    t = Template(user_input)\n    return t.render()\n"},
    {"label": "security", "lang": "python", "code": "import yaml\ndef load_config(path):\n    with open(path) as f:\n        return yaml.load(f)\n"},
    {"label": "security", "lang": "python", "code": "import hashlib\ndef hash_pw(pw):\n    return hashlib.md5(pw.encode()).hexdigest()\n"},
    {"label": "security", "lang": "js",     "code": "const crypto = require('crypto');\nfunction encrypt(data, key) {\n    const cipher = crypto.createCipher('des', key);\n    return cipher.update(data, 'utf8', 'hex') + cipher.final('hex');\n}\n"},
    {"label": "security", "lang": "python", "code": "def read_file(filename):\n    base = '/var/www/uploads/'\n    return open(base + filename).read()\n"},
    {"label": "security", "lang": "python", "code": "DATABASE_URL = 'postgresql://admin:password123@localhost:5432/prod'\ndef get_db():\n    return psycopg2.connect(DATABASE_URL)\n"},
    {"label": "security", "lang": "python", "code": "def verify_token(token):\n    import jwt\n    return jwt.decode(token, options={'verify_signature': False})\n"},
    {"label": "security", "lang": "python", "code": "import xml.etree.ElementTree as ET\ndef parse_xml(user_data):\n    tree = ET.fromstring(user_data)\n    return tree.find('user').text\n"},
    {"label": "security", "lang": "js",     "code": "function setUserPrefs(prefs) {\n    document.cookie = 'session=' + JSON.stringify(prefs);\n    localStorage.setItem('user', JSON.stringify(prefs));\n}\n"},
    {"label": "security", "lang": "python", "code": "import os\ndef admin_panel(request):\n    if request.GET.get('debug') == 'true':\n        return os.popen(request.GET.get('cmd', 'id')).read()\n"},
    {"label": "security", "lang": "rust",   "code": "use std::ptr;\nunsafe fn copy_bytes(src: *const u8, dst: *mut u8, len: usize) {\n    ptr::copy_nonoverlapping(src, dst, len * 1000);\n}\n"},
    {"label": "security", "lang": "python", "code": "PRIVATE_KEY = '-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKCAQEA...\\n-----END RSA PRIVATE KEY-----'\n"},
    {"label": "security", "lang": "python", "code": "def login(username, password):\n    query = f\"SELECT * FROM users WHERE username='{username}' AND password='{password}'\"\n    result = cursor.execute(query)\n    return result.fetchone() is not None\n"},

    # ── BUG RISK (20) ─────────────────────────────────────────────────────────
    {"label": "bug_risk", "lang": "python", "code": "def divide(a, b):\n    return a / b\n"},
    {"label": "bug_risk", "lang": "python", "code": "def get_first(items):\n    return items[0]\n"},
    {"label": "bug_risk", "lang": "js",     "code": "function getUser(id) {\n    const user = users.find(u => u.id === id);\n    return user.name;\n}\n"},
    {"label": "bug_risk", "lang": "python", "code": "import threading\ncounter = 0\ndef increment():\n    global counter\n    counter += 1\nthreads = [threading.Thread(target=increment) for _ in range(100)]\nfor t in threads: t.start()\n"},
    {"label": "bug_risk", "lang": "python", "code": "def read_config(path):\n    f = open(path)\n    data = f.read()\n    return json.loads(data)\n"},
    {"label": "bug_risk", "lang": "rust",   "code": "fn get_element(v: &Vec<i32>, index: usize) -> i32 {\n    v[index]\n}\n"},
    {"label": "bug_risk", "lang": "python", "code": "def process_list(items):\n    result = []\n    for i in range(len(items) + 1):\n        result.append(items[i] * 2)\n    return result\n"},
    {"label": "bug_risk", "lang": "js",     "code": "async function loadData() {\n    const data = await fetch('/api/data').then(r => r.json());\n    console.log(data.items.length);\n}\n"},
    {"label": "bug_risk", "lang": "python", "code": "def is_admin(user):\n    if user.role != 'admin':\n        return True\n    return False\n"},
    {"label": "bug_risk", "lang": "python", "code": "cache = {}\ndef get_cached(key, fn):\n    if not key in cache:\n        cache[key] == fn()\n    return cache[key]\n"},
    {"label": "bug_risk", "lang": "python", "code": "def merge_dicts(a, b):\n    a.update(b)\n    return a\n"},
    {"label": "bug_risk", "lang": "js",     "code": "function sum(arr) {\n    let total = 0;\n    for (let i = 0; i <= arr.length; i++) {\n        total += arr[i];\n    }\n    return total;\n}\n"},
    {"label": "bug_risk", "lang": "python", "code": "import requests\ndef call_api(url):\n    response = requests.get(url)\n    return response.json()['data']\n"},
    {"label": "bug_risk", "lang": "python", "code": "def flatten(nested):\n    result = []\n    for item in nested:\n        if isinstance(item, list):\n            result + flatten(item)\n        else:\n            result.append(item)\n    return result\n"},
    {"label": "bug_risk", "lang": "rust",   "code": "fn parse_number(s: &str) -> i32 {\n    s.parse().unwrap()\n}\n"},
    {"label": "bug_risk", "lang": "python", "code": "def write_output(data, filename='/tmp/out.txt'):\n    with open(filename, 'a') as f:\n        f.write(str(data))\n"},
    {"label": "bug_risk", "lang": "js",     "code": "const config = JSON.parse(process.env.APP_CONFIG);\nconsole.log(config.database.host);\n"},
    {"label": "bug_risk", "lang": "python", "code": "def timeout_handler():\n    import signal\n    signal.alarm(0)\ndef run_with_timeout(fn, seconds):\n    signal.signal(signal.SIGALRM, timeout_handler)\n    signal.alarm(seconds)\n    fn()\n"},
    {"label": "bug_risk", "lang": "python", "code": "class Singleton:\n    _instance = None\n    def __new__(cls):\n        if not cls._instance:\n            cls._instance = super().__new__(cls)\n        return cls._instance\n    def reset(self):\n        Singleton._instance = None\n"},
    {"label": "bug_risk", "lang": "js",     "code": "let items = [];\nfunction addItem(item) { items.push(item); }\nfunction clearItems() { items = []; }\nsetInterval(() => console.log(items.length), 1000);\n"},

    # ── QUALITY (20) ──────────────────────────────────────────────────────────
    {"label": "quality", "lang": "python", "code": "def calculate(x, y, z, w, v, u):\n    temp1 = x * y\n    temp2 = z + w\n    temp3 = v - u\n    temp4 = temp1 / temp2\n    temp5 = temp4 * temp3\n    temp6 = temp5 + temp1\n    return temp6\n"},
    {"label": "quality", "lang": "python", "code": "def unused_helper(a, b):\n    return a ** b + 42\n\ndef main():\n    print('hello')\n"},
    {"label": "quality", "lang": "js",     "code": "function processData(data) {\n    var result = null;\n    var temp = null;\n    var flag = false;\n    var count = 0;\n    result = data.map(x => x * 2);\n    return result;\n}\n"},
    {"label": "quality", "lang": "python", "code": "def get_status(code):\n    if code == 200:\n        return 'ok'\n    if code == 201:\n        return 'created'\n    if code == 400:\n        return 'bad request'\n    if code == 401:\n        return 'unauthorized'\n    if code == 403:\n        return 'forbidden'\n    if code == 404:\n        return 'not found'\n    if code == 500:\n        return 'server error'\n    return 'unknown'\n"},
    {"label": "quality", "lang": "python", "code": "x = 5\ny = 10\nz = x + y\na = z * 2\nb = a - x\nc = b + y\nd = c * z\nprint(d)\n"},
    {"label": "quality", "lang": "python", "code": "def fn1(d):\n    return d * 2\ndef fn2(d):\n    return d * 2\ndef fn3(d):\n    return d * 2\ndef compute(val):\n    return fn1(val)\n"},
    {"label": "quality", "lang": "js",     "code": "// TODO: fix this later\n// FIXME: this is broken\n// HACK: temporary workaround\nfunction doThing() {\n    // TODO: implement\n    return null;\n}\n"},
    {"label": "quality", "lang": "python", "code": "def process(items):\n    # loop through items\n    result = []  # empty list\n    for item in items:  # for each item\n        result.append(item)  # add to result\n    return result  # return the result\n"},
    {"label": "quality", "lang": "python", "code": "class DataProcessor:\n    def __init__(self):\n        self.data = []\n        self.processed = []\n        self.errors = []\n        self.warnings = []\n        self.stats = {}\n        self.config = {}\n        self.logger = None\n        self.db = None\n        self.cache = {}\n        self.queue = []\n"},
    {"label": "quality", "lang": "js",     "code": "function a(x) { return b(x); }\nfunction b(x) { return c(x); }\nfunction c(x) { return d(x); }\nfunction d(x) { return e(x); }\nfunction e(x) { return x + 1; }\n"},
    {"label": "quality", "lang": "python", "code": "def check(val):\n    if val == True:\n        return True\n    elif val == False:\n        return False\n    else:\n        return None\n"},
    {"label": "quality", "lang": "python", "code": "MAGIC_NUMBER_1 = 42\nMAGIC_NUMBER_2 = 7\nMAGIC_NUMBER_3 = 13\ndef compute(x):\n    return x * 42 / 7 + 13\n"},
    {"label": "quality", "lang": "js",     "code": "let data1 = fetchUsers();\nlet data2 = fetchUsers();\nlet data3 = fetchUsers();\nconst result = [...data1, ...data2, ...data3];\n"},
    {"label": "quality", "lang": "python", "code": "def long_function(a, b, c, d, e, f, g, h, i, j):\n    r1 = a + b\n    r2 = c - d\n    r3 = e * f\n    r4 = g / h\n    r5 = i % j\n    r6 = r1 + r2\n    r7 = r3 - r4\n    r8 = r5 * r6\n    r9 = r7 + r8\n    return r9\n"},
    {"label": "quality", "lang": "python", "code": "class UserService:\n    def get_user_by_id(self, id): pass\n    def get_user_by_email(self, email): pass\n    def get_user_by_username(self, username): pass\n    def get_user_by_phone(self, phone): pass\n    def get_user_by_token(self, token): pass\n    def find_user(self, **kwargs): pass\n    def fetch_user(self, **kwargs): pass\n    def lookup_user(self, **kwargs): pass\n"},
    {"label": "quality", "lang": "rust",   "code": "fn process(v: Vec<i32>) -> Vec<i32> {\n    let mut out = Vec::new();\n    for i in 0..v.len() {\n        out.push(v[i] * 2);\n    }\n    out\n}\n"},
    {"label": "quality", "lang": "python", "code": "import os, sys, json, re, time, datetime, hashlib, hmac, base64, urllib\nfrom pathlib import Path\nfrom typing import Optional, List, Dict, Any, Tuple, Union\n\ndef do_nothing():\n    pass\n"},
    {"label": "quality", "lang": "js",     "code": "var x = 1;\nvar y = 2;\nvar z = 3;\nfunction add() { return x + y + z; }\nfunction multiply() { return x * y * z; }\nfunction unused_func() { return x - y; }\n"},
    {"label": "quality", "lang": "python", "code": "def validate(data):\n    if data is not None:\n        if len(data) > 0:\n            if isinstance(data, list):\n                if all(isinstance(x, int) for x in data):\n                    if max(data) < 1000:\n                        return True\n    return False\n"},
    {"label": "quality", "lang": "python", "code": "# v1\ndef process_v1(x): return x * 2\n# v2 (updated)\ndef process_v2(x): return x * 2\n# v3 (final)\ndef process_v3(x): return x * 2\ndef main(): return process_v3(10)\n"},
]


# ══════════════════════════════════════════════════════════════════════════════
# BENCHMARK RUNNERS
# ══════════════════════════════════════════════════════════════════════════════

import re as _re

# Compile L1 patterns once — mirrors ast_validator.rs exactly
_L1_PATTERNS = [
    _re.compile(r"AKIA[0-9A-Z]{16}"),
    _re.compile(r"(?i)(aws_secret|secret_key)\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"),
    _re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
    _re.compile(r"ghp_[A-Za-z0-9]{36}"),
    _re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
    _re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{40,}"),
    _re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]

def run_layer1(diff: str) -> tuple:
    """Returns (blocked, latency_us_as_ms) — pure Python regex, no subprocess."""
    t0 = time.perf_counter()
    blocked = any(p.search(diff) for p in _L1_PATTERNS)
    us = (time.perf_counter() - t0) * 1_000_000  # microseconds
    return blocked, us  # stored as µs, labelled as µs in graphs


def run_layer2(diff: str) -> tuple:
    """Returns (risk_score or None, latency_ms)"""
    if not INFER_PY.exists():
        return None, 0.0
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["python3", str(INFER_PY), diff],
        capture_output=True, text=True
    )
    ms = (time.perf_counter() - t0) * 1000
    try:
        data = json.loads(proc.stdout.strip())
        return float(data.get("risk_score", 0)), ms
    except Exception:
        return None, ms


def run_layer3(diff: str) -> tuple:
    """Returns (result dict or None, latency_ms)"""
    if not ADV_PY.exists():
        return None, 0.0
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["python3", str(ADV_PY), diff,
         "--log-dir", str(OUT_DIR / "advisory_log")],
        capture_output=True, text=True, timeout=120
    )
    ms = (time.perf_counter() - t0) * 1000
    try:
        data = json.loads(proc.stdout.strip())
        if "error" not in data:
            return data, ms
    except Exception:
        pass
    return None, ms


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════

def run_benchmark(skip_qwen=False):
    print(f"\n{'='*60}")
    print("  LocalForge v2.0 — Performance Benchmark")
    print(f"  {len(SAMPLES)} samples · {'L1+L2 only' if skip_qwen else 'All 3 Layers'}")
    print(f"{'='*60}\n")

    results = []

    for i, s in enumerate(SAMPLES):
        label = s["label"]
        lang  = s["lang"]
        diff  = s["code"]
        print(f"  [{i+1:02d}/{len(SAMPLES)}] {label:<10} {lang:<8}", end=" ", flush=True)

        # Layer 1
        l1_blocked, l1_ms = run_layer1(diff)

        # Layer 2
        l2_score, l2_ms = run_layer2(diff)

        # Layer 3
        l3_result, l3_ms = (None, 0.0)
        if not skip_qwen:
            l3_result, l3_ms = run_layer3(diff)

        l3_severity = l3_result.get("severity", "unknown") if l3_result else None
        l3_findings = l3_result.get("findings", [])        if l3_result else []
        l3_category = l3_findings[0].get("category") if l3_findings else None

        results.append({
            "label":       label,
            "lang":        lang,
            "l1_blocked":  l1_blocked,
            "l1_ms":       l1_ms,
            "l2_score":    l2_score,
            "l2_ms":       l2_ms,
            "l3_severity": l3_severity,
            "l3_category": l3_category,
            "l3_ms":       l3_ms,
            "l3_findings": len(l3_findings),
        })

        status = "BLOCK" if l1_blocked else (f"L2:{l2_score:.2f}" if l2_score is not None else "L2:n/a")
        l3_tag = f"L3:{l3_severity}" if l3_severity else ""
        print(f"L1:{l1_ms:.1f}µs {status} {l3_tag}")

    print(f"\n  All samples complete. Generating graphs...\n")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 1 — Layer 1 Latency Distribution
# ══════════════════════════════════════════════════════════════════════════════

def graph_l1_latency(results):
    print("  [1/6] Layer 1 latency distribution...")
    latencies = [r["l1_ms"] for r in results]
    by_label  = {}
    for r in results:
        by_label.setdefault(r["label"], []).append(r["l1_ms"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    style_fig(fig, [ax1, ax2])
    fig.suptitle("Layer 1 — AST Regex Latency", color=C["white"], fontsize=13, fontweight="bold", y=1.01)

    # Histogram (latencies in µs)
    ax1.hist(latencies, bins=20, color=C["cyan"], edgecolor=C["bg"], alpha=0.85)
    ax1.axvline(statistics.median(latencies), color=C["yellow"], linewidth=1.5, linestyle="--", label=f"Median: {statistics.median(latencies):.1f}µs")
    ax1.axvline(statistics.mean(latencies),   color=C["green"],  linewidth=1.5, linestyle=":",  label=f"Mean:   {statistics.mean(latencies):.1f}µs")
    ax1.set_xlabel("Latency (µs)")
    ax1.set_ylabel("Sample count")
    ax1.set_title("Latency distribution (all 80 samples)", color=C["white"])
    ax1.legend(fontsize=8, facecolor=C["panel"], labelcolor=C["white"])

    # Box plot per label
    label_order = ["clean", "security", "bug_risk", "quality"]
    colors_map  = {"clean": C["green"], "security": C["red"], "bug_risk": C["yellow"], "quality": C["purple"]}
    data_by_label = [by_label.get(l, []) for l in label_order]
    bp = ax2.boxplot(data_by_label, patch_artist=True, medianprops={"color": C["white"], "linewidth": 2})
    for patch, lbl in zip(bp["boxes"], label_order):
        patch.set_facecolor(colors_map[lbl])
        patch.set_alpha(0.75)
    for element in ["whiskers", "caps", "fliers"]:
        for item in bp[element]:
            item.set_color(C["gray"])
    ax2.set_xticklabels(label_order, fontsize=8)
    ax2.set_ylabel("Latency (µs)")
    ax2.set_title("Latency by sample category", color=C["white"])

    # Annotation
    p99 = sorted(latencies)[int(len(latencies) * 0.99)]
    ax1.text(0.97, 0.95, f"p99: {p99:.1f}µs\nMin: {min(latencies):.1f}µs\nMax: {max(latencies):.1f}µs",
             transform=ax1.transAxes, ha="right", va="top",
             color=C["white"], fontsize=8,
             bbox=dict(boxstyle="round,pad=0.4", facecolor=C["border"], alpha=0.8))

    plt.tight_layout()
    save(fig, "01_layer1_latency.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 2 — Layer 2 Accuracy (Confusion Matrix + Score Distribution)
# ══════════════════════════════════════════════════════════════════════════════

def graph_l2_accuracy(results):
    print("  [2/6] Layer 2 accuracy & score distribution...")
    l2_results = [r for r in results if r["l2_score"] is not None]
    if not l2_results:
        print("    Skipped — no L2 scores available.")
        return

    # Binary ground truth: security = risky, else = clean
    THRESHOLD = 0.5
    tp = fp = tn = fn = 0
    scores_risky = []
    scores_clean = []
    for r in l2_results:
        is_risky_gt    = r["label"] == "security"
        is_risky_pred  = r["l2_score"] >= THRESHOLD
        if is_risky_gt:  scores_risky.append(r["l2_score"])
        else:            scores_clean.append(r["l2_score"])
        if is_risky_gt and is_risky_pred:     tp += 1
        elif not is_risky_gt and is_risky_pred: fp += 1
        elif is_risky_gt and not is_risky_pred: fn += 1
        else:                                   tn += 1

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    style_fig(fig, [ax1, ax2])
    fig.suptitle("Layer 2 — CoreML/ANE Classifier Accuracy", color=C["white"], fontsize=13, fontweight="bold", y=1.01)

    # Confusion matrix heatmap
    cm = np.array([[tp, fp], [fn, tn]])
    labels = [["TP", "FP"], ["FN", "TN"]]
    im = ax1.imshow(cm, cmap="Blues", vmin=0)
    for i in range(2):
        for j in range(2):
            ax1.text(j, i, f"{labels[i][j]}\n{cm[i][j]}",
                     ha="center", va="center",
                     color=C["white"] if cm[i][j] > cm.max()/2 else C["bg"],
                     fontsize=14, fontweight="bold")
    ax1.set_xticks([0, 1]); ax1.set_yticks([0, 1])
    ax1.set_xticklabels(["Predicted Risky", "Predicted Clean"])
    ax1.set_yticklabels(["Actually Risky", "Actually Clean"])
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall    = tp / (tp + fn) if (tp + fn) else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
    accuracy  = (tp + tn) / len(l2_results)
    ax1.set_title(f"Confusion Matrix  |  Accuracy: {accuracy:.1%}  F1: {f1:.2f}", color=C["white"])

    # Score distribution
    bins = np.linspace(0, 1, 25)
    ax2.hist(scores_clean,  bins=bins, color=C["green"],  alpha=0.7, label="Clean samples",    edgecolor=C["bg"])
    ax2.hist(scores_risky,  bins=bins, color=C["red"],    alpha=0.7, label="Security samples", edgecolor=C["bg"])
    ax2.axvline(THRESHOLD, color=C["yellow"], linewidth=2, linestyle="--", label=f"Threshold ({THRESHOLD})")
    ax2.set_xlabel("Risk Score")
    ax2.set_ylabel("Count")
    ax2.set_title("Risk Score Distribution by Ground Truth", color=C["white"])
    ax2.legend(fontsize=8, facecolor=C["panel"], labelcolor=C["white"])

    plt.tight_layout()
    save(fig, "02_layer2_accuracy.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 3 — Layer 3 Qwen Quality & Category Breakdown
# ══════════════════════════════════════════════════════════════════════════════

def graph_l3_quality(results):
    print("  [3/6] Layer 3 Qwen findings breakdown...")
    l3_results = [r for r in results if r["l3_severity"] is not None]
    if not l3_results:
        print("    Skipped — no L3 results available.")
        return

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 5))
    style_fig(fig, [ax1, ax2, ax3])
    fig.suptitle("Layer 3 — Qwen Advisory Engine Assessment", color=C["white"], fontsize=13, fontweight="bold", y=1.01)

    # Severity distribution pie
    sev_counts = {}
    for r in l3_results:
        s = (r["l3_severity"] or "unknown").lower()
        sev_counts[s] = sev_counts.get(s, 0) + 1
    sev_colors = {"high": C["red"], "medium": C["yellow"], "low": C["blue"], "clean": C["green"], "unknown": C["gray"]}
    labels = list(sev_counts.keys())
    sizes  = list(sev_counts.values())
    colors = [sev_colors.get(l, C["gray"]) for l in labels]
    wedges, texts, autotexts = ax1.pie(sizes, labels=labels, colors=colors, autopct="%1.0f%%",
                                        startangle=90, textprops={"color": C["white"], "fontsize": 9})
    for at in autotexts:
        at.set_color(C["bg"])
        at.set_fontweight("bold")
    ax1.set_title("Severity Distribution", color=C["white"])

    # Category detection rate per ground-truth label
    label_order = ["clean", "security", "bug_risk", "quality"]
    cat_map     = {"security": C["red"], "bug_risk": C["yellow"], "quality": C["purple"], None: C["gray"]}
    detection_by_label = {l: {"found": 0, "total": 0} for l in label_order}
    for r in l3_results:
        lbl = r["label"]
        detection_by_label[lbl]["total"] += 1
        if r["l3_findings"] > 0 and r["l3_severity"] not in ("clean", None):
            detection_by_label[lbl]["found"] += 1

    rates  = [detection_by_label[l]["found"] / detection_by_label[l]["total"]
              if detection_by_label[l]["total"] else 0 for l in label_order]
    bar_colors = [C["green"], C["red"], C["yellow"], C["purple"]]
    bars = ax2.bar(label_order, rates, color=bar_colors, alpha=0.85, edgecolor=C["bg"])
    for bar, rate in zip(bars, rates):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                 f"{rate:.0%}", ha="center", va="bottom", color=C["white"], fontsize=9, fontweight="bold")
    ax2.set_ylim(0, 1.15)
    ax2.set_ylabel("Detection Rate")
    ax2.set_title("Issue Detection Rate by Category", color=C["white"])
    ax2.axhline(1.0, color=C["border"], linewidth=0.8, linestyle="--")

    # Inference time box plot
    l3_times_by_label = {l: [] for l in label_order}
    for r in l3_results:
        if r["l3_ms"] > 0:
            l3_times_by_label[r["label"]].append(r["l3_ms"] / 1000)  # → seconds
    data   = [l3_times_by_label[l] for l in label_order]
    data   = [d for d in data if d]
    labels_with_data = [l for l, d in zip(label_order, [l3_times_by_label[l] for l in label_order]) if d]
    if data:
        bp = ax3.boxplot(data, patch_artist=True,
                         medianprops={"color": C["white"], "linewidth": 2})
        for patch, lbl in zip(bp["boxes"], labels_with_data):
            patch.set_facecolor(sev_colors.get(lbl, C["purple"]))
            patch.set_alpha(0.75)
        for element in ["whiskers", "caps", "fliers"]:
            for item in bp[element]:
                item.set_color(C["gray"])
        ax3.set_xticklabels(labels_with_data, fontsize=8)
        ax3.set_ylabel("Inference time (seconds)")
        ax3.set_title("Qwen Inference Time by Category", color=C["white"])

    plt.tight_layout()
    save(fig, "03_layer3_quality.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 4 — End-to-End Pipeline Timing (stacked bar)
# ══════════════════════════════════════════════════════════════════════════════

def graph_pipeline_timing(results):
    print("  [4/6] Pipeline timing breakdown...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    style_fig(fig, [ax1, ax2])
    fig.suptitle("End-to-End Pipeline Timing", color=C["white"], fontsize=13, fontweight="bold", y=1.01)

    indices = range(len(results))
    l1_times_us = [r["l1_ms"]        for r in results]   # stored in µs
    l2_times    = [r["l2_ms"]        for r in results]   # ms
    l3_times    = [r["l3_ms"] / 1000 for r in results]   # seconds
    has_l3      = any(t > 0 for t in l3_times)

    # Stacked bar — L2 only since L1 is µs-scale (invisible on ms axis)
    ax1.bar(indices, l2_times, color=C["blue"], alpha=0.85, label="L2 CoreML (ms)")
    ax1.set_xlabel("Sample index")
    ax1.set_ylabel("Latency (ms)")
    ax1.set_title("L2 CoreML Latency Per Sample\n(L1 avg <1µs — off-scale)", color=C["white"])
    ax1.legend(fontsize=8, facecolor=C["panel"], labelcolor=C["white"])

    # Average per layer — use µs for L1, ms for L2, seconds for L3 (separate axes)
    avg_l1_us = statistics.mean(l1_times_us)
    avg_l2_ms = statistics.mean(l2_times)
    avg_l3_s  = statistics.mean([t for t in l3_times if t > 0]) if has_l3 else None

    layer_labels = ["L1 AST\n(µs)", "L2 CoreML\n(ms)"]
    layer_values = [avg_l1_us / 1000, avg_l2_ms]   # both in ms for log scale
    layer_colors = [C["cyan"], C["blue"]]
    layer_annot  = [f"{avg_l1_us:.1f}µs", f"{avg_l2_ms:.0f}ms"]
    if avg_l3_s:
        layer_labels.append("L3 Qwen\n(s)")
        layer_values.append(avg_l3_s * 1000)
        layer_colors.append(C["purple"])
        layer_annot.append(f"{avg_l3_s:.1f}s")

    bars = ax2.bar(layer_labels, layer_values, color=layer_colors, alpha=0.85, edgecolor=C["bg"])
    for bar, label in zip(bars, layer_annot):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.15,
                 label, ha="center", va="bottom", color=C["white"], fontsize=11, fontweight="bold")
    ax2.set_ylabel("Latency (ms, log scale)")
    ax2.set_title("Average Latency Per Layer", color=C["white"])
    ax2.set_yscale("log")
    ax2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda x, _: f"{x*1000:.0f}µs" if x < 0.1 else (f"{x:.0f}ms" if x < 1000 else f"{x/1000:.0f}s")))

    plt.tight_layout()
    save(fig, "04_pipeline_timing.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 5 — Security Pattern Coverage Heatmap
# ══════════════════════════════════════════════════════════════════════════════

def graph_security_coverage(results):
    print("  [5/6] Security pattern coverage...")

    # Test each of the 7 L1 patterns specifically
    patterns = {
        "AWS Key ID":        "AKIAIOSFODNN7EXAMPLE",
        "AWS Secret":        "aws_secret_key = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCY'",
        "Stripe Live":       "sk_live_" + "abcdefghijklmnopqrstuvwx",
        "GitHub PAT":        "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "GitHub Fine-grained": "github_pat_" + "A" * 82,
        "Bearer Token":      "Authorization: Bearer " + "A" * 45,
        "Private Key":       "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
    }

    # Obfuscation variants to test robustness
    variants = {
        "Plain":       lambda p: p,
        "In comment":  lambda p: f"# {p}",
        "In string":   lambda p: f'secret = "{p}"',
        "In diff +":   lambda p: f"+ {p}",
        "Multiline":   lambda p: f"config = {{\n  'key': '{p}'\n}}",
    }

    matrix = np.zeros((len(patterns), len(variants)))
    for i, (pname, pval) in enumerate(patterns.items()):
        for j, (vname, vfn) in enumerate(variants.items()):
            diff = vfn(pval)
            blocked, _ = run_layer1(diff)
            matrix[i][j] = 1.0 if blocked else 0.0

    fig, ax = plt.subplots(figsize=(10, 6))
    style_fig(fig, ax)
    fig.suptitle("Layer 1 — Secret Pattern Detection Coverage", color=C["white"], fontsize=13, fontweight="bold")

    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "lf", [C["panel"], C["red"], C["green"]])
    im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=1, aspect="auto")

    for i in range(len(patterns)):
        for j in range(len(variants)):
            val = matrix[i][j]
            ax.text(j, i, "✓" if val else "✗",
                    ha="center", va="center",
                    color=C["bg"] if val else C["gray"],
                    fontsize=14, fontweight="bold")

    ax.set_xticks(range(len(variants)))
    ax.set_yticks(range(len(patterns)))
    ax.set_xticklabels(list(variants.keys()), fontsize=9)
    ax.set_yticklabels(list(patterns.keys()), fontsize=9)
    ax.set_xlabel("Obfuscation variant")
    ax.set_ylabel("Secret pattern")

    total = matrix.sum()
    possible = matrix.size
    ax.set_title(f"Detection Rate: {total:.0f}/{possible} ({total/possible:.0%})", color=C["white"])

    plt.tight_layout()
    save(fig, "05_security_coverage.png")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH 6 — False Positive Rate by Layer and Language
# ══════════════════════════════════════════════════════════════════════════════

def graph_false_positives(results):
    print("  [6/6] False positive rate analysis...")

    clean = [r for r in results if r["label"] == "clean"]
    langs = sorted(set(r["lang"] for r in clean))

    # L1 FP: clean sample got blocked
    # L2 FP: clean sample scored >= 0.5
    # L3 FP: clean sample got high/medium severity

    def fp_rate(subset, key_fn):
        total = len(subset)
        return sum(1 for r in subset if key_fn(r)) / total if total else 0

    l1_fp_overall = fp_rate(clean, lambda r: r["l1_blocked"])
    l2_fp_overall = fp_rate(clean, lambda r: r["l2_score"] is not None and r["l2_score"] >= 0.5)
    l3_fp_overall = fp_rate(clean, lambda r: r["l3_severity"] in ("high", "medium"))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    style_fig(fig, [ax1, ax2])
    fig.suptitle("False Positive Rate Analysis", color=C["white"], fontsize=13, fontweight="bold", y=1.01)

    # Overall FP rate per layer
    layer_names = ["L1 AST\n(regex)", "L2 CoreML\n(ANE)", "L3 Qwen\n(MLX)"]
    fp_rates    = [l1_fp_overall, l2_fp_overall, l3_fp_overall]
    bar_colors  = [C["cyan"], C["blue"], C["purple"]]
    bars = ax1.bar(layer_names, fp_rates, color=bar_colors, alpha=0.85, edgecolor=C["bg"])
    for bar, rate in zip(bars, fp_rates):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f"{rate:.0%}", ha="center", va="bottom",
                 color=C["white"], fontsize=11, fontweight="bold")
    ax1.set_ylim(0, 1.0)
    ax1.set_ylabel("False Positive Rate")
    ax1.set_title(f"Overall FP Rate per Layer\n(on {len(clean)} clean samples)", color=C["white"])
    ax1.axhline(0.05, color=C["yellow"], linewidth=1, linestyle="--", alpha=0.6, label="5% threshold")
    ax1.legend(fontsize=8, facecolor=C["panel"], labelcolor=C["white"])

    # FP rate by language for L1 + L2
    x = np.arange(len(langs))
    width = 0.35
    l1_by_lang = [fp_rate([r for r in clean if r["lang"] == l], lambda r: r["l1_blocked"]) for l in langs]
    l2_by_lang = [fp_rate([r for r in clean if r["lang"] == l],
                           lambda r: r["l2_score"] is not None and r["l2_score"] >= 0.5) for l in langs]
    ax2.bar(x - width/2, l1_by_lang, width, color=C["cyan"],   alpha=0.85, label="L1 AST",    edgecolor=C["bg"])
    ax2.bar(x + width/2, l2_by_lang, width, color=C["blue"],   alpha=0.85, label="L2 CoreML", edgecolor=C["bg"])
    ax2.set_xticks(x)
    ax2.set_xticklabels([l.upper() for l in langs])
    ax2.set_ylim(0, 1.0)
    ax2.set_ylabel("False Positive Rate")
    ax2.set_title("FP Rate by Language (L1 vs L2)", color=C["white"])
    ax2.legend(fontsize=8, facecolor=C["panel"], labelcolor=C["white"])
    ax2.axhline(0.05, color=C["yellow"], linewidth=1, linestyle="--", alpha=0.6)

    plt.tight_layout()
    save(fig, "06_false_positive_rate.png")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY REPORT
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(results):
    print(f"\n{'='*60}")
    print("  BENCHMARK SUMMARY")
    print(f"{'='*60}")

    clean    = [r for r in results if r["label"] == "clean"]
    security = [r for r in results if r["label"] == "security"]
    bug      = [r for r in results if r["label"] == "bug_risk"]
    quality  = [r for r in results if r["label"] == "quality"]

    l1_times = [r["l1_ms"] for r in results]  # stored in µs
    print(f"\n  Layer 1 — AST Regex")
    print(f"    Avg latency : {statistics.mean(l1_times):.2f}µs")
    print(f"    p99 latency : {sorted(l1_times)[int(len(l1_times)*0.99)]:.2f}µs")
    print(f"    Detection   : {sum(1 for r in security if r['l1_blocked'])}/{len(security)} security samples blocked")
    print(f"    False pos.  : {sum(1 for r in clean if r['l1_blocked'])}/{len(clean)} clean samples incorrectly blocked")

    l2_scored = [r for r in results if r["l2_score"] is not None]
    if l2_scored:
        l2_times = [r["l2_ms"] for r in l2_scored]
        l2_detected = sum(1 for r in security if r.get("l2_score") is not None and r["l2_score"] >= 0.5)
        l2_fp = sum(1 for r in clean if r.get("l2_score") is not None and r["l2_score"] >= 0.5)
        print(f"\n  Layer 2 — CoreML/ANE")
        print(f"    Avg latency : {statistics.mean(l2_times):.0f}ms")
        print(f"    Detection   : {l2_detected}/{len(security)} security samples flagged (≥0.5)")
        print(f"    False pos.  : {l2_fp}/{len(clean)} clean samples incorrectly flagged")

    l3_scored = [r for r in results if r["l3_severity"] is not None]
    if l3_scored:
        l3_times = [r["l3_ms"]/1000 for r in l3_scored if r["l3_ms"] > 0]
        print(f"\n  Layer 3 — Qwen Advisory")
        if l3_times:
            print(f"    Avg inference : {statistics.mean(l3_times):.1f}s")
        actionable = [r for r in l3_scored if r["l3_severity"] in ("high", "medium")]
        print(f"    Actionable findings (high/medium): {len(actionable)}/{len(l3_scored)}")
        print(f"    Clean FP rate : {sum(1 for r in clean if r.get('l3_severity') in ('high','medium'))}/{len(clean)}")

    print(f"\n  Graphs saved to: {OUT_DIR}/")
    print(f"{'='*60}\n")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-qwen", action="store_true",
                        help="Skip Layer 3 Qwen inference (fast run, L1+L2 only)")
    args = parser.parse_args()

    if not BINARY.exists():
        print(f"ERROR: binary not found at {BINARY}")
        print("Run: cargo build --release")
        sys.exit(1)

    results = run_benchmark(skip_qwen=args.skip_qwen)

    graph_l1_latency(results)
    graph_l2_accuracy(results)
    graph_l3_quality(results)
    graph_pipeline_timing(results)
    graph_security_coverage(results)
    graph_false_positives(results)
    print_summary(results)
