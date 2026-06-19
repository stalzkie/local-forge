# Reddit Post — LocalForge v2.1

---

**Hey r/MachineLearning / r/rust / r/devops — I'm a recent CS grad trying to break into ML Engineering, and this is my first open source project. Would love feedback.**

---

I got tired of the "oops, I committed an AWS key" dread that every dev eventually feels — especially vibe coders — so I spent a while building **LocalForge**, a fully local pre-commit security pipeline for Apple Silicon. MIT licensed, source on GitHub.

---

## The problem

Server-side secret scanning (GitHub Advanced Security, etc.) catches leaks *after* they're already in your history. Pre-commit tools like `gitleaks` and `detect-secrets` run locally but are pure pattern matchers — they miss anything that isn't a known format, and they say nothing about actual code quality. And piping your diff to a cloud LLM for review just trades one security risk for another.

So I built a hook that chains three completely different detection strategies, each playing to its strength.

---

## How it works

### Layer 1 — Rust regex (`<1ms`, hard block)

**26 compiled patterns across 13 secret providers**, running in-process with zero subprocess overhead. Only scans `+` lines in the diff so removing a secret never triggers a false block.

Providers covered: AWS, GCP (API key + service account JSON), Azure SAS tokens, Stripe (live + restricted), GitHub (classic PAT, fine-grained PAT, Actions secrets), Slack tokens + webhook URLs, Twilio, SendGrid, npm, PyPI, HuggingFace, Anthropic, OpenAI, Shopify, private key blocks (RSA/EC/DSA/OPENSSH/PuTTY), and `.env` literal assignments.

Patterns are compiled once at startup via `once_cell::Lazy` — no per-commit regex compilation cost.

### Layer 2 — CoreML on the Neural Engine (`~200ms`, hard block)

A TF-IDF char n-gram (3–5gram, 1024 features) + logistic regression classifier, trained on labeled clean/risky code samples and exported to `.mlpackage`. Runs with `compute_units=.cpuAndNeuralEngine` so inference actually hits the ANE.

**v2.1 model stats:**
- Training samples: **297** (up from 81 in v2.0)
- Languages: **Python, JS/TS, Java, Go, Rust, C#, PHP, Ruby, Swift, Kotlin, SQL**
- CV F1 (5-fold stratified): **0.754 ± 0.021** (up from 0.496 ± 0.229)
- Held-out verification: **32/33 cases (97%)**

This is the statistical layer. It catches things like `subprocess.run(shell=True)`, path traversal patterns, disabled TLS verification, and weak crypto that don't match any literal regex — and it does it across 11 languages now instead of just Python.

### Layer 3 — Qwen2.5-Coder-1.5B via MLX (`~5-8s`, advisory only)

The layer that reasons about the diff like a human reviewer would. It detects the language from diff file extensions, only reviews added lines, and flags:

- **Security** — SQL injection, command injection, XSS, unsafe deserialization, disabled TLS
- **Bug risk** — off-by-one errors, unhandled exceptions, null dereferences, race conditions
- **Code quality** — dead/orphan functions, unused variables, overly complex logic

All findings from a commit are written to **one consolidated report file** at `~/.localforge/reports/commit_<ts>.txt` — no one-file-per-finding noise. Large diffs are chunked at file boundaries and findings are merged and deduplicated. Runs async after the hook exits so it never adds latency to your actual `git commit`.

4-bit quantized, ~900MB resident, fully on-device via Apple's MLX framework.

---

## The distinction that matters

Layers 1 and 2 **block** the commit. Layer 3 **never blocks** — it advises.

That distinction is intentional. A false-positive block kills trust in a tool fast. A false-positive suggestion costs you nothing.

---

## What else is in the box

- **Native SwiftUI macOS app** with two tabs: a Monitor tab that tails `~/.localforge/hook.log` in real time (color-coded by layer), and a Repos tab that shows hook version status across all your protected repos and lets you upgrade them all in one click
- **`localforge --install`** — one command sets up `~/.localforge/`, copies the binary and model, auto-detects the Qwen model from your HuggingFace cache, installs the hook, and writes the PATH export to your `.zshrc`. No manual steps
- **`localforge --upgrade-all`** — keeps hooks in sync across all registered repos when the hook version bumps
- **MCP server** (`localforge --mcp-port 7777`) — JSON-RPC 2.0 over TCP for IDE integrations
- **Homebrew formula** — `brew tap stalzkie/local-forge && brew install localforge` (coming to the tap soon)
- **43 Rust unit tests** including 34 for the pattern layer: 20 detection tests, 10 false-positive guards, and 4 diff-awareness tests (e.g. removing a secret should never block)

---

## Stack

| | |
|---|---|
| Core binary | Rust 1.78 — tokio, clap, regex, once_cell, serde_json, ratatui |
| Layer 2 training | Python — scikit-learn, coremltools, numpy |
| Layer 2 runtime | Apple CoreML `CPU_AND_NE` |
| Layer 3 | Qwen2.5-Coder-1.5B-Instruct-4bit via Apple MLX |
| macOS app | Swift 6, SwiftUI, Combine, macOS 14+ |
| Protocol | JSON-RPC 2.0 over TCP (MCP) |

Everything runs on-device on M-series — no API calls, no telemetry, nothing leaves your laptop.

---

## Known limitations

- **Apple Silicon only** — CoreML and MLX are both Apple-specific. A Linux port would need a different runtime for both layers
- **Layer 2 is still a small model** — 297 samples is a real improvement over 81 but it's not a large dataset. The CV F1 variance tightened a lot (±0.229 → ±0.021) which tells me the generalization is better, but more data is still on the list
- **Layer 3 is a 1.5B model** — it's remarkably capable for its size but it will miss subtle logic bugs that a larger model would catch. Advisory-only status is the right call here

---

## Links

- **Repo:** https://github.com/stalzkie/local-forge
- **Original article (v2.0 release):** https://medium.com/@dstalingrad/localforge-building-an-on-device-ai-security-gateway-for-git-commits-16daf19fb6d6

Would love feedback, issues, or PRs — especially around growing the Layer 2 training set further or adding language-specific risky patterns I might have missed.
