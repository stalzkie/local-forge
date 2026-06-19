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

// ── Installation ──────────────────────────────────────────────────────────────

fn run_install(repo_path: &str) -> anyhow::Result<()> {
    use std::fs;
    use std::path::PathBuf;

    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let lf_dir   = PathBuf::from(&home).join(".localforge");
    let bin_dir  = lf_dir.join("bin");
    let coreml_dir = lf_dir.join("coreml");

    // ── 1. Create directory structure ─────────────────────────────────────────
    for dir in [&lf_dir, &bin_dir, &coreml_dir, &lf_dir.join("reports")] {
        fs::create_dir_all(dir)?;
    }

    // ── 2. Copy binary ────────────────────────────────────────────────────────
    let self_path = std::env::current_exe()?;
    let bin_dest  = bin_dir.join("localforge");
    fs::copy(&self_path, &bin_dest)?;
    // Make executable
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&bin_dest, fs::Permissions::from_mode(0o755))?;
    }
    println!("[LocalForge] ✓ Binary installed  → {}", bin_dest.display());

    // ── 3. Copy CoreML model ──────────────────────────────────────────────────
    // Search: next to binary (bundle Resources) → exe-relative → cwd-relative
    let model_dest = lf_dir.join("LocalForgeModel.mlpackage");
    let model_src = find_bundled_resource("LocalForgeModel.mlpackage");
    if let Some(src) = model_src {
        if model_dest.exists() { fs::remove_dir_all(&model_dest)?; }
        copy_dir_all(&src, &model_dest)?;
        println!("[LocalForge] ✓ CoreML model     → {}", model_dest.display());
    } else {
        println!("[LocalForge] ⚠ CoreML model not found. Build it with:");
        println!("             python3 coreml/build_model.py");
    }

    // ── 4. Copy Python shims ──────────────────────────────────────────────────
    for shim in ["infer.py", "advisory.py"] {
        if let Some(src) = find_bundled_resource(&format!("coreml/{shim}")) {
            let dest = coreml_dir.join(shim);
            fs::copy(&src, &dest)?;
            println!("[LocalForge] ✓ {shim:<14} → {}", dest.display());
        } else if let Some(src) = find_repo_resource(&format!("coreml/{shim}")) {
            let dest = coreml_dir.join(shim);
            fs::copy(&src, &dest)?;
            println!("[LocalForge] ✓ {shim:<14} → {}", dest.display());
        } else {
            println!("[LocalForge] ⚠ {shim} not found");
        }
    }

    // ── 5. Check Qwen model ───────────────────────────────────────────────────
    let qwen_dir = lf_dir.join("qwen2.5-coder-1.5b-4bit");
    if !qwen_dir.exists() {
        println!("[LocalForge] ⚠ Qwen model not found at {}", qwen_dir.display());
        println!("             Install with:");
        println!("               pip3 install mlx-lm");
        println!("               python3 -c \"from mlx_lm import load; load('Qwen/Qwen2.5-Coder-1.5B-Instruct-4bit')\"");
        println!("             Then move the model folder to: {}", qwen_dir.display());
    } else {
        println!("[LocalForge] ✓ Qwen model found  → {}", qwen_dir.display());
    }

    // ── 6. Install git hook ───────────────────────────────────────────────────
    let repo = std::path::Path::new(repo_path);
    let git_hooks = repo.join(".git/hooks");
    if !git_hooks.exists() {
        println!("[LocalForge] ⚠ Not a git repo: {} — skipping hook install", repo.display());
        println!("             Run inside a git repo or pass the path:");
        println!("             localforge --install /path/to/your/repo");
    } else {
        let hook_dest = git_hooks.join("pre-commit");
        let hook_src  = find_hook_source();
        if let Some(src) = hook_src {
            fs::copy(&src, &hook_dest)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&hook_dest, fs::Permissions::from_mode(0o755))?;
            }
            println!("[LocalForge] ✓ Hook installed   → {}", hook_dest.display());
        } else {
            println!("[LocalForge] ⚠ pre-commit hook source not found");
        }

        // Register repo
        let repos_file = lf_dir.join("repos");
        let abs_repo   = fs::canonicalize(repo).unwrap_or_else(|_| repo.to_path_buf());
        let abs_str    = abs_repo.to_string_lossy().to_string();
        let existing   = fs::read_to_string(&repos_file).unwrap_or_default();
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

fn run_uninstall(repo_path: &str) -> anyhow::Result<()> {
    use std::fs;
    use std::path::PathBuf;

    let home   = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    let lf_dir = PathBuf::from(&home).join(".localforge");

    // ── Remove hook from repo ─────────────────────────────────────────────────
    let repo     = std::path::Path::new(repo_path);
    let hook     = repo.join(".git/hooks/pre-commit");
    if hook.exists() {
        // Only remove if it's a LocalForge hook
        let content = fs::read_to_string(&hook).unwrap_or_default();
        if content.contains("LocalForge") {
            fs::remove_file(&hook)?;
            println!("[LocalForge] ✓ Hook removed from {}", hook.display());
        } else {
            println!("[LocalForge] ⚠ Hook at {} is not a LocalForge hook — skipping", hook.display());
        }
    }

    // ── Remove repo from registry ─────────────────────────────────────────────
    let repos_file = lf_dir.join("repos");
    if repos_file.exists() {
        let abs_repo = fs::canonicalize(repo).unwrap_or_else(|_| repo.to_path_buf());
        let abs_str  = abs_repo.to_string_lossy().to_string();
        let existing = fs::read_to_string(&repos_file).unwrap_or_default();
        let filtered: String = existing.lines()
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

    let home       = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
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
        let path  = std::path::Path::new(repo);
        let hook  = path.join(".git/hooks/pre-commit");
        let exists = path.exists();

        let hook_status = if !exists {
            "✗ path not found"
        } else if !hook.exists() {
            "⚠ hook missing — run: localforge --install"
        } else {
            let content = std::fs::read_to_string(&hook).unwrap_or_default();
            if content.contains("LocalForge") { "✓ hook active" } else { "⚠ hook replaced by another tool" }
        };

        println!("  {} — {}", repo, hook_status);
    }

    println!();
    Ok(())
}

// ── Install helpers ───────────────────────────────────────────────────────────

/// Find a resource by checking app bundle Resources, then repo-relative paths.
fn find_bundled_resource(relative: &str) -> Option<std::path::PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(macos) = exe.parent() {
            let candidate = macos
                .parent().unwrap_or(macos)
                .join("Resources")
                .join(relative);
            if candidate.exists() { return Some(candidate); }
        }
    }
    None
}

/// Find a resource relative to the repo root (two levels up from src/).
fn find_repo_resource(relative: &str) -> Option<std::path::PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        // target/release/localforge → go up to repo root
        if let Some(p) = exe.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
            let candidate = p.join(relative);
            if candidate.exists() { return Some(candidate); }
        }
    }
    // cwd-relative fallback
    let cwd = std::path::PathBuf::from(relative);
    if cwd.exists() { return Some(cwd); }
    None
}

/// Find the pre-commit hook source.
fn find_hook_source() -> Option<std::path::PathBuf> {
    // App bundle Resources/hooks/pre-commit
    if let Some(p) = find_bundled_resource("hooks/pre-commit") { return Some(p); }
    // Repo-relative
    if let Some(p) = find_repo_resource("hooks/pre-commit") { return Some(p); }
    None
}

/// Recursively copy a directory (used for .mlpackage which is a directory).
fn copy_dir_all(src: &std::path::Path, dst: &std::path::Path) -> anyhow::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let ty    = entry.file_type()?;
        if ty.is_dir() {
            copy_dir_all(&entry.path(), &dst.join(entry.file_name()))?;
        } else {
            std::fs::copy(entry.path(), dst.join(entry.file_name()))?;
        }
    }
    Ok(())
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
