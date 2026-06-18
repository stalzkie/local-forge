use std::path::PathBuf;
use std::process::Command;

/// Result from the ANE inference shim.
pub struct AneResult {
    pub risk_score: f32,
    pub risk_label: u8,        // 0 = clean, 1 = risky
    pub advisory: Option<String>,
}

/// Run the CoreML model on `diff` via the Python inference shim.
///
/// Returns Ok(None) if the model artifacts are not built yet (non-fatal —
/// the AST validator already ran). Returns Ok(Some(result)) otherwise.
/// Returns Err only on unexpected subprocess failure.
pub fn analyse(diff: &str) -> anyhow::Result<Option<AneResult>> {
    let shim = resolve_shim_path()?;

    if !shim.exists() {
        return Ok(None);
    }

    let model_path = shim.parent().unwrap().join("LocalForgeModel.mlpackage");
    if !model_path.exists() {
        eprintln!(
            "[ANE] Model not built yet. Run: python3 coreml/build_model.py"
        );
        return Ok(None);
    }

    let output = Command::new("python3")
        .arg(&shim)
        .arg(diff)
        .output()?;

    // Exit codes: 0 = clean, 2 = risky, 1 = internal error
    if output.status.code() == Some(1) {
        let stderr = String::from_utf8_lossy(&output.stderr);
        eprintln!("[ANE] Shim error: {stderr}");
        return Ok(None);
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let trimmed = stdout.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }

    let json: serde_json::Value = serde_json::from_str(trimmed)?;

    let risk_score = json["risk_score"].as_f64().unwrap_or(0.0) as f32;
    let risk_label = json["risk_label"].as_u64().unwrap_or(0) as u8;
    let advisory   = json["advisory"].as_str().map(|s| s.to_string());

    Ok(Some(AneResult { risk_score, risk_label, advisory }))
}

/// Resolve coreml/infer.py relative to the running binary's location,
/// falling back to the current working directory.
fn resolve_shim_path() -> anyhow::Result<PathBuf> {
    // When running from the project root (dev or hook context)
    let cwd_shim = PathBuf::from("coreml/infer.py");
    if cwd_shim.exists() {
        return Ok(cwd_shim);
    }

    // When running as an installed binary, look two levels up from the binary
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
            let candidate = parent.join("coreml/infer.py");
            if candidate.exists() {
                return Ok(candidate);
            }
        }
    }

    Ok(cwd_shim) // return cwd path even if absent — caller checks .exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn returns_none_gracefully_when_model_absent() {
        // When run from a directory without coreml/infer.py the bridge
        // returns Ok(None) rather than panicking or erroring.
        let tmp = std::env::temp_dir();
        let original = std::env::current_dir().unwrap();
        std::env::set_current_dir(&tmp).unwrap();
        let result = analyse("fn main() {}");
        std::env::set_current_dir(original).unwrap();
        assert!(result.is_ok());
    }
}
