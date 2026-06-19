use serde::Deserialize;
use std::path::PathBuf;
use tokio::process::Command;

// ── Public types ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum Severity {
    High,
    Medium,
    Low,
    Clean,
    Unknown,
}

impl Severity {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "high"   => Self::High,
            "medium" => Self::Medium,
            "low"    => Self::Low,
            "clean"  => Self::Clean,
            _        => Self::Unknown,
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            Self::High    => "HIGH",
            Self::Medium  => "MEDIUM",
            Self::Low     => "LOW",
            Self::Clean   => "CLEAN",
            Self::Unknown => "UNKNOWN",
        }
    }

    pub fn is_actionable(&self) -> bool {
        matches!(self, Self::High | Self::Medium)
    }
}

#[derive(Debug, Deserialize, Clone)]
pub struct Finding {
    pub category:     Option<String>, // "security" | "quality" | "bug_risk"
    pub r#type:       String,
    pub line_hint:    String,
    pub explanation:  String,
    pub remediation:  String,
}

#[derive(Debug, Clone)]
pub struct AdvisoryResult {
    pub severity:    Severity,
    pub summary:     String,
    pub findings:    Vec<Finding>,
    pub report_path: String,
}

// ── Public API ────────────────────────────────────────────────────────────────

/// Spawn the Qwen advisory engine as a non-blocking background task.
/// Returns a JoinHandle — the caller awaits it only if it wants to display
/// the result; the commit is never blocked waiting for this.
pub fn spawn(diff: String) -> tokio::task::JoinHandle<Option<AdvisoryResult>> {
    tokio::spawn(async move { run_advisory(&diff).await })
}

/// Await the result of a previously spawned advisory task with a timeout.
/// Returns None if the model isn't built, times out, or errors.
pub async fn await_with_timeout(
    handle: tokio::task::JoinHandle<Option<AdvisoryResult>>,
    timeout_secs: u64,
) -> Option<AdvisoryResult> {
    match tokio::time::timeout(
        std::time::Duration::from_secs(timeout_secs),
        handle,
    )
    .await
    {
        Ok(Ok(result)) => result,
        Ok(Err(e))     => { eprintln!("[Advisory] Task panicked: {e}"); None }
        Err(_)         => { eprintln!("[Advisory] Timed out after {timeout_secs}s"); None }
    }
}

// ── Internal ──────────────────────────────────────────────────────────────────

async fn run_advisory(diff: &str) -> Option<AdvisoryResult> {
    let shim = resolve_shim_path();
    if !shim.exists() {
        return None;
    }

    let log_dir    = resolve_log_dir();
    let report_file = resolve_report_path(diff);

    let output = Command::new("python3")
        .arg(&shim)
        .arg(diff)
        .arg("--log-dir")
        .arg(&log_dir)
        .arg("--report-file")
        .arg(&report_file)
        .output()
        .await
        .ok()?;

    if !output.status.success() && output.stdout.is_empty() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        eprintln!("[Advisory] Shim error: {stderr}");
        return None;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let trimmed = stdout.trim();
    if trimmed.is_empty() {
        return None;
    }

    // Parse the JSON line emitted by advisory.py
    let json: serde_json::Value = serde_json::from_str(trimmed).ok()?;

    // Check for error key
    if let Some(err) = json.get("error") {
        eprintln!("[Advisory] Script error: {err}");
        return None;
    }

    let severity = Severity::from_str(
        json["severity"].as_str().unwrap_or("unknown")
    );
    let summary     = json["summary"].as_str().unwrap_or("").to_string();
    let report_path = json["report_path"].as_str().unwrap_or("").to_string();
    let findings: Vec<Finding> = serde_json::from_value(
        json["findings"].clone()
    ).unwrap_or_default();

    Some(AdvisoryResult { severity, summary, findings, report_path })
}

fn resolve_shim_path() -> PathBuf {
    // 1. Canonical installed location
    if let Ok(home) = std::env::var("HOME") {
        let installed = PathBuf::from(home).join(".localforge/coreml/advisory.py");
        if installed.exists() { return installed; }
    }

    // 2. App bundle Resources
    if let Ok(exe) = std::env::current_exe() {
        if let Some(macos) = exe.parent() {
            let bundled = macos
                .parent().unwrap_or(macos)
                .join("Resources/coreml/advisory.py");
            if bundled.exists() { return bundled; }
        }
    }

    // 3. Repo-relative (dev context)
    let cwd = PathBuf::from("coreml/advisory.py");
    if cwd.exists() { return cwd; }

    // 4. Legacy: two levels up from the binary
    if let Ok(exe) = std::env::current_exe() {
        if let Some(p) = exe.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
            let candidate = p.join("coreml/advisory.py");
            if candidate.exists() { return candidate; }
        }
    }
    cwd
}

fn resolve_log_dir() -> PathBuf {
    dirs_or_home().join(".localforge").join("reports")
}

fn resolve_report_path(diff: &str) -> PathBuf {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    let mut h = DefaultHasher::new();
    diff.hash(&mut h);
    let hash = format!("{:x}", h.finish());
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    dirs_or_home()
        .join(".localforge")
        .join("reports")
        .join(format!("commit_{ts}_{}.txt", &hash[..8]))
}

fn dirs_or_home() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/tmp"))
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn severity_parsing() {
        assert_eq!(Severity::from_str("high"),   Severity::High);
        assert_eq!(Severity::from_str("HIGH"),   Severity::High);
        assert_eq!(Severity::from_str("medium"), Severity::Medium);
        assert_eq!(Severity::from_str("clean"),  Severity::Clean);
        assert_eq!(Severity::from_str("???"),    Severity::Unknown);
    }

    #[test]
    fn severity_actionable() {
        assert!(Severity::High.is_actionable());
        assert!(Severity::Medium.is_actionable());
        assert!(!Severity::Low.is_actionable());
        assert!(!Severity::Clean.is_actionable());
    }

    #[tokio::test]
    async fn returns_none_when_shim_absent() {
        let tmp = std::env::temp_dir();
        let original = std::env::current_dir().unwrap();
        std::env::set_current_dir(&tmp).unwrap();
        let result = run_advisory("fn main() {}").await;
        std::env::set_current_dir(original).unwrap();
        assert!(result.is_none());
    }
}
