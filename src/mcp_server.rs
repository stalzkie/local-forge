use anyhow::Result;
use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpListener;

// ── JSON-RPC 2.0 request shape ────────────────────────────────────────────────

#[derive(Deserialize, Debug)]
struct McpRequest {
    jsonrpc: String,
    method: String,
    params: McpParams,
    id: serde_json::Value,
}

#[derive(Deserialize, Debug)]
struct McpParams {
    file_path: String,
    staged_diff_content: String,
}

// ── JSON-RPC 2.0 response shapes ──────────────────────────────────────────────

#[derive(Serialize)]
struct McpResponse {
    jsonrpc: &'static str,
    result: McpResult,
    id: serde_json::Value,
}

#[derive(Serialize)]
struct McpResult {
    compliance_status: &'static str,
    blocked: bool,
    blocked_by: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    layer2_score: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    advisory: Option<AdvisoryPayload>,
    file_path: String,
}

#[derive(Serialize)]
struct AdvisoryPayload {
    severity:    String,
    summary:     String,
    findings:    Vec<FindingPayload>,
    report_path: String,
}

#[derive(Serialize)]
struct FindingPayload {
    r#type:      String,
    line_hint:   String,
    explanation: String,
    remediation: String,
}

#[derive(Serialize)]
struct McpErrorResponse {
    jsonrpc: &'static str,
    error: McpError,
    id: serde_json::Value,
}

#[derive(Serialize)]
struct McpError {
    code: i32,
    message: String,
}

// ── Public entry point ────────────────────────────────────────────────────────

pub async fn run(port: u16) -> Result<()> {
    let addr = format!("127.0.0.1:{port}");
    let listener = TcpListener::bind(&addr).await?;
    println!("[MCP] JSON-RPC 2.0 server listening on {addr}");
    println!("[MCP] Supported methods: scan, ping");

    loop {
        let (socket, peer) = listener.accept().await?;
        println!("[MCP] Connection accepted from {peer}");
        tokio::spawn(async move {
            if let Err(e) = handle_connection(socket).await {
                eprintln!("[MCP] Connection error from {peer}: {e}");
            }
            println!("[MCP] Connection closed: {peer}");
        });
    }
}

// ── Per-connection handler ────────────────────────────────────────────────────

async fn handle_connection(socket: tokio::net::TcpStream) -> Result<()> {
    let (reader, mut writer) = socket.into_split();
    let mut lines = BufReader::new(reader).lines();

    while let Ok(Some(line)) = lines.next_line().await {
        let line = line.trim().to_string();
        if line.is_empty() { continue; }

        let response = handle_message(line).await;
        writer.write_all(response.as_bytes()).await?;
        writer.write_all(b"\n").await?;
        writer.flush().await?;
    }
    Ok(())
}

// ── Message dispatch ──────────────────────────────────────────────────────────

async fn handle_message(raw: String) -> String {
    let req: McpRequest = match serde_json::from_str(&raw) {
        Ok(r) => r,
        Err(e) => {
            let err = McpErrorResponse {
                jsonrpc: "2.0",
                error: McpError { code: -32700, message: format!("Parse error: {e}") },
                id: serde_json::Value::Null,
            };
            return serde_json::to_string(&err).unwrap();
        }
    };

    if req.jsonrpc != "2.0" {
        let err = McpErrorResponse {
            jsonrpc: "2.0",
            error: McpError { code: -32600, message: "jsonrpc must be \"2.0\"".into() },
            id: req.id,
        };
        return serde_json::to_string(&err).unwrap();
    }

    match req.method.as_str() {
        "scan" => handle_scan(req).await,
        "ping" => handle_ping(req),
        other  => {
            let err = McpErrorResponse {
                jsonrpc: "2.0",
                error: McpError { code: -32601, message: format!("Method not found: {other}") },
                id: req.id,
            };
            serde_json::to_string(&err).unwrap()
        }
    }
}

// ── Method: scan (runs all 3 layers) ─────────────────────────────────────────

async fn handle_scan(req: McpRequest) -> String {
    let diff = &req.params.staged_diff_content;

    // Layer 1: AST regex
    if crate::ast_validator::scan(diff) {
        eprintln!("[MCP] scan — file: {}  blocked_by: layer1", req.params.file_path);
        let advisory_handle = crate::advisory_engine::spawn(diff.clone());
        let advisory = crate::advisory_engine::await_with_timeout(advisory_handle, 30).await
            .map(|r| advisory_to_payload(&r));

        let response = McpResponse {
            jsonrpc: "2.0",
            result: McpResult {
                compliance_status: "Blocked",
                blocked: true,
                blocked_by: "layer1_ast",
                reason: Some("High-entropy secret detected by AST validator".into()),
                layer2_score: None,
                advisory,
                file_path: req.params.file_path,
            },
            id: req.id,
        };
        return serde_json::to_string(&response).unwrap();
    }

    // Layer 2: CoreML classifier
    let (layer2_blocked, layer2_score) = match crate::ane_bridge::analyse(diff) {
        Ok(Some(r)) => (r.risk_label == 1, Some(r.risk_score)),
        _           => (false, None),
    };

    if layer2_blocked {
        eprintln!("[MCP] scan — file: {}  blocked_by: layer2  score: {:?}", req.params.file_path, layer2_score);
        let advisory_handle = crate::advisory_engine::spawn(diff.clone());
        let advisory = crate::advisory_engine::await_with_timeout(advisory_handle, 30).await
            .map(|r| advisory_to_payload(&r));

        let response = McpResponse {
            jsonrpc: "2.0",
            result: McpResult {
                compliance_status: "Blocked",
                blocked: true,
                blocked_by: "layer2_coreml",
                reason: Some("CoreML classifier flagged high-risk pattern".into()),
                layer2_score,
                advisory,
                file_path: req.params.file_path,
            },
            id: req.id,
        };
        return serde_json::to_string(&response).unwrap();
    }

    // Layer 3: Qwen advisory (async, never blocks)
    eprintln!("[MCP] scan — file: {}  layers 1&2 clean, running Qwen advisory", req.params.file_path);
    let advisory_handle = crate::advisory_engine::spawn(diff.clone());
    let advisory = crate::advisory_engine::await_with_timeout(advisory_handle, 30).await
        .map(|r| advisory_to_payload(&r));

    let response = McpResponse {
        jsonrpc: "2.0",
        result: McpResult {
            compliance_status: "Clean",
            blocked: false,
            blocked_by: "none",
            reason: None,
            layer2_score,
            advisory,
            file_path: req.params.file_path,
        },
        id: req.id,
    };
    serde_json::to_string(&response).unwrap()
}

fn advisory_to_payload(r: &crate::advisory_engine::AdvisoryResult) -> AdvisoryPayload {
    AdvisoryPayload {
        severity:    r.severity.label().to_string(),
        summary:     r.summary.clone(),
        report_path: r.report_path.clone(),
        findings: r.findings.iter().map(|f| FindingPayload {
            r#type:      f.r#type.clone(),
            line_hint:   f.line_hint.clone(),
            explanation: f.explanation.clone(),
            remediation: f.remediation.clone(),
        }).collect(),
    }
}

// ── Method: ping ─────────────────────────────────────────────────────────────

fn handle_ping(req: McpRequest) -> String {
    #[derive(Serialize)]
    struct PingResult  { status: &'static str, version: &'static str }
    #[derive(Serialize)]
    struct PingResponse { jsonrpc: &'static str, result: PingResult, id: serde_json::Value }

    serde_json::to_string(&PingResponse {
        jsonrpc: "2.0",
        result: PingResult { status: "ok", version: "2.0.0" },
        id: req.id,
    }).unwrap()
}

// ── Unit tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    async fn send(payload: serde_json::Value) -> serde_json::Value {
        let raw = serde_json::to_string(&payload).unwrap();
        let resp = handle_message(raw).await;
        serde_json::from_str(&resp).unwrap()
    }

    #[tokio::test]
    async fn scan_blocked_layer1() {
        let resp = send(serde_json::json!({
            "jsonrpc": "2.0", "method": "scan", "id": 1,
            "params": {"file_path": "f.py", "staged_diff_content": "AKIAIIIIIIIIIIIIIIII"}
        })).await;
        assert_eq!(resp["result"]["blocked"], true);
        assert_eq!(resp["result"]["blocked_by"], "layer1_ast");
    }

    #[tokio::test]
    async fn scan_clean_passes() {
        let resp = send(serde_json::json!({
            "jsonrpc": "2.0", "method": "scan", "id": 2,
            "params": {"file_path": "f.rs", "staged_diff_content": "fn main() {}"}
        })).await;
        assert_eq!(resp["result"]["blocked"], false);
    }

    #[tokio::test]
    async fn ping_returns_ok() {
        let resp = send(serde_json::json!({
            "jsonrpc": "2.0", "method": "ping", "id": 99,
            "params": {"file_path": "", "staged_diff_content": ""}
        })).await;
        assert_eq!(resp["result"]["status"], "ok");
    }

    #[tokio::test]
    async fn unknown_method_error() {
        let resp = send(serde_json::json!({
            "jsonrpc": "2.0", "method": "explode", "id": 3,
            "params": {"file_path": "", "staged_diff_content": ""}
        })).await;
        assert_eq!(resp["error"]["code"], -32601);
    }

    #[tokio::test]
    async fn malformed_json_error() {
        let resp: serde_json::Value =
            serde_json::from_str(&handle_message("not json {{".to_string()).await).unwrap();
        assert_eq!(resp["error"]["code"], -32700);
    }
}
