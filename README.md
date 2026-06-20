<div align="center">

<img src="ui/assets/localforge logo.png" alt="LocalForge" width="100" height="100" />

# LocalForge

### a rust-native security gateway that reviews your code before git does

[![Platform](https://img.shields.io/badge/platform-Apple%20Silicon-black?style=flat-square&logo=apple)](https://github.com/stalzkie/local-forge/releases)
[![macOS](https://img.shields.io/badge/macOS-14%2B-blue?style=flat-square&logo=apple)](https://github.com/stalzkie/local-forge/releases)
[![Rust](https://img.shields.io/badge/rust-1.78%2B-orange?style=flat-square&logo=rust)](https://www.rust-lang.org)
[![Swift](https://img.shields.io/badge/swift-6.0-red?style=flat-square&logo=swift)](https://swift.org)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-43%20passing-brightgreen?style=flat-square)](https://github.com/stalzkie/local-forge)
[![MCP](https://img.shields.io/badge/MCP-compliant-purple?style=flat-square)](https://github.com/stalzkie/local-forge)

</div>

---

LocalForge is an on-device AI code review engine that intercepts every `git commit` before it lands. It runs a 3-layer hybrid pipeline — Rust regex, CoreML on the Apple Neural Engine, and a local Qwen LLM — entirely on your machine. No cloud. No API keys. No code ever leaves your Mac.

It catches hardcoded secrets, SQL injection, dead functions, unhandled errors, and logic bugs in the staged diff, then surfaces findings in a native macOS terminal UI — all before the commit finalises.

> **Install once per repo. Protect every commit.**

---

## What You Get

| Category | Details |
|---|---|
| **Secret Detection** | 26 patterns across 13 providers — AWS, GCP, Azure, Stripe, GitHub, Slack, Twilio, SendGrid, npm, HuggingFace, Anthropic, OpenAI, Shopify, private keys — blocked before commit |
| **AI Code Review** | Qwen2.5-Coder running locally via MLX finds SQL injection, XSS, command injection, dead functions, unhandled errors, and logic flaws across 11 languages |
| **CoreML / ANE** | TF-IDF + logistic regression trained on 297 samples across 11 languages, running on the Apple Neural Engine — CV F1: 0.754 |
| **Native macOS App** | Dark terminal-style SwiftUI app with Monitor tab (live scan events) and Repos tab (multi-repo management) |
| **One-Command Install** | `localforge --install` sets up `~/.localforge/`, installs the hook, auto-detects the Qwen model, and adds itself to PATH |
| **Team Install** | `localforge --install-org` generates a ready-to-share shell script — paste it into your dev setup doc or Makefile, every teammate runs it once |
| **Compliance Export** | `localforge --export-report json` exports all scan results to JSON or CSV for security audits and due diligence |
| **MCP Server** | JSON-RPC 2.0 server for IDE integrations — connect Cursor, VS Code, or any MCP-compatible tool |
| **Zero Cloud** | All three layers — Rust, CoreML, Qwen — run fully offline on Apple Silicon |

---

## How It Works

LocalForge intercepts commits via a **git pre-commit hook**. When you run `git commit`, the hook runs before git finalises anything:

```
git commit
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  hooks/pre-commit                                        │
│                                                          │
│  1. git diff --cached  →  staged diff (added lines only) │
│  2. Strip .localforgeignore paths                        │
│  3. Pipe diff into localforge --scan                     │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│  Layer 1 — Rust Regex              <1ms   HARD BLOCK     │
│  26 patterns across 13 providers — compiled once at boot │
├──────────────────────────────────────────────────────────┤
│  Layer 2 — CoreML / ANE          ~200ms   HARD BLOCK     │
│  TF-IDF char n-gram + logistic regression (297 samples)  │
│  11 languages · CV F1: 0.754 ± 0.021                    │
├──────────────────────────────────────────────────────────┤
│  Layer 3 — Qwen2.5-Coder / MLX    ~5-8s   ADVISORY ONLY │
│  Full semantic review: security · quality · bug risks    │
│  Language-aware · single consolidated report per commit  │
└──────────────────────────────────────────────────────────┘
               │
               ▼
    Results → ~/.localforge/hook.log
    Report  → ~/.localforge/reports/commit_<ts>.txt
               │
               ▼
    LocalForge.app reads log and displays live in UI
```

Layers 1 and 2 **block** the commit on a positive. Layer 3 always runs in the background and writes a single advisory report — it never blocks, it informs.

---

## Installation

### Requirements

- macOS 14+ on Apple Silicon (M1/M2/M3/M4)
- Rust 1.78+ — [install via rustup](https://rustup.rs)
- Python 3.11+ (ships with macOS 14)
- Xcode 16+ (for building the app — optional)

### 1. Clone and build

```bash
git clone https://github.com/stalzkie/local-forge.git
cd local-forge
source "$HOME/.cargo/env"   # load Rust if freshly installed
cargo build --release
```

### 2. Build the CoreML model (Layer 2)

```bash
pip3 install coremltools scikit-learn numpy
python3 coreml/build_model.py
```

Training prints live progress to your terminal: per-fold F1 bars, a classification report, and a confusion matrix. Takes under 5 seconds on M-series hardware.

### 3. Enable Qwen code review (Layer 3 — optional but recommended)

```bash
pip3 install mlx-lm
python3 -c "from mlx_lm import load; load('Qwen/Qwen2.5-Coder-1.5B-Instruct-4bit')"
```

The installer auto-detects the downloaded model from your HuggingFace cache — no manual `mv` needed.

### 4. Install into your project

```bash
# Protect any git repo — defaults to current directory
./scripts/install_hook.sh /path/to/your/project
```

This one command:
- Copies the binary to `~/.localforge/bin/` and writes `export PATH` to `~/.zshrc` automatically
- Installs the CoreML model and Python shims to `~/.localforge/`
- Moves the Qwen model from your HuggingFace cache if present
- Installs the pre-commit hook (v4) into your repo
- Registers the repo for multi-repo management in the app

> **Note:** Open a new terminal (or run `source ~/.zshrc`) after the first install for `localforge` to be available in PATH.

To protect additional repos after the first install:

```bash
localforge --install /path/to/another/project
```

### 5. Download the macOS app (optional)

Grab the latest release from the [Releases page](https://github.com/stalzkie/local-forge/releases) and drag **LocalForge.app** to your Applications folder — it connects to your installed binary automatically.

Or build it yourself:

```bash
./scripts/build_release.sh   # bundles binary + CoreML model + shims into .app
./scripts/package_dmg.sh     # wraps .app into a distributable DMG
open build/LocalForge-v2.0-arm64.dmg
```

### Homebrew (coming soon)

```bash
brew tap stalzkie/local-forge
brew install localforge
localforge --install /path/to/your/repo
```

The formula symlinks the binary into `~/.localforge/bin/` automatically — no PATH changes needed.

---

## The macOS App

The native SwiftUI app has two tabs:

**Monitor tab** — live scan events streamed from `~/.localforge/hook.log`. Every commit triggers a real-time feed of layer results, risk scores, and advisory summaries.

**Repos tab** — manage all protected repositories from one place. Shows hook status per repo (Active / Outdated / Missing / Replaced), lets you upgrade all hooks in one click, and reveals repos in Finder.

```
┌─────────────────────────────────────────────────────────────────┐
│  🛡 LocalForge                    [Monitor]  [Repos]   ● Active  │
├─────────────────────────────────────────────────────────────────┤
│  INFO   Scanning commit — files: api/routes.py                  │
│  L1     Layer 1 (AST regex): ready                              │
│  L2     Layer 2 score: 0.789 — BLOCKED                          │
│  ERR    Commit BLOCKED — a secret was detected in the diff      │
│                                                                 │
│  INFO   Scanning commit — files: models/user.py                 │
│  L2     Layer 2 score: 0.322 — clean.                           │
│  L3     Qwen [MEDIUM] SQL injection risk in fetch_records()     │
│  L3       Fix: Use parameterised queries or an ORM              │
└─────────────────────────────────────────────────────────────────┘
```

---

## The 3-Layer Pipeline

### Layer 1 — Rust Regex (`<1ms`)

26 deterministic patterns across 13 secret providers, compiled once at startup via `once_cell::Lazy`. Fires synchronously — no subprocess, no model load. Only scans **added lines** (`+`) to avoid blocking commits that are removing secrets.

| Provider | Patterns |
|---|---|
| AWS | Access Key ID, Secret Access Key |
| GCP | API Key (`AIza...`), Service Account JSON |
| Azure | Storage Key, SAS Token |
| Stripe | Live Secret Key, Restricted Key |
| GitHub | PAT (classic), Fine-Grained PAT, Actions Secret |
| Slack | Bot/User/App tokens, Webhook URLs |
| Twilio | Account SID, API Key |
| SendGrid | API Key |
| npm / PyPI | Access tokens |
| HuggingFace / Anthropic / OpenAI | API tokens |
| Shopify | Access Token, Shared Secret |
| Private Keys | RSA, EC, DSA, OPENSSH, PuTTY |
| `.env` assignments | `SECRET_KEY=bare_value` patterns |

### Layer 2 — CoreML / Apple Neural Engine (`~200ms`)

A TF-IDF char n-gram vectorizer (3–5gram, 1024 features) + logistic regression classifier trained on **297 samples across 11 languages**, running on the Neural Engine via `CPU_AND_NE` compute units.

```
Model version   : 2.1.0
Training samples: 297  (170 risky / 127 clean)
Languages       : Python, JS/TS, Java, Go, Rust, C#, PHP, Ruby, Swift, Kotlin, SQL
Train accuracy  : 89.56%
CV F1 (5-fold)  : 0.754 ± 0.021
Verification    : 32/33 held-out cases (97%)
```

Rebuilt from v2.0's 81-sample Python-only model. The CV F1 improvement from **0.496 ± 0.229 → 0.754 ± 0.021** reflects both better generalization and far more stable fold-to-fold performance.

Retrain at any time:

```bash
python3 coreml/build_model.py
localforge --install   # redeploys updated model to ~/.localforge/
```

### Layer 3 — Qwen2.5-Coder via MLX (`~5-8s`)

A 1.5B parameter code model running locally via Apple's MLX framework. Detects language from diff file extensions and reviews only **added lines** — not deletions. All findings from a single `git commit` are written to **one consolidated report file** at `~/.localforge/reports/commit_<timestamp>.txt`.

Review categories:
- **Security** — injection, insecure crypto, path traversal, unsafe deserialization, disabled TLS
- **Bug Risk** — off-by-one errors, unhandled exceptions, null dereferences, race conditions
- **Code Quality** — dead/orphan functions, unused variables, overly complex logic

Large diffs are chunked at file boundaries and findings are merged and deduplicated. **Layer 3 never blocks a commit** — it advises.

---

## CLI Reference

```bash
# Scan a staged diff (used by the pre-commit hook)
localforge --scan

# Install hook + binary + model into a repo
localforge --install /path/to/repo

# Uninstall hook from a repo and deregister it
localforge --uninstall /path/to/repo

# List all registered repos with hook version status
localforge --list-repos

# Upgrade hooks in all registered repos to the current version
localforge --upgrade-all

# Generate a team install script (share with your devs or paste into Makefile)
localforge --install-org /path/to/repo

# Export scan history to JSON or CSV for audits
localforge --export-report json
localforge --export-report csv --last 30 --out audit-q2.csv

# Launch the ratatui TUI dashboard
localforge

# GUI monitor mode — plain stdout for the app
localforge --monitor

# Start the MCP JSON-RPC server
localforge --mcp-port 7777
```

### Team Install

For teams where one engineer mandates LocalForge for everyone:

```bash
# Generate the script (run once, in your repo)
localforge --install-org /path/to/your/repo

# Share with your team — each dev runs it once on their machine
bash localforge-install-org.sh

# Or add to your dev setup doc as a one-liner:
curl -fsSL https://github.com/stalzkie/local-forge/releases/latest/download/localforge-install-org.sh | bash
```

The generated script downloads the binary, sets up `~/.localforge/`, adds PATH to the shell profile, and installs the hook — no admin rights required.

### Compliance Export

Export the full scan history to hand to an auditor or drop into a compliance folder:

```bash
# All-time JSON export
localforge --export-report json --out localforge-audit.json

# Last 30 commits as CSV
localforge --export-report csv --last 30 --out security-audit-q2.csv
```

Each row includes: commit ID, timestamp, severity, summary, finding count, and path to the full report. Useful for SOC 2, ISO 27001, and Series A due diligence questionnaires.

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
    "staged_diff_content": "+aws_token = 'AKIAIOSFODNN7EXAMPLE'"
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

Add file paths to `.localforgeignore` in your repo root. Diff hunks from matching files are stripped before scanning reaches any layer.

```
# .localforgeignore
# Syntax: one pattern per line, substring-matched against the diff file path

# Test fixtures with intentional fake keys
tests/fixtures/
tests/verify.py

# Source files that contain regex patterns or training data
src/ast_validator.rs
coreml/build_model.py
```

---

## Advisory Reports

Every commit with Layer 3 enabled writes a single `.txt` report to `~/.localforge/reports/`. All findings from all diff chunks are consolidated into one file per commit.

```
======================================================================
  LocalForge Security & Code Assessment
  2026-06-19 14:31:02 UTC
  Diff hash : 4d06522c65
  Model     : Qwen2.5-Coder-1.5B (Layer 3 advisory)
======================================================================

  Severity : MEDIUM
  Summary  : SQL injection risk in fetch_records() — user input concatenated into query string

  Findings (1):

  [1] [SECURITY] sql_injection
      Code    : query = "SELECT * FROM users WHERE id = " + user_id
      Issue   : user_id is concatenated directly into the SQL string without sanitization
      Fix     : Use parameterised queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))

──────────────────────────────────────────────────────────────────────
```

Toggle Layer 3 on/off using the **Code Review** switch in the app. When off, Qwen is skipped entirely and no report is written.

---

## Benchmark Results

### v2.1 Model (current)

Run with `python3 tests/benchmark_v2.py` — reads from `coreml/model_metadata.json`, no re-inference required.

| Metric | v2.0 | v2.1 |
|---|---|---|
| Training samples | 81 | **297** |
| Languages covered | 2 | **11** |
| CV F1 score | 0.496 ± 0.229 | **0.754 ± 0.021** |
| Verification accuracy | 10/10 (88% rate) | **32/33 (97%)** |
| Layer 1 patterns | 7 | **26** |
| Layer 1 providers | 5 | **13** |

### v2.1 Benchmark Graphs

| Graph | What It Shows |
|---|---|
| `07_v21_before_after.png` | Side-by-side: training samples, CV F1 with error bars, verification accuracy |
| `08_v21_score_distribution.png` | Risk score histogram split by ground truth — clean vs risky separation |
| `09_v21_language_heatmap.png` | Per-language precision / recall / F1 heatmap (Python, JS, Java, Go, PHP) |
| `10_v21_cv_stability.png` | Fold-by-fold F1 bars — v2.0 wild variance vs v2.1 tight consistency |
| `11_v21_l1_coverage.png` | Pie charts: Layer 1 pattern coverage (7 → 26 across 13 providers) |
| `12_v21_confidence_margin.png` | Per-sample distance from 0.5 threshold — confidence of each prediction |

### v2.0 Baseline Graphs (historical)

| Graph | What It Shows |
|---|---|
| `01_layer1_latency.png` | Histogram + box plot of L1 latency per category (µs) |
| `02_layer2_accuracy.png` | Confusion matrix + risk score distribution |
| `03_layer3_quality.png` | Severity pie + detection rate + inference time |
| `04_pipeline_timing.png` | Per-sample L2 bars + avg per layer (log scale) |
| `05_security_coverage.png` | Pattern × obfuscation variant heatmap |
| `06_false_positive_rate.png` | FP rate per layer + per language |

All graphs are saved to `tests/benchmark_results/`.

---

## Running Tests

```bash
# Rust unit + integration tests (43 tests across all modules)
cargo test

# End-to-end validation suite
python3 tests/verify.py

# 80-sample v2.0 benchmark (all 3 layers)
python3 tests/benchmark.py --skip-qwen

# v2.1 benchmark charts from model metadata (no inference)
python3 tests/benchmark_v2.py

# Manual smoke test — should exit 1 and print BLOCKED
echo 'token = "AKIAIOSFODNN7EXAMPLE"' | ./target/release/localforge --scan
```

**Test coverage (43 tests):**

| Module | Tests | Coverage |
|---|---|---|
| `ast_validator` | 34 | 20 secret detection + 10 false positive guards + 4 diff-awareness tests |
| `mcp_server` | 5 | scan blocked, scan clean, ping, malformed JSON, unknown method |
| `advisory_engine` | 3 | severity parsing, actionable check, no-panic guarantee |
| `ane_bridge` | 1 | graceful degradation when model absent |

---

## Project Structure

```
local-forge/
├── src/
│   ├── main.rs               # CLI entry — --scan, --install, --install-org, --export-report, TUI, MCP
│   ├── ast_validator.rs      # Layer 1: 26 regex patterns, once_cell compiled
│   ├── ane_bridge.rs         # Layer 2: CoreML subprocess bridge
│   ├── advisory_engine.rs    # Layer 3: Qwen async runner + severity types
│   ├── mcp_server.rs         # JSON-RPC 2.0 TCP server
│   └── tui/
│       ├── dashboard.rs      # ratatui layout and widgets
│       └── events.rs         # crossterm keyboard events
├── coreml/
│   ├── build_model.py        # Train TF-IDF + logistic regression → CoreML (live progress)
│   ├── infer.py              # Layer 2 inference shim
│   ├── advisory.py           # Layer 3 Qwen inference + single-file report writer
│   ├── LocalForgeModel.mlpackage/
│   └── qwen2.5-coder-1.5b-4bit/  (gitignored — downloaded separately)
├── ui/
│   ├── LocalForge.xcodeproj/
│   └── LocalForgeApp/
│       ├── App.swift
│       ├── ContentView.swift  # Monitor + Repos tabs
│       ├── LogViewModel.swift
│       ├── ReposView.swift    # Repos tab UI
│       └── ReposViewModel.swift # Hook status per repo, upgrade-all
├── hooks/
│   └── pre-commit            # Hook v4 — orchestrates all 3 layers, single report file
├── scripts/
│   ├── install_hook.sh       # Full install: binary + model + hook + PATH
│   ├── build_release.sh      # Build Rust + archive .app + bundle Resources
│   ├── package_dmg.sh        # Wrap .app into distributable DMG
│   ├── notarize.sh           # Submit DMG to Apple notarytool + staple
│   └── package_homebrew.sh   # Generate Homebrew tarball + SHA256
├── Formula/
│   └── localforge.rb         # Homebrew formula (brew tap stalzkie/local-forge)
├── tests/
│   ├── verify.py             # End-to-end validation suite
│   ├── benchmark.py          # 80-sample v2.0 benchmark
│   ├── benchmark_v2.py       # v2.1 accuracy benchmark charts
│   └── benchmark_results/    # PNGs: 01-06 (v2.0 baseline), 07-12 (v2.1)
└── .localforgeignore         # Paths excluded from scanning
```

---

## Stack

| Layer | Technology |
|---|---|
| Core binary | Rust 1.78, tokio, clap, regex, once_cell, dirs, serde_json, ratatui, crossterm, anyhow |
| Layer 2 training | Python, scikit-learn, coremltools, numpy |
| Layer 2 runtime | Apple CoreML `CPU_AND_NE` (Apple Neural Engine) |
| Layer 3 model | Qwen2.5-Coder-1.5B-Instruct-4bit |
| Layer 3 runtime | Apple MLX, mlx-lm |
| macOS app | Swift 6, SwiftUI, Combine, AppKit, macOS 14+ |
| Packaging | xcodebuild, create-dmg, xcrun notarytool |
| Distribution | GitHub Releases, Homebrew tap |
| Protocol | JSON-RPC 2.0 over TCP (MCP) |

---

## Roadmap

- [x] Layer 1 — Rust regex secret scanner (26 patterns, 13 providers)
- [x] Layer 2 — CoreML/ANE statistical classifier (297 samples, 11 languages)
- [x] Layer 3 — Qwen local LLM code reviewer (language-aware, single consolidated report)
- [x] Git pre-commit hook v4 with `.localforgeignore`
- [x] MCP JSON-RPC 2.0 server
- [x] Native macOS SwiftUI app (Monitor + Repos tabs)
- [x] `localforge --install` one-command setup (auto PATH, auto Qwen detection)
- [x] Multi-repo dashboard in the app with hook version status
- [x] Hook version checking and `--upgrade-all`
- [x] Distributable DMG with bundled CoreML model
- [x] Homebrew formula (`brew tap stalzkie/local-forge`)
- [x] Notarization script for Gatekeeper-free distribution
- [x] `localforge --install-org` team install script generator
- [x] `localforge --export-report` compliance export (JSON / CSV)
- [ ] Configurable block thresholds per-project
- [ ] VS Code extension
- [ ] CI/CD mode (exit codes for GitHub Actions)

---

## Privacy

LocalForge processes your code exclusively on your device. No diff, file, or finding is ever sent to a remote server. The Qwen model runs via Apple MLX locally. The CoreML model was trained offline and runs on-device via the Neural Engine. The MCP server binds to `127.0.0.1` only.

`~/.localforge/` is the only directory written to: the binary, model artifacts, advisory reports, and the hook event log live there. Nothing else is touched.

---

## Contributing

Pull requests are welcome. Keep changes focused — one feature or fix per PR.

**Before submitting:**
- [ ] `cargo test` passes (all 43 tests)
- [ ] New Layer 1 patterns include a detection test and a false-positive guard test
- [ ] No real secrets in test fixtures — use runtime-constructed strings (`format!("AKIA{}", ...)`)
- [ ] Update `.localforgeignore` if your files contain intentional fake keys
- [ ] If retraining Layer 2, run `python3 coreml/build_model.py` and commit updated artifacts

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

Built by [Stalingrad Dollosa](https://github.com/stalzkie) · Apple Silicon M4 · June 2026

*LocalForge — your last line of defence before git history.*

</div>
