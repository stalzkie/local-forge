# Security Policy

## Supported Versions

Only the latest release of LocalForge receives security fixes.

| Version | Supported |
|---------|-----------|
| 2.1.x (latest) | ✓ |
| < 2.1 | ✗ |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report security issues by emailing **dstalingrad@gmail.com** with the subject line `[LocalForge Security]`. You should receive a response within **72 hours**. If you do not, follow up to ensure the original message was received.

Include as much of the following as possible:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- The LocalForge version affected (`localforge --version`)
- Your macOS version and Apple Silicon chip model

You are welcome to suggest a fix in your report. We will credit you in the release notes unless you prefer to remain anonymous.

## What We Ask

- Give us reasonable time to investigate and release a fix before any public disclosure
- Do not access or modify data that does not belong to you
- Do not perform denial-of-service attacks

## Scope

LocalForge is a **fully on-device tool** — no user code is ever transmitted to a remote server. The attack surface is therefore local:

**In scope:**
- Vulnerabilities in the Rust binary (`localforge`) that allow privilege escalation or arbitrary code execution
- The pre-commit hook executing unintended commands
- The MCP server (`--mcp-port`) accepting connections beyond `127.0.0.1`
- Path traversal or sandbox escape in diff scanning
- The advisory report file being written to an unintended path

**Out of scope:**
- Vulnerabilities in third-party models (Qwen, CoreML) — report those to their respective maintainers
- Issues requiring physical access to the machine
- Social engineering
- Theoretical vulnerabilities with no practical exploit path

## Security Design

- The MCP JSON-RPC server binds to `127.0.0.1` only — never exposed to the network
- `localforge --scan` reads from stdin only; it does not access the filesystem beyond `~/.localforge/`
- The pre-commit hook runs as the committing user — it does not use `sudo` or escalate privileges
- All three pipeline layers (Rust regex, CoreML, Qwen/MLX) run entirely on-device
- No telemetry, no analytics, no network requests
