mod advisory_engine;
mod ane_bridge;
mod ast_validator;
mod daemon_client;
mod mcp_server;
mod tui;

use clap::Parser;
use std::io::Read;

/// Bump this whenever the hook interface changes (new env vars, new exit codes,
/// new log format). The hook embeds the same number as LOCALFORGE_HOOK_VERSION.
const EXPECTED_HOOK_VERSION: u32 = 6;

const EMBEDDED_HOOK: &str = include_str!("../hooks/pre-commit");
const EMBEDDED_INFER: &str = include_str!("../coreml/infer.py");
const EMBEDDED_ADVISORY: &str = include_str!("../coreml/advisory.py");
const EMBEDDED_DAEMON: &str = include_str!("../coreml/daemon.py");

#[derive(Parser)]
#[command(
    name = "localforge",
    version = "2.1.3",
    about = "LocalForge Security Shield"
)]
struct Cli {
    /// Read a staged diff from stdin; exits 1 if blocked, 0 if clean
    #[arg(long)]
    scan: bool,

    /// Start the MCP JSON-RPC server on the given port
    #[arg(long)]
    mcp_port: Option<u16>,

    /// Plain-text monitor mode for GUI apps — prints structured log lines to stdout, no TUI
    #[arg(long)]
    monitor: bool,

    /// Install LocalForge: copy binary + model to ~/.localforge/, install hook into repo
    /// Optionally pass a repo path to protect; defaults to current directory
    #[arg(long, value_name = "REPO_PATH")]
    install: Option<Option<String>>,

    /// Remove LocalForge from ~/.localforge/ and uninstall hook from a repo
    /// Optionally pass a repo path; defaults to current directory
    #[arg(long, value_name = "REPO_PATH")]
    uninstall: Option<Option<String>>,

    /// List all repos registered with LocalForge and their hook status
    #[arg(long)]
    list_repos: bool,

    /// Re-install the latest hook into every registered repo
    #[arg(long)]
    upgrade_all: bool,

    /// Generate a setup script for your whole team.
    /// Outputs a shell script that any teammate can run to install LocalForge on their machine.
    /// Optionally pass a repo path; defaults to current directory.
    #[arg(long, value_name = "REPO_PATH")]
    install_org: Option<Option<String>>,

    /// Export scan reports to a file for compliance/auditing.
    /// Format: csv or json (default: json). Optionally pass --last N to limit report count.
    #[arg(long, value_name = "FORMAT")]
    export_report: Option<String>,

    /// Limit --export-report to the last N reports (default: all)
    #[arg(long, value_name = "N")]
    last: Option<usize>,

    /// Output path for --export-report (default: ./localforge-report.<ext>)
    #[arg(long, value_name = "PATH")]
    out: Option<String>,

    /// Toggle dry-run mode: on|off. While on, a blocked commit is logged and
    /// explained but never actually rejected — lets a team try LocalForge
    /// against real commits before it starts enforcing blocks.
    /// With no argument, prints whether dry-run is currently on or off.
    #[arg(long, value_name = "on|off", num_args = 0..=1, default_missing_value = "status")]
    dry_run: Option<String>,

    /// Add PATH to .localforgeignore at the repo root, so future scans skip it.
    /// Use right after a commit is blocked for a known false positive — no need
    /// to find and hand-edit .localforgeignore yourself.
    ///
    /// Example: localforge --allow tests/fixtures/fake_key.py
    #[arg(long, value_name = "PATH")]
    allow: Option<String>,

    /// Print a quick scriptable summary: hook status for this repo, dry-run
    /// state, registered repo count, Layer 2/3 availability, and the last
    /// few scan reports — without launching the full-screen TUI.
    #[arg(long)]
    status: bool,

    /// Control the warm-model daemon that keeps Layer 2/3 models resident
    /// across commits: start|stop. With no argument, prints whether it's
    /// currently running. The daemon is also started automatically (best
    /// effort, non-blocking) the first time a scan needs Layer 2 or 3.
    #[arg(long, value_name = "start|stop", num_args = 0..=1, default_missing_value = "status")]
    daemon: Option<String>,

    /// Scan the diff between BASE and HEAD and print findings as JSON.
    /// Exits 1 if Layer 1 detects secrets, 0 if clean.
    /// Respects .localforgeignore. Use in CI to scan PRs without the hook.
    ///
    /// Example: localforge --scan-pr main feature/my-branch
    #[arg(long, value_names = ["BASE", "HEAD"], num_args = 2)]
    scan_pr: Option<Vec<String>>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    if let Some(repo_arg) = cli.install {
        let repo = repo_arg.unwrap_or_else(|| ".".to_string());
        return run_install(&repo);
    }

    if let Some(repo_arg) = cli.uninstall {
        let repo = repo_arg.unwrap_or_else(|| ".".to_string());
        return run_uninstall(&repo);
    }

    if cli.list_repos {
        return run_list_repos();
    }

    if cli.upgrade_all {
        return run_upgrade_all();
    }

    if let Some(repo_arg) = cli.install_org {
        let repo = repo_arg.unwrap_or_else(|| ".".to_string());
        return run_install_org(&repo);
    }

    if let Some(fmt) = cli.export_report {
        return run_export_report(&fmt, cli.last, cli.out.as_deref());
    }

    if let Some(path) = cli.allow {
        return run_allow(&path);
    }

    if let Some(mode) = cli.dry_run {
        return run_dry_run(&mode);
    }

    if cli.status {
        return run_status();
    }

    if let Some(mode) = cli.daemon {
        return run_daemon_ctl(&mode);
    }

    if let Some(refs) = cli.scan_pr {
        let base = &refs[0];
        let head = &refs[1];
        return run_scan_pr(base, head);
    }

    if cli.scan {
        let mut diff = String::new();
        std::io::stdin().read_to_string(&mut diff)?;

        // ── Hook version check — warn but never block ─────────────────────────
        check_hook_version();

        // ── Layer 1: Rust AST regex — deterministic, <1 ms ───────────────────
        if ast_validator::scan(&diff) {
            // Layer 1 hard-blocks — spawn Layer 3 advisory in background so
            // the developer still gets a Qwen report, but don't wait for it.
            drop(advisory_engine::spawn(diff));
            std::process::exit(1);
        }

        // ── Layer 2: CoreML classifier — statistical, ~200 ms ─────────────────
        let layer2_blocked = match ane_bridge::analyse(&diff) {
            Ok(Some(ref result)) if result.risk_label == 1 => {
                if let Some(ref advisory) = result.advisory {
                    eprintln!("[LocalForge] ANE ADVISORY — {advisory}");
                }
                eprintln!(
                    "[LocalForge] Layer 2 risk score: {:.3} — commit blocked.",
                    result.risk_score
                );
                true
            }
            Ok(Some(ref result)) => {
                eprintln!(
                    "[LocalForge] Layer 2 score: {:.3} — clean.",
                    result.risk_score
                );
                false
            }
            Ok(None) => false,
            Err(e) => {
                eprintln!("[LocalForge] Layer 2 error (non-fatal): {e}");
                false
            }
        };

        // ── Layer 3: Qwen advisory — semantic, async, never blocks ────────────
        // Spawn immediately so inference starts while we decide on exit code.
        let advisory_handle = advisory_engine::spawn(diff.clone());

        if layer2_blocked {
            // Wait up to 30s for an advisory to accompany the block message
            if let Some(report) = advisory_engine::await_with_timeout(advisory_handle, 30).await {
                print_advisory(&report);
            }
            std::process::exit(1);
        }

        // Diff passed both blocking layers — wait briefly (10s) for advisory.
        // If Qwen finds something high/medium, warn but don't block.
        eprintln!("[LocalForge] Layers 1 & 2 passed. Running Qwen advisory (async)...");
        if let Some(report) = advisory_engine::await_with_timeout(advisory_handle, 30).await {
            print_advisory(&report);
            if report.severity.is_actionable() {
                eprintln!(
                    "[LocalForge] Advisory severity: {} — review report at: {}",
                    report.severity.label(),
                    report.report_path
                );
            }
        }

        std::process::exit(0);
    }

    if let Some(port) = cli.mcp_port {
        mcp_server::run(port).await?;
        return Ok(());
    }

    if cli.monitor {
        return run_monitor().await;
    }

    tui::run_dashboard()
}

async fn run_monitor() -> anyhow::Result<()> {
    use std::io::{BufRead, BufReader, Seek, SeekFrom};
    use std::time::Duration;
    use tokio::time::sleep;

    println!("[LocalForge] Monitor started — LocalForge Security Shield v2.0");
    println!("[LocalForge] 3-Layer pipeline: L1 AST  •  L2 CoreML/ANE  •  L3 Qwen/MLX");
    println!("[LocalForge] Watching for git hook scan events...");
    println!("[LocalForge] Layer 1 (AST regex): ready");

    match ane_bridge::analyse("healthcheck") {
        Ok(Some(_)) => println!("[LocalForge] Layer 2 (CoreML/ANE): ready"),
        Ok(None) => println!("[LocalForge] Layer 2 (CoreML/ANE): model not found — skipping"),
        Err(e) => println!("[LocalForge] Layer 2 (CoreML/ANE): unavailable ({e})"),
    }

    println!("[LocalForge] Layer 3 (Qwen/MLX): advisory engine ready");
    println!("[LocalForge] All layers initialised. Waiting for commits...");

    // Tail ~/.localforge/hook.log — forward any new lines written by the git hook
    let log_path = {
        let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
        std::path::PathBuf::from(home).join(".localforge/hook.log")
    };
    std::fs::create_dir_all(log_path.parent().unwrap()).ok();

    // Seek to end so we only show events that happen after the monitor starts
    let mut pos: u64 = std::fs::metadata(&log_path).map(|m| m.len()).unwrap_or(0);

    loop {
        sleep(Duration::from_millis(500)).await;

        if let Ok(file) = std::fs::File::open(&log_path) {
            let mut reader = BufReader::new(file);
            reader.seek(SeekFrom::Start(pos)).ok();
            let mut new_pos = pos;
            for line in reader.lines().map_while(Result::ok) {
                println!("{line}");
                new_pos += line.len() as u64 + 1; // +1 for newline
            }
            pos = new_pos;
        }
    }
}

// ── Installation ──────────────────────────────────────────────────────────────

fn run_install(repo_path: &str) -> anyhow::Result<()> {
    use std::fs;
    use std::path::PathBuf;

    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let lf_dir = PathBuf::from(&home).join(".localforge");
    let bin_dir = lf_dir.join("bin");
    let coreml_dir = lf_dir.join("coreml");

    // ── 1. Create directory structure ─────────────────────────────────────────
    for dir in [&lf_dir, &bin_dir, &coreml_dir, &lf_dir.join("reports")] {
        fs::create_dir_all(dir)?;
    }

    // ── 2. Copy binary ────────────────────────────────────────────────────────
    let self_path = std::env::current_exe()?;
    let bin_dest = bin_dir.join("localforge");
    fs::copy(&self_path, &bin_dest)?;
    // Make executable
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&bin_dest, fs::Permissions::from_mode(0o755))?;
    }
    println!("[LocalForge] ✓ Binary installed  → {}", bin_dest.display());

    // ── 3. Copy CoreML model ──────────────────────────────────────────────────
    // Search: already at dest → bundle Resources → repo-relative → cwd
    let model_dest = lf_dir.join("LocalForgeModel.mlpackage");
    let model_src = if model_dest.exists() {
        Some(model_dest.clone()) // already installed, skip copy
    } else {
        find_bundled_resource("LocalForgeModel.mlpackage")
            .or_else(|| find_repo_resource("LocalForgeModel.mlpackage"))
    };
    if let Some(src) = model_src {
        if src != model_dest {
            if model_dest.exists() {
                fs::remove_dir_all(&model_dest)?;
            }
            copy_dir_all(&src, &model_dest)?;
        }
        println!("[LocalForge] ✓ CoreML model     → {}", model_dest.display());
    } else {
        println!("[LocalForge] ⚠ CoreML model not found. Build it with:");
        println!("             python3 coreml/build_model.py");
    }

    // ── 4. Write Python shims (embedded at compile time) ─────────────────────
    for (shim, content) in [
        ("infer.py", EMBEDDED_INFER),
        ("advisory.py", EMBEDDED_ADVISORY),
        ("daemon.py", EMBEDDED_DAEMON),
    ] {
        let dest = coreml_dir.join(shim);
        if dest.exists() {
            println!(
                "[LocalForge] ✓ {shim:<14} → {} (already present)",
                dest.display()
            );
            continue;
        }
        fs::write(&dest, content)?;
        println!("[LocalForge] ✓ {shim:<14} → {}", dest.display());
    }

    // ── 5. Qwen 7B model — prefer 7B, fall back to 1.5B ─────────────────────
    let qwen_7b_dir = lf_dir.join("qwen2.5-coder-7b-4bit");
    let qwen_15b_dir = lf_dir.join("qwen2.5-coder-1.5b-4bit");

    if qwen_7b_dir.exists() {
        println!(
            "[LocalForge] ✓ Qwen 7B model     → {}",
            qwen_7b_dir.display()
        );
    } else if qwen_15b_dir.exists() {
        // Upgrade path: 1.5B present, download 7B
        println!("[LocalForge] ℹ Qwen 1.5B found. Downloading 7B for better accuracy...");
        install_qwen_model(
            &lf_dir,
            "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
            "qwen2.5-coder-7b-4bit",
        );
    } else {
        // Fresh install: try to find in repo/HF cache first, then download
        let repo_qwen = find_repo_resource("qwen2.5-coder-7b-4bit")
            .or_else(|| find_repo_resource("qwen2.5-coder-1.5b-4bit"));
        let hf_cache = find_qwen_in_hf_cache();
        if let Some(src) = repo_qwen.or(hf_cache) {
            if fs::rename(&src, &qwen_7b_dir).is_err() {
                copy_dir_all(&src, &qwen_7b_dir)?;
            }
            println!(
                "[LocalForge] ✓ Qwen model moved  → {}",
                qwen_7b_dir.display()
            );
        } else {
            println!(
                "[LocalForge] ℹ Downloading Qwen2.5-Coder-7B (4-bit, ~4GB) for Layer 3 advisory..."
            );
            install_qwen_model(
                &lf_dir,
                "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
                "qwen2.5-coder-7b-4bit",
            );
        }
    }

    // ── 5b. Static analysis tools — auto-install if missing ──────────────────
    println!();
    println!("[LocalForge] Checking static analysis tools (Layer 3.5)...");
    install_static_tools();

    // ── 6. Install git hook ───────────────────────────────────────────────────
    let repo = std::path::Path::new(repo_path);
    let git_hooks = repo.join(".git/hooks");
    if !git_hooks.exists() {
        println!(
            "[LocalForge] ⚠ Not a git repo: {} — skipping hook install",
            repo.display()
        );
        println!("             Run inside a git repo or pass the path:");
        println!("             localforge --install /path/to/your/repo");
    } else {
        let hook_dest = git_hooks.join("pre-commit");
        fs::write(&hook_dest, EMBEDDED_HOOK)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&hook_dest, fs::Permissions::from_mode(0o755))?;
        }
        println!("[LocalForge] ✓ Hook installed   → {}", hook_dest.display());

        // Register repo
        let repos_file = lf_dir.join("repos");
        let abs_repo = fs::canonicalize(repo).unwrap_or_else(|_| repo.to_path_buf());
        let abs_str = abs_repo.to_string_lossy().to_string();
        let existing = fs::read_to_string(&repos_file).unwrap_or_default();
        if !existing.lines().any(|l| l == abs_str) {
            fs::write(&repos_file, format!("{existing}{abs_str}\n"))?;
            println!("[LocalForge] ✓ Registered       → {}", repos_file.display());
        }
    }

    // ── 7. PATH hint ─────────────────────────────────────────────────────────
    let path_env = std::env::var("PATH").unwrap_or_default();
    if !path_env.contains(".localforge/bin") {
        println!();
        println!("[LocalForge] Add to your shell profile (~/.zshrc or ~/.bashrc):");
        println!("             export PATH=\"$HOME/.localforge/bin:$PATH\"");
    }

    println!();
    println!("[LocalForge] Installation complete. Every commit is now protected.");
    Ok(())
}

// ── Org install ───────────────────────────────────────────────────────────────

fn run_install_org(repo_path: &str) -> anyhow::Result<()> {
    use std::path::PathBuf;

    let repo_abs = std::fs::canonicalize(repo_path).unwrap_or_else(|_| PathBuf::from(repo_path));
    let repo_display = repo_abs.display();

    let script = format!(
        r#"#!/usr/bin/env bash
# LocalForge team install script
# Generated by: localforge --install-org
# Repo: {repo_display}
#
# Run this once per developer machine:
#   bash localforge-install-org.sh
#
# What it does:
#   1. Downloads the latest LocalForge binary for Apple Silicon
#   2. Installs it to ~/.localforge/bin/
#   3. Adds ~/.localforge/bin to your PATH in ~/.zshrc / ~/.bashrc
#   4. Installs the pre-commit hook into: {repo_display}
#
# Requirements: macOS 14+, Apple Silicon (M1/M2/M3/M4)

set -euo pipefail

LF_DIR="$HOME/.localforge"
BIN_DIR="$LF_DIR/bin"
BINARY="$BIN_DIR/localforge"
REPO="{repo_display}"
RELEASE_URL="https://github.com/stalzkie/local-forge/releases/latest/download/localforge-macos-arm64"

echo "[LocalForge] Starting team install..."

# ── 1. Create directories ─────────────────────────────────────────────────────
mkdir -p "$BIN_DIR" "$LF_DIR/coreml" "$LF_DIR/reports"

# ── 2. Download binary ────────────────────────────────────────────────────────
if [ -f "$BINARY" ]; then
    echo "[LocalForge] Binary already installed at $BINARY — checking for update..."
fi

echo "[LocalForge] Downloading LocalForge binary..."
curl -fsSL "$RELEASE_URL" -o "$BINARY"
chmod +x "$BINARY"
echo "[LocalForge] ✓ Binary installed → $BINARY"

# ── 3. PATH setup ─────────────────────────────────────────────────────────────
add_to_path() {{
    local profile="$1"
    local line='export PATH="$HOME/.localforge/bin:$PATH"'
    if [ -f "$profile" ] && grep -qF ".localforge/bin" "$profile"; then
        return 0
    fi
    printf '\n# LocalForge\n%s\n' "$line" >> "$profile"
    echo "[LocalForge] ✓ PATH added to $profile"
}}

add_to_path "$HOME/.zshrc"
[ -f "$HOME/.bashrc" ] && add_to_path "$HOME/.bashrc"

# ── 4. Install hook into repo ─────────────────────────────────────────────────
if [ -d "$REPO/.git" ]; then
    "$BINARY" --install "$REPO"
else
    echo "[LocalForge] ⚠ $REPO is not a git repo — skipping hook install."
    echo "             Run: localforge --install /path/to/your/repo"
fi

echo ""
echo "[LocalForge] ✓ Team install complete."
echo "             Open a new terminal (or run: source ~/.zshrc) to activate PATH."
echo "             Every commit in $REPO is now protected."
echo ""
echo "             To protect additional repos:"
echo "               localforge --install /path/to/other/repo"
echo ""
echo "             To install the Layer 2 CoreML model (required for statistical scanning):"
echo "               python3 -m pip install coremltools scikit-learn"
echo "               python3 coreml/build_model.py   # from the LocalForge repo"
echo ""
echo "             To install the Layer 3 Qwen advisory model:"
echo "               pip3 install mlx-lm"
echo '               python3 -c "from mlx_lm import load; load(\"Qwen/Qwen2.5-Coder-1.5B-Instruct-4bit\")"'
"#
    );

    let out_path = "localforge-install-org.sh";
    std::fs::write(out_path, &script)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(out_path, std::fs::Permissions::from_mode(0o755))?;
    }

    println!("[LocalForge] ✓ Team install script written → {out_path}");
    println!();
    println!("  Share this with your team:");
    println!("    bash {out_path}");
    println!();
    println!("  Or add to your dev setup doc / Makefile:");
    println!("    curl -fsSL https://raw.githubusercontent.com/stalzkie/local-forge/main/localforge-install-org.sh | bash");
    println!();
    println!("  Each dev runs it once. No admin rights required.");

    Ok(())
}

// ── Report export ─────────────────────────────────────────────────────────────

#[derive(serde::Serialize)]
struct ReportEntry {
    filename: String,
    timestamp: String,
    commit_id: String,
    severity: String,
    summary: String,
    findings: usize,
    raw_path: String,
}

fn parse_report_file(path: &std::path::Path) -> Option<ReportEntry> {
    let content = std::fs::read_to_string(path).ok()?;
    let filename = path.file_name()?.to_string_lossy().to_string();

    // Parse header lines: "  Key  : Value"
    let mut timestamp = String::from("unknown");
    let mut commit_id = String::from("unknown");
    let mut severity = String::from("CLEAN");
    let mut summary = String::from("");

    for line in content.lines().take(20) {
        let line = line.trim();
        if line.starts_with("Severity") {
            if let Some(v) = line.split_once(':').map(|x| x.1) {
                severity = v.trim().to_string();
            }
        } else if line.starts_with("Summary") {
            if let Some(v) = line.split_once(':').map(|x| x.1) {
                summary = v.trim().to_string();
            }
        } else if line.contains("UTC") && line.contains('|') {
            // "  2026-06-18 12:34:11 UTC  |  diff: abc123  |  model: ..."
            let parts: Vec<&str> = line.split('|').collect();
            if let Some(ts) = parts.first() {
                timestamp = ts.trim().to_string();
            }
            if let Some(diff_part) = parts.get(1) {
                if let Some(v) = diff_part.trim().strip_prefix("diff:") {
                    commit_id = v.trim().to_string();
                }
            }
        }
    }

    // Count finding blocks: lines that start with "  [N]"
    let findings = content
        .lines()
        .filter(|l| {
            let t = l.trim();
            t.starts_with('[')
                && t.len() > 3
                && t.chars().nth(1).is_some_and(|c| c.is_ascii_digit())
        })
        .count();

    Some(ReportEntry {
        filename,
        timestamp,
        commit_id,
        severity,
        summary,
        findings,
        raw_path: path.to_string_lossy().to_string(),
    })
}

fn run_export_report(fmt: &str, last: Option<usize>, out: Option<&str>) -> anyhow::Result<()> {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let reports_dir = std::path::PathBuf::from(&home).join(".localforge/reports");

    if !reports_dir.exists() {
        println!("[LocalForge] No reports found at {}", reports_dir.display());
        println!("             Reports are generated after each commit scan.");
        return Ok(());
    }

    let mut entries: Vec<std::path::PathBuf> = std::fs::read_dir(&reports_dir)?
        .flatten()
        .filter(|e| {
            e.path().extension().is_some_and(|x| x == "txt")
                && e.file_name().to_string_lossy().starts_with("commit_")
        })
        .map(|e| e.path())
        .collect();

    // Sort newest first (filename contains timestamp)
    entries.sort_by(|a, b| b.file_name().cmp(&a.file_name()));

    if let Some(n) = last {
        entries.truncate(n);
    }

    if entries.is_empty() {
        println!("[LocalForge] No commit reports found.");
        return Ok(());
    }

    let records: Vec<ReportEntry> = entries
        .iter()
        .filter_map(|p| parse_report_file(p))
        .collect();

    let fmt_lower = fmt.to_lowercase();
    let ext = if fmt_lower == "csv" { "csv" } else { "json" };
    let out_path = out
        .map(|s| s.to_string())
        .unwrap_or_else(|| format!("localforge-report.{ext}"));

    match fmt_lower.as_str() {
        "csv" => {
            let mut csv =
                String::from("filename,timestamp,commit_id,severity,summary,findings,raw_path\n");
            for r in &records {
                // Escape commas in summary
                let summary_escaped = format!("\"{}\"", r.summary.replace('"', "\"\""));
                csv.push_str(&format!(
                    "{},{},{},{},{},{},{}\n",
                    r.filename,
                    r.timestamp,
                    r.commit_id,
                    r.severity,
                    summary_escaped,
                    r.findings,
                    r.raw_path,
                ));
            }
            std::fs::write(&out_path, csv)?;
        }
        _ => {
            let json = serde_json::to_string_pretty(&records)?;
            std::fs::write(&out_path, json)?;
        }
    }

    println!(
        "[LocalForge] ✓ Exported {} report(s) → {}",
        records.len(),
        out_path
    );
    println!();

    // Print summary table to terminal
    println!(
        "  {:<40}  {:<8}  {:<8}  Summary",
        "Commit", "Severity", "Findings"
    );
    println!("  {}", "─".repeat(90));
    for r in &records {
        let short_id = if r.commit_id.len() > 8 {
            &r.commit_id[..8]
        } else {
            &r.commit_id
        };
        let short_summary = if r.summary.len() > 40 {
            format!("{}…", &r.summary[..39])
        } else {
            r.summary.clone()
        };
        println!(
            "  {:<40}  {:<8}  {:<8}  {}",
            short_id, r.severity, r.findings, short_summary
        );
    }
    println!();

    Ok(())
}

fn run_status() -> anyhow::Result<()> {
    use std::path::PathBuf;

    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let lf_dir = PathBuf::from(&home).join(".localforge");

    println!("[LocalForge] Status");
    println!();

    // ── Hook status for the current repo ──────────────────────────────────────
    let cwd_hook_status = match std::process::Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
    {
        Ok(out) if out.status.success() => {
            let repo_root = String::from_utf8_lossy(&out.stdout).trim().to_string();
            let repo = std::path::Path::new(&repo_root);
            let hook = repo.join(".git/hooks/pre-commit");
            if !hook.exists() {
                "⚠ hook missing — run: localforge --install".to_string()
            } else {
                let content = std::fs::read_to_string(&hook).unwrap_or_default();
                if !content.contains("LocalForge") {
                    "⚠ hook replaced by another tool".to_string()
                } else {
                    match hook_version_in_repo(repo) {
                        Some(v) if v < EXPECTED_HOOK_VERSION => format!(
                            "⚠ hook v{v} outdated (binary expects v{EXPECTED_HOOK_VERSION}) — run: localforge --install"
                        ),
                        Some(v) if v > EXPECTED_HOOK_VERSION => {
                            format!("⚠ hook v{v} newer than binary v{EXPECTED_HOOK_VERSION} — update binary")
                        }
                        Some(v) => format!("✓ active (v{v})"),
                        None => "✓ active (unversioned)".to_string(),
                    }
                }
            }
        }
        _ => "— not inside a git repository".to_string(),
    };
    println!("  Hook (this repo):    {cwd_hook_status}");

    // ── Dry-run mode ───────────────────────────────────────────────────────────
    let dry_run_state = if lf_dir.join("dry_run").exists() {
        "ON"
    } else {
        "OFF"
    };
    println!("  Dry-run mode:        {dry_run_state}");

    // ── Registered repos ───────────────────────────────────────────────────────
    let repos_file = lf_dir.join("repos");
    let repo_count = std::fs::read_to_string(&repos_file)
        .unwrap_or_default()
        .lines()
        .filter(|l| !l.is_empty())
        .count();
    println!("  Registered repos:    {repo_count}");

    // ── Layer availability ─────────────────────────────────────────────────────
    println!("  Layer 1 (regex):     ✓ always available");
    println!(
        "  Layer 2 (CoreML):    {}",
        if ane_bridge::is_available() {
            "✓ available"
        } else {
            "✗ not built — run: localforge --install"
        }
    );
    println!(
        "  Layer 3 (Qwen):      {}",
        if advisory_engine::is_available() {
            "✓ available"
        } else {
            "✗ not built — run: localforge --install"
        }
    );
    println!(
        "  Warm-model daemon:   {}",
        if daemon_client::is_running() {
            "✓ running"
        } else {
            "— not running (starts automatically on next Layer 2/3 scan)"
        }
    );

    // ── Recent scans ───────────────────────────────────────────────────────────
    let reports_dir = lf_dir.join("reports");
    println!();
    if !reports_dir.exists() {
        println!("  No scan reports yet.");
        println!();
        return Ok(());
    }

    let mut entries: Vec<PathBuf> = std::fs::read_dir(&reports_dir)?
        .flatten()
        .filter(|e| {
            e.path().extension().is_some_and(|x| x == "txt")
                && e.file_name().to_string_lossy().starts_with("commit_")
        })
        .map(|e| e.path())
        .collect();
    entries.sort_by(|a, b| b.file_name().cmp(&a.file_name()));
    entries.truncate(5);

    if entries.is_empty() {
        println!("  No scan reports yet.");
        println!();
        return Ok(());
    }

    println!("  Last {} scan(s):", entries.len());
    for r in entries.iter().filter_map(|p| parse_report_file(p)) {
        let short_id = if r.commit_id.len() > 8 {
            &r.commit_id[..8]
        } else {
            &r.commit_id
        };
        println!(
            "    {}  {:<8}  {:<8}  {} finding(s)",
            r.timestamp, short_id, r.severity, r.findings
        );
    }
    println!();

    Ok(())
}

fn run_uninstall(repo_path: &str) -> anyhow::Result<()> {
    use std::fs;
    use std::path::PathBuf;

    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let lf_dir = PathBuf::from(&home).join(".localforge");

    // ── Remove hook from repo ─────────────────────────────────────────────────
    let repo = std::path::Path::new(repo_path);
    let hook = repo.join(".git/hooks/pre-commit");
    if hook.exists() {
        // Only remove if it's a LocalForge hook
        let content = fs::read_to_string(&hook).unwrap_or_default();
        if content.contains("LocalForge") {
            fs::remove_file(&hook)?;
            println!("[LocalForge] ✓ Hook removed from {}", hook.display());
        } else {
            println!(
                "[LocalForge] ⚠ Hook at {} is not a LocalForge hook — skipping",
                hook.display()
            );
        }
    }

    // ── Remove repo from registry ─────────────────────────────────────────────
    let repos_file = lf_dir.join("repos");
    if repos_file.exists() {
        let abs_repo = fs::canonicalize(repo).unwrap_or_else(|_| repo.to_path_buf());
        let abs_str = abs_repo.to_string_lossy().to_string();
        let existing = fs::read_to_string(&repos_file).unwrap_or_default();
        let filtered: String = existing
            .lines()
            .filter(|l| *l != abs_str)
            .map(|l| format!("{l}\n"))
            .collect();
        fs::write(&repos_file, filtered)?;
        println!("[LocalForge] ✓ Deregistered {}", abs_str);
    }

    println!();
    println!("[LocalForge] Uninstall complete for {}.", repo_path);
    println!("             To fully remove LocalForge: rm -rf ~/.localforge");
    Ok(())
}

fn run_list_repos() -> anyhow::Result<()> {
    use std::path::PathBuf;

    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let repos_file = PathBuf::from(&home).join(".localforge/repos");

    if !repos_file.exists() {
        println!("[LocalForge] No repos registered. Run: localforge --install");
        return Ok(());
    }

    let content = std::fs::read_to_string(&repos_file).unwrap_or_default();
    let repos: Vec<&str> = content.lines().filter(|l| !l.is_empty()).collect();

    if repos.is_empty() {
        println!("[LocalForge] No repos registered.");
        return Ok(());
    }

    println!("[LocalForge] Registered repos ({}):", repos.len());
    println!();

    for repo in repos {
        let path = std::path::Path::new(repo);
        let hook = path.join(".git/hooks/pre-commit");
        let exists = path.exists();

        let hook_status = if !exists {
            "✗ path not found".to_string()
        } else if !hook.exists() {
            "⚠ hook missing — run: localforge --install".to_string()
        } else {
            let content = std::fs::read_to_string(&hook).unwrap_or_default();
            if !content.contains("LocalForge") {
                "⚠ hook replaced by another tool".to_string()
            } else {
                match hook_version_in_repo(path) {
                    Some(v) if v < EXPECTED_HOOK_VERSION =>
                        format!("⚠ hook v{v} outdated (binary expects v{EXPECTED_HOOK_VERSION}) — run: localforge --install"),
                    Some(v) if v > EXPECTED_HOOK_VERSION =>
                        format!("⚠ hook v{v} newer than binary v{EXPECTED_HOOK_VERSION} — update binary"),
                    Some(v) =>
                        format!("✓ hook active (v{v})"),
                    None =>
                        "✓ hook active (unversioned)".to_string(),
                }
            }
        };

        println!("  {} — {}", repo, hook_status);
    }

    println!();
    Ok(())
}

fn run_upgrade_all() -> anyhow::Result<()> {
    use std::path::PathBuf;

    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let repos_file = PathBuf::from(&home).join(".localforge/repos");

    if !repos_file.exists() {
        println!("[LocalForge] No repos registered. Run: localforge --install");
        return Ok(());
    }

    let content = std::fs::read_to_string(&repos_file).unwrap_or_default();
    let repos: Vec<&str> = content.lines().filter(|l| !l.is_empty()).collect();

    if repos.is_empty() {
        println!("[LocalForge] No repos registered.");
        return Ok(());
    }

    println!("[LocalForge] Upgrading hooks in {} repo(s)...", repos.len());
    println!();

    let mut upgraded = 0;
    let mut skipped = 0;

    for repo in &repos {
        let path = std::path::Path::new(repo);
        let git_hooks = path.join(".git/hooks");

        if !git_hooks.exists() {
            println!("  ✗ {} — not a git repo, skipping", repo);
            skipped += 1;
            continue;
        }

        let hook_dest = git_hooks.join("pre-commit");
        match std::fs::write(&hook_dest, EMBEDDED_HOOK) {
            Ok(_) => {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    let _ = std::fs::set_permissions(
                        &hook_dest,
                        std::fs::Permissions::from_mode(0o755),
                    );
                }
                println!("  ✓ {} — hook upgraded to v{EXPECTED_HOOK_VERSION}", repo);
                upgraded += 1;
            }
            Err(e) => {
                println!("  ✗ {} — failed: {e}", repo);
                skipped += 1;
            }
        }
    }

    println!();
    println!("[LocalForge] Done: {upgraded} upgraded, {skipped} skipped.");
    Ok(())
}

// ── Hook version check ────────────────────────────────────────────────────────

fn check_hook_version() {
    // Read the hook from the current repo's .git/hooks/pre-commit
    let hook_path = match find_current_hook() {
        Some(p) => p,
        None => return, // no hook found — nothing to check
    };

    let content = match std::fs::read_to_string(&hook_path) {
        Ok(c) => c,
        Err(_) => return,
    };

    let installed_version = parse_hook_version(&content);

    if let Some(v) = installed_version {
        if v < EXPECTED_HOOK_VERSION {
            eprintln!(
                "[LocalForge] ⚠ Hook version mismatch: hook is v{v}, binary expects v{EXPECTED_HOOK_VERSION}."
            );
            eprintln!("[LocalForge]   Update with: localforge --install");
        }
        // v > EXPECTED means a newer hook with an older binary — also warn
        if v > EXPECTED_HOOK_VERSION {
            eprintln!(
                "[LocalForge] ⚠ Hook version v{v} is newer than binary v{EXPECTED_HOOK_VERSION}."
            );
            eprintln!(
                "[LocalForge]   Update binary: cargo build --release && localforge --install"
            );
        }
    }
    // If no version line found, hook predates versioning — silently skip
}

fn parse_hook_version(content: &str) -> Option<u32> {
    for line in content.lines().take(10) {
        if let Some(rest) = line.strip_prefix("# LOCALFORGE_HOOK_VERSION=") {
            return rest.trim().parse::<u32>().ok();
        }
    }
    None
}

fn find_current_hook() -> Option<std::path::PathBuf> {
    // Walk up from cwd to find .git/hooks/pre-commit
    let mut dir = std::env::current_dir().ok()?;
    loop {
        let hook = dir.join(".git/hooks/pre-commit");
        if hook.exists() {
            return Some(hook);
        }
        if !dir.pop() {
            return None;
        }
    }
}

/// Extract the hook version from a repo's pre-commit hook (used by --list-repos).
fn hook_version_in_repo(repo: &std::path::Path) -> Option<u32> {
    let hook = repo.join(".git/hooks/pre-commit");
    let content = std::fs::read_to_string(hook).ok()?;
    parse_hook_version(&content)
}

// ── Install helpers ───────────────────────────────────────────────────────────

/// Find a resource by checking app bundle Resources, then repo-relative paths.
fn find_bundled_resource(relative: &str) -> Option<std::path::PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(macos) = exe.parent() {
            let candidate = macos
                .parent()
                .unwrap_or(macos)
                .join("Resources")
                .join(relative);
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }
    None
}

/// Find a resource relative to the repo root (two levels up from src/).
fn find_repo_resource(relative: &str) -> Option<std::path::PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        // target/release/localforge → go up to repo root
        if let Some(p) = exe
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
        {
            let candidate = p.join(relative);
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }
    // cwd-relative fallback
    let cwd = std::path::PathBuf::from(relative);
    if cwd.exists() {
        return Some(cwd);
    }
    None
}

/// Search the HuggingFace hub cache for the Qwen2.5-Coder snapshot directory.
fn find_qwen_in_hf_cache() -> Option<std::path::PathBuf> {
    let home = dirs::home_dir()?;
    let hub = home.join(".cache/huggingface/hub");
    // Look for models--Qwen--Qwen2.5-Coder* directories
    let rd = std::fs::read_dir(&hub).ok()?;
    for entry in rd.flatten() {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.starts_with("models--Qwen--Qwen2.5-Coder") && entry.file_type().ok()?.is_dir() {
            // Find the snapshots/<hash>/ directory inside
            let snapshots = entry.path().join("snapshots");
            if let Ok(snaps) = std::fs::read_dir(&snapshots) {
                for snap in snaps.flatten() {
                    if snap.file_type().ok()?.is_dir() {
                        return Some(snap.path());
                    }
                }
            }
        }
    }
    None
}

/// Recursively copy a directory (used for .mlpackage which is a directory).
fn copy_dir_all(src: &std::path::Path, dst: &std::path::Path) -> anyhow::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        if ty.is_dir() {
            copy_dir_all(&entry.path(), &dst.join(entry.file_name()))?;
        } else {
            std::fs::copy(entry.path(), dst.join(entry.file_name()))?;
        }
    }
    Ok(())
}

fn install_qwen_model(lf_dir: &std::path::Path, hf_repo: &str, model_name: &str) {
    // Ensure mlx-lm is available
    let pip_ok = std::process::Command::new("pip3")
        .args(["install", "-q", "mlx-lm"])
        .status()
        .map(|s| s.success())
        .unwrap_or(false);

    if !pip_ok {
        println!("[LocalForge] ⚠ pip3 not found — cannot auto-download Qwen model.");
        println!("             Install Python 3 and run: pip3 install mlx-lm");
        println!("             Then: python3 -m mlx_lm.convert --hf-path {hf_repo} --mlx-path ~/.localforge/{model_name}");
        return;
    }

    let dest = lf_dir.join(model_name);
    println!("[LocalForge]   Destination: {}", dest.display());
    println!("[LocalForge]   This may take a few minutes depending on your connection...");

    let status = std::process::Command::new("python3")
        .args([
            "-c",
            &format!(
                "from mlx_lm import load; import os; \
                 m,t=load('{hf_repo}'); \
                 print('[LocalForge] ✓ Qwen model downloaded')"
            ),
        ])
        .status();

    match status {
        Ok(s) if s.success() => {
            // mlx_lm.load caches to ~/.cache/huggingface — move to .localforge
            let hf_cache = std::path::PathBuf::from(std::env::var("HOME").unwrap_or_default())
                .join(".cache/huggingface/hub");
            if let Ok(entries) = std::fs::read_dir(&hf_cache) {
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().to_lowercase();
                    if name.contains("qwen2.5-coder") && name.contains(&model_name[..6]) {
                        let _ = std::fs::rename(entry.path(), &dest)
                            .or_else(|_| copy_dir_all(&entry.path(), &dest));
                        break;
                    }
                }
            }
            if dest.exists() {
                println!("[LocalForge] ✓ Qwen model ready  → {}", dest.display());
            } else {
                println!("[LocalForge] ✓ Qwen model cached in HuggingFace cache.");
                println!("             advisory.py will find it automatically.");
            }
        }
        _ => {
            println!("[LocalForge] ⚠ Model download failed. To install manually:");
            println!("               pip3 install mlx-lm");
            println!("               python3 -m mlx_lm.convert --hf-path {hf_repo} \\");
            println!("                 --mlx-path ~/.localforge/{model_name}");
        }
    }
}

fn install_static_tools() {
    // ── bandit (Python security) ──────────────────────────────────────────────
    let bandit_ok = which_tool("bandit");
    if bandit_ok {
        println!("[LocalForge] ✓ bandit            → installed");
    } else {
        print!("[LocalForge]   Installing bandit (Python security)... ");
        let ok = std::process::Command::new("pip3")
            .args(["install", "-q", "bandit"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        println!(
            "{}",
            if ok {
                "✓"
            } else {
                "⚠ failed (pip3 install bandit)"
            }
        );
    }

    // ── pylint (Python quality) ───────────────────────────────────────────────
    let pylint_ok = which_tool("pylint");
    if pylint_ok {
        println!("[LocalForge] ✓ pylint            → installed");
    } else {
        print!("[LocalForge]   Installing pylint (Python quality)... ");
        let ok = std::process::Command::new("pip3")
            .args(["install", "-q", "pylint"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        println!(
            "{}",
            if ok {
                "✓"
            } else {
                "⚠ failed (pip3 install pylint)"
            }
        );
    }

    // ── eslint (JS/TS) ────────────────────────────────────────────────────────
    let eslint_ok = which_tool("eslint");
    if eslint_ok {
        println!("[LocalForge] ✓ eslint            → installed");
    } else {
        print!("[LocalForge]   Installing eslint (JS/TS quality)... ");
        let ok = std::process::Command::new("npm")
            .args(["install", "-g", "--silent", "eslint"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !ok {
            println!("⚠ failed");
            println!("             npm not found or permission error.");
            println!("             To install manually: npm install -g eslint");
        } else {
            println!("✓");
        }
    }

    // ── staticcheck (Go) ─────────────────────────────────────────────────────
    let sc_ok = which_tool("staticcheck");
    if sc_ok {
        println!("[LocalForge] ✓ staticcheck       → installed");
    } else {
        // Try go install first, then brew
        let go_ok = which_tool("go");
        if go_ok {
            print!("[LocalForge]   Installing staticcheck (Go quality)... ");
            let ok = std::process::Command::new("go")
                .args(["install", "honnef.co/go/tools/cmd/staticcheck@latest"])
                .status()
                .map(|s| s.success())
                .unwrap_or(false);
            println!(
                "{}",
                if ok {
                    "✓"
                } else {
                    "⚠ failed (go install staticcheck)"
                }
            );
        } else {
            // Try brew
            let brew_ok = which_tool("brew");
            if brew_ok {
                print!("[LocalForge]   Installing staticcheck via brew... ");
                let ok = std::process::Command::new("brew")
                    .args(["install", "-q", "staticcheck"])
                    .status()
                    .map(|s| s.success())
                    .unwrap_or(false);
                println!("{}", if ok { "✓" } else { "⚠ failed" });
            } else {
                println!("[LocalForge] ⚠ staticcheck not found.");
                println!("             Install with: brew install staticcheck");
            }
        }
    }

    // ── go vet (built into go toolchain) ─────────────────────────────────────
    if which_tool("go") {
        println!("[LocalForge] ✓ go vet            → available (part of Go toolchain)");
    } else {
        println!("[LocalForge] ℹ go not found — Go static analysis will be skipped.");
        println!("             Install Go from https://go.dev/dl/ to enable it.");
    }

    // ── cargo clippy (built into rustup) ─────────────────────────────────────
    if which_tool("cargo") {
        let clippy_ok = std::process::Command::new("cargo")
            .args(["clippy", "--version"])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false);
        if clippy_ok {
            println!("[LocalForge] ✓ cargo clippy      → available");
        } else {
            print!("[LocalForge]   Installing clippy component... ");
            let ok = std::process::Command::new("rustup")
                .args(["component", "add", "clippy"])
                .status()
                .map(|s| s.success())
                .unwrap_or(false);
            println!(
                "{}",
                if ok {
                    "✓"
                } else {
                    "⚠ failed (rustup component add clippy)"
                }
            );
        }
    } else {
        println!("[LocalForge] ℹ cargo not found — Rust static analysis will be skipped.");
    }
}

fn which_tool(name: &str) -> bool {
    std::process::Command::new("which")
        .arg(name)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn print_advisory(report: &advisory_engine::AdvisoryResult) {
    eprintln!(
        "[LocalForge] Qwen [{severity}] {summary}",
        severity = report.severity.label(),
        summary = report.summary,
    );
    for (i, f) in report.findings.iter().enumerate() {
        let cat = f.category.as_deref().unwrap_or("general").to_uppercase();
        eprintln!(
            "[LocalForge]   [{cat}] Finding {n}: {t} — {exp}",
            n = i + 1,
            t = f.r#type,
            exp = f.explanation,
        );
        eprintln!("[LocalForge]   Fix: {}", f.remediation);
    }
    if !report.report_path.is_empty() {
        eprintln!("[LocalForge]   Full report: {}", report.report_path);
    }
}

// ── --dry-run ─────────────────────────────────────────────────────────────────

/// Toggle `~/.localforge/dry_run`. Its mere presence tells the pre-commit hook
/// (LOCALFORGE_HOOK_VERSION >= 6) to log a would-have-blocked commit and let it
/// through instead of rejecting it.
fn run_dry_run(mode: &str) -> anyhow::Result<()> {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let marker = std::path::PathBuf::from(&home).join(".localforge/dry_run");

    match mode {
        "on" => {
            if let Some(parent) = marker.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::write(&marker, "")?;
            println!(
                "[LocalForge] Dry-run mode ON — blocked commits will be logged, not rejected."
            );
        }
        "off" => {
            if marker.exists() {
                std::fs::remove_file(&marker)?;
            }
            println!("[LocalForge] Dry-run mode OFF — blocked commits are rejected as normal.");
        }
        "status" => {
            let state = if marker.exists() { "ON" } else { "OFF" };
            println!("[LocalForge] Dry-run mode is {state}.");
        }
        other => {
            anyhow::bail!("unknown --dry-run value '{other}' — expected 'on' or 'off'");
        }
    }
    Ok(())
}

// ── --daemon ──────────────────────────────────────────────────────────────────

fn run_daemon_ctl(mode: &str) -> anyhow::Result<()> {
    match mode {
        "start" => {
            daemon_client::ensure_running(&daemon_client::resolve_daemon_script());
            // ensure_running is fire-and-forget; give it a moment to bind
            // the socket before reporting status back to the user.
            std::thread::sleep(std::time::Duration::from_millis(500));
            if daemon_client::is_running() {
                println!("[LocalForge] ✓ Warm-model daemon is running.");
            } else {
                println!(
                    "[LocalForge] Daemon starting in the background — check again with: localforge --daemon"
                );
            }
        }
        "stop" => {
            if daemon_client::request(&serde_json::json!({"cmd": "shutdown"})).is_some() {
                println!("[LocalForge] ✓ Warm-model daemon stopped.");
            } else {
                println!("[LocalForge] Daemon was not running.");
            }
        }
        "status" => {
            let state = if daemon_client::is_running() {
                "running"
            } else {
                "not running"
            };
            println!("[LocalForge] Warm-model daemon is {state}.");
        }
        other => {
            anyhow::bail!("unknown --daemon value '{other}' — expected 'start' or 'stop'");
        }
    }
    Ok(())
}

// ── --allow ───────────────────────────────────────────────────────────────────

/// Add `path` to .localforgeignore at the repo root, creating the file if it
/// doesn't exist yet. No-op (with a message) if the path is already listed.
fn run_allow(path: &str) -> anyhow::Result<()> {
    let toplevel_out = std::process::Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
        .map_err(|e| anyhow::anyhow!("failed to run git rev-parse: {e}"))?;

    if !toplevel_out.status.success() {
        anyhow::bail!("not inside a git repository");
    }

    let repo_root = String::from_utf8_lossy(&toplevel_out.stdout)
        .trim()
        .to_string();
    let ignore_path = std::path::Path::new(&repo_root).join(".localforgeignore");

    let existing = std::fs::read_to_string(&ignore_path).unwrap_or_default();
    if existing.lines().any(|l| l.trim() == path) {
        println!("[LocalForge] {path} is already in .localforgeignore — nothing to do.");
        return Ok(());
    }

    let mut updated = existing;
    if !updated.is_empty() && !updated.ends_with('\n') {
        updated.push('\n');
    }
    updated.push_str(path);
    updated.push('\n');

    std::fs::write(&ignore_path, updated)?;
    println!("[LocalForge] ✓ Added '{path}' to {}", ignore_path.display());
    println!(
        "[LocalForge]   Future scans will skip this path. Stage and commit the ignore file update."
    );
    Ok(())
}

// ── --scan-pr ─────────────────────────────────────────────────────────────────

/// Strip diff hunks for files that match any .localforgeignore pattern.
/// Mirrors the awk logic in the pre-commit hook (substring match per line).
fn apply_localforgeignore(diff: &str) -> (String, Vec<String>) {
    let ignore_path = std::path::Path::new(".localforgeignore");
    let patterns: Vec<String> = if ignore_path.exists() {
        std::fs::read_to_string(ignore_path)
            .unwrap_or_default()
            .lines()
            .filter(|l| !l.trim_start().starts_with('#') && !l.trim().is_empty())
            .map(|l| l.to_string())
            .collect()
    } else {
        vec![]
    };

    if patterns.is_empty() {
        return (diff.to_string(), vec![]);
    }

    let mut out = String::new();
    let mut ignored_files: Vec<String> = vec![];
    let mut skip = false;

    for line in diff.lines() {
        if line.starts_with("diff --git ") {
            let file = line
                .split_whitespace()
                .last()
                .unwrap_or("")
                .trim_start_matches("b/")
                .to_string();
            skip = patterns.iter().any(|p| file.contains(p.as_str()));
            if skip {
                ignored_files.push(file.clone());
            }
        }
        if !skip {
            out.push_str(line);
            out.push('\n');
        }
    }

    (out, ignored_files)
}

fn run_scan_pr(base: &str, head: &str) -> anyhow::Result<()> {
    // ── Collect diff ──────────────────────────────────────────────────────────
    let diff_out = std::process::Command::new("git")
        .args(["diff", &format!("{base}..{head}")])
        .output()
        .map_err(|e| anyhow::anyhow!("failed to run git diff: {e}"))?;

    if !diff_out.status.success() {
        let msg = String::from_utf8_lossy(&diff_out.stderr);
        anyhow::bail!("git diff {base}..{head} failed: {msg}");
    }

    let raw_diff = String::from_utf8_lossy(&diff_out.stdout).to_string();

    // ── Collect changed file names ────────────────────────────────────────────
    let names_out = std::process::Command::new("git")
        .args(["diff", "--name-only", &format!("{base}..{head}")])
        .output()
        .map_err(|e| anyhow::anyhow!("failed to run git diff --name-only: {e}"))?;
    let all_files: Vec<String> = String::from_utf8_lossy(&names_out.stdout)
        .lines()
        .filter(|l| !l.is_empty())
        .map(|l| l.to_string())
        .collect();

    // ── Apply .localforgeignore ───────────────────────────────────────────────
    let (filtered_diff, ignored_files) = apply_localforgeignore(&raw_diff);
    let scanned_files: Vec<&String> = all_files
        .iter()
        .filter(|f| !ignored_files.contains(f))
        .collect();

    // ── Diff stats ────────────────────────────────────────────────────────────
    let total_lines = filtered_diff.lines().count();
    let added_lines = filtered_diff
        .lines()
        .filter(|l| l.starts_with('+') && !l.starts_with("+++"))
        .count();

    // ── Layer 1 scan ──────────────────────────────────────────────────────────
    let findings = if filtered_diff.trim().is_empty() {
        vec![]
    } else {
        ast_validator::scan_findings(&filtered_diff)
    };

    let blocked = !findings.is_empty();

    // ── JSON output ───────────────────────────────────────────────────────────
    let result = serde_json::json!({
        "blocked":       blocked,
        "blocked_by":    if blocked { serde_json::json!("layer1") } else { serde_json::Value::Null },
        "base":          base,
        "head":          head,
        "findings":      findings.iter().map(|l| serde_json::json!({ "label": l })).collect::<Vec<_>>(),
        "files_scanned": scanned_files,
        "files_ignored": ignored_files,
        "diff_stats": {
            "total_lines": total_lines,
            "added_lines": added_lines,
        },
    });

    println!("{}", serde_json::to_string_pretty(&result)?);
    std::process::exit(if blocked { 1 } else { 0 });
}
