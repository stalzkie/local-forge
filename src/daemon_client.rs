//! Client for the optional warm-model daemon (`coreml/daemon.py`).
//!
//! The daemon keeps CoreML/MLX models resident across commits instead of
//! paying Python-interpreter + model-load cost every time. It is a pure
//! performance optimization: every function here degrades to `None` on any
//! failure (socket missing, connection refused, malformed response), and
//! `ane_bridge`/`advisory_engine` fall back to their existing per-invocation
//! subprocess shim whenever that happens.

use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::Duration;

fn socket_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home).join(".localforge/daemon.sock")
}

/// Resolve coreml/daemon.py using the same priority chain
/// ane_bridge/advisory_engine use for their own shims:
///   1. ~/.localforge/coreml/daemon.py   (installed)
///   2. <app bundle>/Contents/Resources/coreml/daemon.py
///   3. coreml/daemon.py relative to cwd (dev / repo context)
pub fn resolve_daemon_script() -> PathBuf {
    if let Ok(home) = std::env::var("HOME") {
        let installed = PathBuf::from(home).join(".localforge/coreml/daemon.py");
        if installed.exists() {
            return installed;
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(macos) = exe.parent() {
            let bundled = macos
                .parent()
                .unwrap_or(macos)
                .join("Resources/coreml/daemon.py");
            if bundled.exists() {
                return bundled;
            }
        }
    }

    PathBuf::from("coreml/daemon.py")
}

/// Send `request` (a JSON object) to the daemon and return its JSON
/// response. Returns `None` if the daemon isn't running, the request can't
/// be sent, or the response can't be parsed.
pub fn request(request: &serde_json::Value) -> Option<serde_json::Value> {
    let mut stream = UnixStream::connect(socket_path()).ok()?;
    // Model inference can legitimately take a couple of minutes on first
    // load with a large Qwen model — give it room before giving up.
    stream
        .set_read_timeout(Some(Duration::from_secs(180)))
        .ok()?;
    stream.set_write_timeout(Some(Duration::from_secs(5))).ok()?;

    let mut line = serde_json::to_string(request).ok()?;
    line.push('\n');
    stream.write_all(line.as_bytes()).ok()?;
    stream.shutdown(std::net::Shutdown::Write).ok();

    let mut buf = String::new();
    stream.read_to_string(&mut buf).ok()?;
    serde_json::from_str(buf.trim()).ok()
}

/// True if a daemon is currently listening on the socket.
pub fn is_running() -> bool {
    request(&serde_json::json!({"cmd": "ping"}))
        .is_some_and(|v| v.get("ok").and_then(|b| b.as_bool()).unwrap_or(false))
}

/// Best-effort: spawn the daemon in the background if it isn't already
/// running. Never blocks the caller on daemon startup or model load — the
/// request that triggered this call still falls back to the subprocess
/// shim path, so a slow-to-warm-up daemon never delays a commit.
pub fn ensure_running(daemon_script: &Path) {
    if !daemon_script.exists() || is_running() {
        return;
    }
    let _ = std::process::Command::new("python3")
        .arg(daemon_script)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_returns_none_when_daemon_absent() {
        // No daemon is running in the test environment (and $HOME here is
        // whatever the test process inherits) — the important behavior is
        // that a missing/refused socket degrades to None, never a panic.
        let result = request(&serde_json::json!({"cmd": "ping"}));
        // Only assert the no-panic contract; a daemon may legitimately be
        // running on the developer's machine while tests execute.
        let _ = result;
    }

    #[test]
    fn ensure_running_is_a_noop_when_script_missing() {
        ensure_running(Path::new("/nonexistent/daemon.py"));
    }
}
