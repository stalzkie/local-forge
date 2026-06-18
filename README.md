<div align="center">

<img src="ui/assets/localforge logo.svg" alt="LocalForge" width="100" height="100" />

# LocalForge

### a rust-native security gateway that reviews your code before git does

[![Platform](https://img.shields.io/badge/platform-Apple%20Silicon-black?style=flat-square&logo=apple)](https://github.com/stalzkie/local-forge/releases)
[![macOS](https://img.shields.io/badge/macOS-14%2B-blue?style=flat-square&logo=apple)](https://github.com/stalzkie/local-forge/releases)
[![Rust](https://img.shields.io/badge/rust-1.78%2B-orange?style=flat-square&logo=rust)](https://www.rust-lang.org)
[![Swift](https://img.shields.io/badge/swift-6.0-red?style=flat-square&logo=swift)](https://swift.org)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-16%20passing-brightgreen?style=flat-square)](https://github.com/stalzkie/local-forge)
[![MCP](https://img.shields.io/badge/MCP-compliant-purple?style=flat-square)](https://github.com/stalzkie/local-forge)

</div>

---

LocalForge is an on-device AI code review engine that intercepts every `git commit` before it lands. It runs a 3-layer hybrid pipeline — Rust regex, CoreML on the Apple Neural Engine, and a local Qwen LLM — entirely on your machine. No cloud. No API keys. No code ever leaves your Mac.

It catches hardcoded secrets, SQL injection, dead functions, unhandled errors, and logic bugs in the staged diff, then surfaces findings in a native macOS terminal UI — all in under 10 seconds per commit.

> **Install once per repo. Protect every commit.**

---

## What You Get

| Category | Details |
|---|---|
| **Secret Detection** | AWS keys, Stripe live secrets, GitHub PATs, private key blocks, high-entropy bearer tokens — blocked before commit |
| **AI Code Review** | Qwen2.5-Coder running locally via MLX finds SQL injection, dead functions, unhandled errors, logic flaws |
| **CoreML / ANE** | TF-IDF + logistic regression classifier runs on the Apple Neural Engine at ~200ms for statistical risk scoring |
| **Native macOS App** | Dark terminal-style SwiftUI app shows live scan results, layer status, and advisory reports |
| **MCP Server** | JSON-RPC 2.0 server for IDE integrations — connect Cursor, VS Code, or any MCP-compatible tool |
| **Zero Cloud** | All three layers — Rust, CoreML, Qwen — run fully offline on Apple Silicon |

---

## How It Works

LocalForge intercepts commits via a **git pre-commit hook**. When you run `git commit`, the hook runs before git finalizes anything:

```
git commit
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  hooks/pre-commit                                        │
│                                                          │
│  1. git diff --cached  →  staged diff                    │
│  2. Strip .localforgeignore paths                        │
│  3. Pipe diff into localforge --scan                     │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│  Layer 1 — Rust AST Regex          <1ms   HARD BLOCK     │
│  7 patterns: AWS, Stripe, GitHub PAT, private key...     │
├──────────────────────────────────────────────────────────┤
│  Layer 2 — CoreML / ANE          ~200ms   HARD BLOCK     │
│  TF-IDF char n-gram + logistic regression on Neural Engine│
├──────────────────────────────────────────────────────────┤
│  Layer 3 — Qwen2.5-Coder / MLX    ~5-8s   ADVISORY ONLY │
│  Full semantic review: security · quality · bug risks    │
└──────────────────────────────────────────────────────────┘
               │
               ▼
    Results → ~/.localforge/hook.log
               │
               ▼
    LocalForge.app reads log and displays live in UI
```

Layers 1 and 2 **block** the commit if they detect an issue. Layer 3 always runs in the background and writes an advisory report — it never blocks, it informs.

---

## Installation

### Requirements

- macOS 14+ on Apple Silicon (M1/M2/M3/M4)
- Rust 1.78+ — [install via rustup](https://rustup.rs)
- Python 3.11+ (ships with macOS 14)
- Xcode 16+ (for building the app)

### 1. Clone the repo

```bash
git clone https://github.com/stalzkie/local-forge.git
cd local-forge
```

### 2. Build the Rust binary

```bash
source "$HOME/.cargo/env"
cargo build --release
```

### 3. Build the CoreML model (Layer 2)

```bash
pip3 install coremltools scikit-learn numpy
python3 coreml/build_model.py
```

### 4. Set up Qwen for Layer 3 (optional but recommended)

```bash
pip3 install mlx-lm
python3 -c "from mlx_lm import load; load('Qwen/Qwen2.5-Coder-1.5B-Instruct-4bit')"
# Move the downloaded model:
mv ~/.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-1.5B-Instruct-4bit/snapshots/*/  coreml/qwen2.5-coder-1.5b-4bit/
```

### 5. Install the git hook into your project

```bash
# From inside the repo you want to protect:
/path/to/local-forge/scripts/install_hook.sh
```

Or copy manually:

```bash
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### 6. Download the macOS app (DMG)

Grab the latest release from the [Releases page](https://github.com/stalzkie/local-forge/releases) and drag **LocalForge.app** to your Applications folder.

Or build it yourself:

```bash
./scripts/build_release.sh
./scripts/package_dmg.sh
open build/LocalForge-v2.0-arm64.dmg
```

---

## The macOS App

The native SwiftUI app connects to the `localforge --monitor` process and displays every scan event in real time. Open it alongside your terminal while you work.

```
┌─────────────────────────────────────────────────────────────────┐
│  🛡 LocalForge Security Shield        L1  L2  L3   ● Active  Stop │
│     v2.0 · 3-Layer Hybrid Pipeline   AST ANE Qwen             │
├─────────────────────────────────────────────────────────────────┤
│  INFO   LocalForge v2.0 starting…                               │
│  OK     Engine started (PID 59620).                             │
│  INFO   3-Layer pipeline: L1 AST  •  L2 CoreML/ANE  •  L3 Qwen │
│  L1     Layer 1 (AST regex): ready                              │
│  L2     Layer 2 (CoreML/ANE): ready                             │
│  L3     Layer 3 (Qwen/MLX): advisory engine ready               │
│  INFO   All layers initialised. Waiting for commits...          │
│                                                                 │
│  INFO   Scanning commit — files: api/routes.py                  │
│  ERR    BLOCKED — secret detected: AWS Access Key ID            │
│  ERR    Commit BLOCKED — a secret was detected in the diff      │
│                                                                 │
│  INFO   Scanning commit — files: models/user.py                 │
│  OK     Layer 2 score: 0.322 — clean.                           │
│  L3     Qwen [MEDIUM] SQL injection risk in fetch_records()     │
│  L3       [SECURITY] sql_injection — query built via string...  │
│  L3       Fix: Use parameterised queries or an ORM              │
└─────────────────────────────────────────────────────────────────┘
│  Scanned: 12  Blocked: 1          📁 Advisory Logs              │
└─────────────────────────────────────────────────────────────────┘
```

**Color coding:**
- `L1` cyan — AST regex findings
- `L2` blue — CoreML/ANE risk score
- `L3` purple — Qwen advisory output
- `ERR` red — blocked commit or security finding
- `WARN` yellow — bug risk
- `ADV` magenta — code quality finding
- `OK` green — clean scan

---

## The 3-Layer Pipeline

### Layer 1 — Rust AST Regex (`<1ms`)

Seven deterministic patterns compiled into the binary. Fires synchronously — no subprocess, no model load, no network.

| Pattern | Example |
|---|---|
| AWS Access Key ID | `AKIA...` (20 chars) |
| AWS Secret Key | `aws_secret = "..."` (40 chars) |
| Stripe Live Key | `sk_live_...` |
| GitHub PAT (classic) | `ghp_...` (40 chars) |
| GitHub Fine-Grained PAT | `github_pat_...` (82 chars) |
| High-Entropy Bearer Token | `Authorization: Bearer <40+ chars>` |
| Private Key Block | `-----BEGIN RSA PRIVATE KEY-----` |

### Layer 2 — CoreML / Apple Neural Engine (`~200ms`)

A TF-IDF char n-gram vectorizer (3–5gram, 512 features) + logistic regression classifier trained on 81 samples. Runs on the Neural Engine via `CPU_AND_NE` compute units for hardware-accelerated inference.

```
Train accuracy:  93.83%
CV F1 score:     0.496 ± 0.229
Verification:    10/10 cases passed
```

### Layer 3 — Qwen2.5-Coder via MLX (`~3.8s`)

A 1.5B parameter code model running locally via Apple's MLX framework. Reviews the full diff for three categories:

- **Security** — injection, insecure patterns, path traversal, unsafe deserialization
- **Bug Risk** — off-by-one errors, unhandled exceptions, null dereferences, race conditions
- **Code Quality** — dead/orphan functions, unused variables, overly complex logic

Findings are appended to `~/.localforge/reports/commit_<timestamp>.txt` — one file per commit, all findings in plain text. Click the folder icon in the app to open reports in Finder. **Layer 3 never blocks a commit** — it advises.

---

## CLI Reference

```bash
# Scan stdin diff (used by the hook)
localforge --scan

# Launch the ratatui TUI dashboard
localforge

# GUI monitor mode — plain stdout, no TTY required (used by the app)
localforge --monitor

# Start the MCP JSON-RPC server
localforge --mcp-port 7777
```

---

## MCP Server

LocalForge exposes a JSON-RPC 2.0 server for IDE integrations. Start it and connect any MCP-compatible client (Cursor, VS Code with MCP extension, etc.).

```bash
localforge --mcp-port 7777
```

**Example request:**

```json
{
  "jsonrpc": "2.0",
  "method": "scan",
  "params": {
    "file_path": "src/api.py",
    "staged_diff_content": "aws_token = 'AKIAIOSFODNN7EXAMPLE'"
  },
  "id": 1
}
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "blocked": true,
    "blocked_by": "layer1",
    "layer2_score": 0.847,
    "advisory": null
  },
  "id": 1
}
```

**Methods:** `scan`, `ping`

---

## Suppressing False Positives

Add file paths to `.localforgeignore` in your repo root. Any diff hunks from matching files are stripped before scanning.

```
# .localforgeignore
# Syntax: one pattern per line, substring-matched against the diff file path

# Test fixtures with intentional fake keys
tests/fixtures/
tests/verify.py

# Source files that contain regex patterns
src/ast_validator.rs
```

---

## Advisory Reports

Every commit with Layer 3 enabled writes a human-readable `.txt` report to `~/.localforge/reports/`. One file per commit — all findings appended. Click the folder icon in the app to open it in Finder.

```
======================================================================
  LocalForge Code Assessment
  2026-06-18 12:23:03 UTC  |  diff: 4d06522c65  |  model: Qwen2.5-Coder-1.5B
======================================================================
  Severity : MEDIUM
  Summary  : SQL injection risk in fetch_records() — user input concatenated into query string

  [1] [SECURITY] sql_injection
      Code    : query = "SELECT * FROM users WHERE id = " + user_id
      Issue   : user_id is concatenated directly into the SQL string without sanitization
      Fix     : Use parameterised queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
======================================================================
```

Toggle Layer 3 on/off at any time using the **Code Review** switch in the app header. When off, Qwen is skipped and no report is written.

---

## Benchmark Results

80-sample benchmark across clean, security, bug_risk, and quality categories in Python, Rust, and JavaScript. Run with `python3 tests/benchmark.py`.

### Layer 1 — AST Regex

| Metric | Result |
|---|---|
| Average latency | **40.81 µs** |
| p99 latency | 156.08 µs |
| Secret detection rate | 4/20 security samples blocked (20%) |
| False positive rate | **0%** — zero clean samples blocked |

Layer 1 operates entirely in-process with no subprocess overhead. The 20% detection rate is by design: it only catches the seven explicit secret patterns (AWS keys, GitHub PATs, etc.) — not general security issues.

### Layer 2 — CoreML / ANE

| Metric | Result |
|---|---|
| Average latency | **2,083 ms** (model load + inference) |
| Security detection rate | 3/20 flagged (≥ 0.5 threshold) |
| False positive rate | 2/20 clean samples flagged (10%) |

The CoreML classifier is a statistical model trained on 81 samples. Its risk score complements Layer 1 — it catches patterns that aren't literal secrets but look statistically similar to known bad code.

### Layer 3 — Qwen Advisory

| Metric | Result |
|---|---|
| Average inference | **3.8 s** |
| Actionable findings (high/medium) | 78/80 samples |
| Clean code advisory rate | 18/20 — L3 is advisory-only, never blocks |

Layer 3's high advisory rate on clean code is intentional — it surfaces quality and best-practice suggestions even when code is safe. It is a code reviewer, not a blocker.

### Benchmark Graphs

| Graph | What It Shows |
|---|---|
| `01_layer1_latency.png` | Histogram + box plot of L1 latency per category (µs) |
| `02_layer2_accuracy.png` | Confusion matrix + risk score distribution |
| `03_layer3_quality.png` | Severity pie + detection rate + inference time |
| `04_pipeline_timing.png` | Per-sample L2 bars + avg per layer (log scale) |
| `05_security_coverage.png` | 7×5 heatmap of pattern × obfuscation variant |
| `06_false_positive_rate.png` | FP rate per layer + per language |

All graphs are saved to `tests/benchmark_results/`.

---

## Running Tests

```bash
# Rust unit tests (16 tests across all modules)
cargo test

# End-to-end validation suite
python3 tests/verify.py

# 80-sample performance benchmark (all 3 layers)
python3 tests/benchmark.py

# Skip Qwen for a faster L1+L2-only run
python3 tests/benchmark.py --skip-qwen

# Manual smoke test — should exit 1 and print BLOCKED
echo 'token = "AKIAIOSFODNN7EXAMPLE"' | ./target/release/localforge --scan
```

**Test coverage:**

| Module | Tests |
|---|---|
| `ast_validator` | AWS key, Stripe key, GitHub PAT, private key, clean Python, clean Rust, short token |
| `mcp_server` | scan blocked, scan clean, ping, malformed JSON, unknown method |
| `advisory_engine` | severity parsing, actionable check, absent shim |
| `ane_bridge` | graceful degradation when model absent |

---

## Project Structure

```
local-forge/
├── src/
│   ├── main.rs               # CLI entry point — --scan, --monitor, --mcp-port, TUI
│   ├── ast_validator.rs      # Layer 1: 7 regex secret patterns
│   ├── ane_bridge.rs         # Layer 2: CoreML subprocess bridge
│   ├── advisory_engine.rs    # Layer 3: Qwen async runner
│   ├── mcp_server.rs         # JSON-RPC 2.0 TCP server
│   └── tui/
│       ├── dashboard.rs      # ratatui layout and widgets
│       └── events.rs         # crossterm keyboard events
├── coreml/
│   ├── build_model.py        # Train TF-IDF + logistic regression → CoreML
│   ├── infer.py              # Layer 2 inference shim
│   ├── advisory.py           # Layer 3 Qwen inference + report writer
│   ├── LocalForgeModel.mlpackage/
│   └── qwen2.5-coder-1.5b-4bit/
├── ui/
│   ├── LocalForge.xcodeproj/
│   └── LocalForgeApp/
│       ├── App.swift
│       ├── ContentView.swift
│       └── LogViewModel.swift
├── hooks/
│   └── pre-commit            # Git hook — orchestrates all 3 layers
├── scripts/
│   ├── install_hook.sh       # Install hook into any repo
│   ├── build_release.sh      # Build Rust + archive .app
│   └── package_dmg.sh        # Wrap .app into distributable DMG
├── tests/
│   ├── verify.py             # End-to-end validation suite
│   ├── benchmark.py          # 80-sample 3-layer performance benchmark
│   └── benchmark_results/    # Benchmark graphs (PNG)
└── .localforgeignore         # Paths excluded from scanning
```

---

## Stack

| Layer | Technology |
|---|---|
| Core binary | Rust 1.78, tokio, clap, regex, serde_json, ratatui, crossterm |
| Layer 2 model | Python, scikit-learn, coremltools, CoreML NeuralNetwork spec |
| Layer 2 runtime | Apple CoreML, `CPU_AND_NE` compute units (Apple Neural Engine) |
| Layer 3 model | Qwen2.5-Coder-1.5B-Instruct-4bit |
| Layer 3 runtime | Apple MLX, mlx-lm |
| macOS app | Swift 6, SwiftUI, Combine, macOS 14+ |
| Packaging | xcodebuild, create-dmg |
| Protocol | JSON-RPC 2.0 over TCP (MCP) |

---

## Roadmap

- [x] Layer 1 — Rust regex secret scanner
- [x] Layer 2 — CoreML/ANE statistical classifier
- [x] Layer 3 — Qwen local LLM code reviewer
- [x] Git pre-commit hook with `.localforgeignore`
- [x] MCP JSON-RPC 2.0 server
- [x] Native macOS SwiftUI app
- [x] Distributable DMG
- [x] Hook log forwarding to GUI
- [ ] `localforge --install` one-command hook setup
- [ ] Multi-repo dashboard view in the app
- [ ] Configurable block thresholds per-project
- [ ] VS Code extension
- [ ] Support for additional secret patterns (Twilio, SendGrid, OpenAI)

---

## Privacy

LocalForge processes your code exclusively on your device. No diff, file, or finding is ever sent to a remote server. The Qwen model runs via Apple MLX locally. The CoreML model was trained offline and runs on-device via the Neural Engine. The MCP server binds to `127.0.0.1` only.

`~/.localforge/` is the only directory written to: advisory reports and the hook event log live there. Nothing else is touched.

---

## Contributing

Pull requests are welcome. Keep changes focused — one feature or fix per PR.

**Before submitting:**
- [ ] `cargo test` passes (all 16 tests)
- [ ] New patterns or rules include a corresponding unit test
- [ ] No real secrets or credentials in test fixtures — use runtime-constructed strings
- [ ] Update `.localforgeignore` if your files contain intentional fake keys

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

Built by [Stalingrad Dollosa](https://github.com/stalzkie) · Apple Silicon M4 · June 2026

*LocalForge — your last line of defence before git history.*

</div>
