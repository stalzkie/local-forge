mod ane_bridge;
mod ast_validator;
mod mcp_server;
mod tui;

use clap::Parser;
use std::io::Read;

#[derive(Parser)]
#[command(name = "localforge", version = "2.0.0", about = "LocalForge Security Shield")]
struct Cli {
    /// Read a staged diff from stdin and exit with code 1 if a secret is detected
    #[arg(long)]
    scan: bool,

    /// Start the MCP JSON-RPC server on the given port
    #[arg(long)]
    mcp_port: Option<u16>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    if cli.scan {
        let mut input = String::new();
        std::io::stdin().read_to_string(&mut input)?;

        // Phase 2: deterministic AST/regex scan — blocks immediately if hit
        if ast_validator::scan(&input) {
            std::process::exit(1);
        }

        // Phase 4: ANE semantic analysis — advisory layer after regex passes
        match ane_bridge::analyse(&input) {
            Ok(Some(result)) if result.risk_label == 1 => {
                if let Some(advisory) = &result.advisory {
                    eprintln!("[LocalForge] ANE ADVISORY — {advisory}");
                }
                eprintln!(
                    "[LocalForge] ANE risk score: {:.3} — commit blocked by semantic analysis.",
                    result.risk_score
                );
                std::process::exit(1);
            }
            Ok(Some(result)) => {
                eprintln!(
                    "[LocalForge] ANE score: {:.3} — clean.",
                    result.risk_score
                );
            }
            Ok(None) => {
                // Model not built yet — non-fatal, AST scan already passed
            }
            Err(e) => {
                eprintln!("[LocalForge] ANE bridge error (non-fatal): {e}");
            }
        }

        std::process::exit(0);
    }

    if let Some(port) = cli.mcp_port {
        mcp_server::run(port).await?;
        return Ok(());
    }

    // Default: launch the TUI dashboard
    tui::run_dashboard()
}
