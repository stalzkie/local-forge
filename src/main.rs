mod advisory_engine;
mod ane_bridge;
mod ast_validator;
mod mcp_server;
mod tui;

use clap::Parser;
use std::io::Read;

#[derive(Parser)]
#[command(name = "localforge", version = "2.0.0", about = "LocalForge Security Shield")]
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
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    if cli.scan {
        let mut diff = String::new();
        std::io::stdin().read_to_string(&mut diff)?;

        // ── Layer 1: Rust AST regex — deterministic, <1 ms ───────────────────
        if ast_validator::scan(&diff) {
            // Layer 1 hard-blocks — spawn Layer 3 advisory in background so
            // the developer still gets a Qwen report, but don't wait for it.
            let _ = advisory_engine::spawn(diff);
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
                eprintln!("[LocalForge] Layer 2 score: {:.3} — clean.", result.risk_score);
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
        Ok(None)    => println!("[LocalForge] Layer 2 (CoreML/ANE): model not found — skipping"),
        Err(e)      => println!("[LocalForge] Layer 2 (CoreML/ANE): unavailable ({e})"),
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
    let mut pos: u64 = std::fs::metadata(&log_path)
        .map(|m| m.len())
        .unwrap_or(0);

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

fn print_advisory(report: &advisory_engine::AdvisoryResult) {
    eprintln!(
        "[LocalForge] Qwen [{severity}] {summary}",
        severity = report.severity.label(),
        summary  = report.summary,
    );
    for (i, f) in report.findings.iter().enumerate() {
        let cat = f.category.as_deref().unwrap_or("general").to_uppercase();
        eprintln!(
            "[LocalForge]   [{cat}] Finding {n}: {t} — {exp}",
            n   = i + 1,
            t   = f.r#type,
            exp = f.explanation,
        );
        eprintln!("[LocalForge]   Fix: {}", f.remediation);
    }
    if !report.report_path.is_empty() {
        eprintln!("[LocalForge]   Full report: {}", report.report_path);
    }
}
