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
    id: serde_json::Value, // accept number or string per JSON-RPC spec
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
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    file_path: String,
    method: String,
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
        if line.is_empty() {
            continue;
        }

        let response_json = handle_message(&line);
        writer.write_all(response_json.as_bytes()).await?;
        writer.write_all(b"\n").await?;
        writer.flush().await?;
    }

    Ok(())
}

// ── Message dispatch ──────────────────────────────────────────────────────────

fn handle_message(raw: &str) -> String {
    // Parse the incoming JSON — return a JSON-RPC error if malformed
    let req: McpRequest = match serde_json::from_str(raw) {
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

    // Validate jsonrpc version
    if req.jsonrpc != "2.0" {
        let err = McpErrorResponse {
            jsonrpc: "2.0",
            error: McpError { code: -32600, message: "Invalid Request: jsonrpc must be \"2.0\"".into() },
            id: req.id,
        };
        return serde_json::to_string(&err).unwrap();
    }

    match req.method.as_str() {
        "scan" => handle_scan(req),
        "ping" => handle_ping(req),
        other => {
            let err = McpErrorResponse {
                jsonrpc: "2.0",
                error: McpError {
                    code: -32601,
                    message: format!("Method not found: {other}"),
                },
                id: req.id,
            };
            serde_json::to_string(&err).unwrap()
        }
    }
}

// ── Method: scan ─────────────────────────────────────────────────────────────

fn handle_scan(req: McpRequest) -> String {
    let blocked = crate::ast_validator::scan(&req.params.staged_diff_content);

    eprintln!(
        "[MCP] scan — file: {}  blocked: {}",
        req.params.file_path, blocked
    );

    let response = McpResponse {
        jsonrpc: "2.0",
        result: McpResult {
            compliance_status: if blocked { "Blocked" } else { "Clean" },
            blocked,
            reason: if blocked {
                Some("High-entropy secret detected by AST validator".into())
            } else {
                None
            },
            file_path: req.params.file_path,
            method: req.method,
        },
        id: req.id,
    };

    serde_json::to_string(&response).unwrap()
}

// ── Method: ping ─────────────────────────────────────────────────────────────

fn handle_ping(req: McpRequest) -> String {
    #[derive(Serialize)]
    struct PingResult { status: &'static str, version: &'static str }

    #[derive(Serialize)]
    struct PingResponse { jsonrpc: &'static str, result: PingResult, id: serde_json::Value }

    let response = PingResponse {
        jsonrpc: "2.0",
        result: PingResult { status: "ok", version: "2.0.0" },
        id: req.id,
    };
    serde_json::to_string(&response).unwrap()
}

// ── Unit tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn scan_request(diff: &str, id: i64) -> String {
        format!(
            r#"{{"jsonrpc":"2.0","method":"scan","params":{{"file_path":"test.py","staged_diff_content":"{diff}"}},"id":{id}}}"#
        )
    }

    #[test]
    fn scan_blocked_returns_blocked_true() {
        let raw = scan_request("aws_token = AKIAIOSFODNN7EXAMPLE", 1);
        let resp: serde_json::Value = serde_json::from_str(&handle_message(&raw)).unwrap();
        assert_eq!(resp["result"]["blocked"], true);
        assert_eq!(resp["result"]["compliance_status"], "Blocked");
        assert_eq!(resp["id"], 1);
    }

    #[test]
    fn scan_clean_returns_blocked_false() {
        let raw = scan_request("fn main() {}", 2);
        let resp: serde_json::Value = serde_json::from_str(&handle_message(&raw)).unwrap();
        assert_eq!(resp["result"]["blocked"], false);
        assert_eq!(resp["result"]["compliance_status"], "Clean");
        assert!(resp["result"]["reason"].is_null());
    }

    #[test]
    fn ping_returns_ok() {
        let raw = r#"{"jsonrpc":"2.0","method":"ping","params":{"file_path":"","staged_diff_content":""},"id":99}"#;
        let resp: serde_json::Value = serde_json::from_str(&handle_message(raw)).unwrap();
        assert_eq!(resp["result"]["status"], "ok");
        assert_eq!(resp["id"], 99);
    }

    #[test]
    fn unknown_method_returns_error() {
        let raw = r#"{"jsonrpc":"2.0","method":"explode","params":{"file_path":"","staged_diff_content":""},"id":3}"#;
        let resp: serde_json::Value = serde_json::from_str(&handle_message(raw)).unwrap();
        assert_eq!(resp["error"]["code"], -32601);
    }

    #[test]
    fn malformed_json_returns_parse_error() {
        let resp: serde_json::Value = serde_json::from_str(&handle_message("not json {{")).unwrap();
        assert_eq!(resp["error"]["code"], -32700);
    }

    #[test]
    fn wrong_jsonrpc_version_returns_invalid_request() {
        let raw = r#"{"jsonrpc":"1.0","method":"ping","params":{"file_path":"","staged_diff_content":""},"id":4}"#;
        let resp: serde_json::Value = serde_json::from_str(&handle_message(raw)).unwrap();
        assert_eq!(resp["error"]["code"], -32600);
    }
}
