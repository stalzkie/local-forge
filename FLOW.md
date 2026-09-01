# LocalForge Flow

```mermaid
flowchart TD
    A[git commit] --> B[hooks/pre-commit]
    B --> C[localforge --scan\nstdin: staged diff]

    C --> D{Layer 1\nast_validator::scan\nregex on + lines}
    D -- match --> D1[BLOCK\nexit 1]
    D1 --> D2[spawn Layer 3 advisory\nasync, best-effort]

    D -- clean --> E{Layer 2\nane_bridge::analyse\nCoreML via ANE}
    E -- risk_label = 1 --> E1[BLOCK\nexit 1]
    E -- clean / error --> F[spawn Layer 3 advisory]

    E1 --> F2[await advisory ≤30s]
    F2 --> G1[print advisory if ready]
    G1 --> H1[exit 1]

    F --> F3[await advisory ≤30s]
    F3 --> G2[print advisory if ready]
    G2 --> H2[exit 0\nnever blocks]

    D2 -.-> R[(consolidated report\n~/.localforge/reports/)]
    G1 -.-> R
    G2 -.-> R

    R --> M[TUI / Monitor\nlocalforge --monitor\nSwiftUI app]
    C -.-> MCP[localforge --mcp-port\nJSON-RPC 2.0 server]
```

## Layers

| Layer | Module | Cost | Blocks? |
|---|---|---|---|
| 1 — AST regex | `ast_validator.rs` | <1 ms | Yes |
| 2 — CoreML classifier | `ane_bridge.rs` (ANE) | ~200 ms | Yes |
| 3 — Qwen advisory | `advisory_engine.rs` (MLX) | ~5–10 s, async | Never |

## Key points

- Only Layer 1 and Layer 2 can fail the commit (`exit 1`). Layer 3 is advisory-only and runs in the background regardless of the outcome of Layers 1/2.
- Layer 3 is spawned as soon as a decision path is known, so inference overlaps with the exit-code decision instead of adding latency serially.
- Every Layer 3 run writes one consolidated report per commit to `~/.localforge/reports/`, never one file per finding.
- The Swift TUI (`tui/`) and the SwiftUI macOS app both read from the same report/log stream produced by this pipeline — they observe, they don't participate in the block decision.
- `localforge --mcp-port <PORT>` exposes the same engine over JSON-RPC 2.0 for external tooling, independent of the git-hook path.
