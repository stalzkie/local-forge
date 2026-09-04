use once_cell::sync::Lazy;
use regex::Regex;
use serde::Deserialize;

struct Rule {
    pattern: &'static str,
    label: &'static str,
}

const RULES: &[Rule] = &[
    // ── AWS ───────────────────────────────────────────────────────────────────
    Rule {
        pattern: r"AKIA[0-9A-Z]{16,}",
        label: "AWS Access Key ID",
    },
    Rule {
        pattern: r#"(?i)(aws_secret|secret_access_key)\s*[=:]\s*['"]?[A-Za-z0-9/+=]{40,}['"]?"#,
        label: "AWS Secret Access Key",
    },
    // ── GCP ───────────────────────────────────────────────────────────────────
    Rule {
        pattern: r#""type"\s*:\s*"service_account""#,
        label: "GCP Service Account JSON",
    },
    Rule {
        pattern: r"AIza[0-9A-Za-z\-_]{35,}",
        label: "GCP API Key",
    },
    // ── Azure ─────────────────────────────────────────────────────────────────
    Rule {
        pattern: r"(?i)(AccountKey|SharedAccessSignature)\s*=\s*[A-Za-z0-9+/=]{40,}",
        label: "Azure Storage Key / SAS Token",
    },
    // ── Stripe ────────────────────────────────────────────────────────────────
    Rule {
        pattern: r"sk_live_[0-9a-zA-Z]{24,}",
        label: "Stripe Live Secret Key",
    },
    Rule {
        pattern: r"rk_live_[0-9a-zA-Z]{24,}",
        label: "Stripe Live Restricted Key",
    },
    // ── GitHub ────────────────────────────────────────────────────────────────
    Rule {
        pattern: r"ghp_[A-Za-z0-9]{36,}",
        label: "GitHub PAT (classic)",
    },
    Rule {
        pattern: r"github_pat_[A-Za-z0-9_]{82,}",
        label: "GitHub Fine-Grained PAT",
    },
    Rule {
        pattern: r"ghs_[A-Za-z0-9]{36,}",
        label: "GitHub Actions Secret",
    },
    // ── Slack ─────────────────────────────────────────────────────────────────
    Rule {
        pattern: r"xox[bpars]-[0-9A-Za-z\-]{10,}",
        label: "Slack Token",
    },
    Rule {
        pattern: r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+",
        label: "Slack Webhook URL",
    },
    // ── Twilio ────────────────────────────────────────────────────────────────
    Rule {
        pattern: r"AC[0-9a-f]{32,}",
        label: "Twilio Account SID",
    },
    Rule {
        pattern: r"SK[0-9a-f]{32,}",
        label: "Twilio API Key",
    },
    // ── SendGrid ──────────────────────────────────────────────────────────────
    Rule {
        pattern: r"SG\.[A-Za-z0-9\-_]{22,}\.[A-Za-z0-9\-_]{43,}",
        label: "SendGrid API Key",
    },
    // ── npm / PyPI / HuggingFace / Anthropic / OpenAI ────────────────────────
    Rule {
        pattern: r"npm_[A-Za-z0-9]{36,}",
        label: "npm Access Token",
    },
    Rule {
        pattern: r"pypi-[A-Za-z0-9\-_]{40,}",
        label: "PyPI API Token",
    },
    Rule {
        pattern: r"hf_[A-Za-z0-9]{34,}",
        label: "HuggingFace API Token",
    },
    Rule {
        pattern: r"sk-ant-[A-Za-z0-9\-_]{40,}",
        label: "Anthropic API Key",
    },
    Rule {
        pattern: r"sk-[A-Za-z0-9]{48,}",
        label: "OpenAI API Key",
    },
    Rule {
        pattern: r"sk-proj-[A-Za-z0-9_\-]{20,}",
        label: "OpenAI Project API Key",
    },
    // ── Shopify ───────────────────────────────────────────────────────────────
    Rule {
        pattern: r"shpss_[A-Za-z0-9]{32}",
        label: "Shopify Shared Secret",
    },
    Rule {
        pattern: r"shpat_[A-Za-z0-9]{32}",
        label: "Shopify Access Token",
    },
    // ── Generic private keys ──────────────────────────────────────────────────
    Rule {
        pattern: r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY(?: BLOCK)?-----",
        label: "Private Key Block",
    },
    Rule {
        pattern: r"PuTTY-User-Key-File-[23]:",
        label: "PuTTY Private Key File",
    },
    // ── .env literal assignments (KEY=bare_secret_value) ─────────────────────
    // Matches lines like  SECRET_KEY=abc123longvalue  in .env file hunks.
    // Value must be 16+ alphanum chars (excludes $VAR references by char class).
    Rule {
        pattern: r#"(?i)(SECRET|PASSWORD|PASSWD|PWD|API_KEY|AUTH_TOKEN|CREDENTIAL)[A-Z0-9_]*\s*=\s*[A-Za-z0-9/+=_\-]{16,}"#,
        label: "Hardcoded Secret in .env Assignment",
    },
    // ── High-entropy bearer tokens (exclude docs / test fixtures) ────────────
    // Requires 60+ chars to reduce false positives on example tokens in comments.
    Rule {
        pattern: r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{60,}",
        label: "High-Entropy Bearer Token",
    },
];

static COMPILED: Lazy<Vec<(Regex, &'static str)>> = Lazy::new(|| {
    RULES
        .iter()
        .map(|r| {
            (
                Regex::new(r.pattern).expect("invalid regex in RULES"),
                r.label,
            )
        })
        .collect()
});

// ── Entropy-based fallback (novel/internal secret formats) ───────────────────
//
// The rules above only catch known provider formats. This is a last line of
// defense: flag an assignment to a secret-ish variable name whose value has
// high Shannon entropy, even when no dedicated rule recognizes its shape —
// catches internal token formats and new provider formats before someone has
// to hit the same gap that OpenAI's sk-proj- keys once left in this repo.
// Gated on variable name AND entropy AND a mixed character class so it does
// not fire on English words, numeric IDs, or env-var references.

static ENTROPY_CANDIDATE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?i)\b\w*(?:secret|token|password|passwd|api[_-]?key|credential|auth[_-]?key|access[_-]?key|private[_-]?key|signing[_-]?key|client[_-]?secret)\w*\s*[:=]\s*['"]?([A-Za-z0-9+/=_\-.]{20,})['"]?"#,
    )
    .expect("invalid entropy candidate regex")
});

/// Substrings that mark a captured value as an env-var reference or module
/// path rather than a literal secret — these can slip past the char-class
/// filter (e.g. `process.env.SECRET_KEY` is 23 letters/dots, no quotes).
const ENV_REF_MARKERS: &[&str] = &[
    "process.env",
    "os.environ",
    "os.getenv",
    "system.getenv",
    "std::env::var",
    "env[",
    "env.get",
];

fn shannon_entropy(s: &str) -> f64 {
    use std::collections::HashMap;
    let len = s.chars().count() as f64;
    if len == 0.0 {
        return 0.0;
    }
    let mut counts: HashMap<char, u32> = HashMap::new();
    for c in s.chars() {
        *counts.entry(c).or_insert(0) += 1;
    }
    counts
        .values()
        .map(|&count| {
            let p = f64::from(count) / len;
            -p * p.log2()
        })
        .sum()
}

/// True if `value` looks like a high-entropy secret rather than a word,
/// placeholder, numeric ID, or env-var reference.
fn is_high_entropy_secret(value: &str) -> bool {
    let lower = value.to_lowercase();
    if ENV_REF_MARKERS.iter().any(|m| lower.contains(m)) {
        return false;
    }

    // Require a mixed character class — plain words, numeric IDs, and
    // dotted paths rarely satisfy both letters AND digits.
    let has_digit = value.bytes().any(|b| b.is_ascii_digit());
    let has_alpha = value.bytes().any(|b| b.is_ascii_alphabetic());
    if !has_digit || !has_alpha {
        return false;
    }

    // Hex strings max out at 4 bits/char (vs ~6 for base64), so they need a
    // lower absolute threshold to register as "high entropy" at all.
    let is_hex = value.bytes().all(|b| b.is_ascii_hexdigit());
    let bits_per_char = shannon_entropy(value);

    if is_hex {
        bits_per_char > 3.0
    } else {
        bits_per_char > 4.0
    }
}

/// True if `target` contains any secret-ish assignment whose value scores as
/// high entropy under `is_high_entropy_secret`.
fn scan_entropy_fallback(target: &str) -> bool {
    ENTROPY_CANDIDATE
        .captures_iter(target)
        .filter_map(|caps| caps.get(1))
        .any(|m| is_high_entropy_secret(m.as_str()))
}

// ── Custom patterns (.localforge/patterns.toml) ───────────────────────────────

#[derive(Deserialize)]
struct PatternsFile {
    #[serde(default)]
    patterns: Vec<CustomRule>,
}

#[derive(Deserialize)]
struct CustomRule {
    pattern: String,
    label: String,
}

/// Load user-defined patterns from `.localforge/patterns.toml` in the current
/// working directory (which is always the repo root when invoked by the hook).
/// Returns an empty vec if the file does not exist — not an error.
fn load_custom_patterns() -> Vec<(Regex, String)> {
    let path = std::path::Path::new(".localforge/patterns.toml");
    if !path.exists() {
        return vec![];
    }
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[LocalForge] WARNING: could not read .localforge/patterns.toml: {e}");
            return vec![];
        }
    };
    let file: PatternsFile = match toml::from_str(&content) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("[LocalForge] WARNING: failed to parse .localforge/patterns.toml: {e}");
            return vec![];
        }
    };
    file.patterns
        .into_iter()
        .filter_map(|r| match Regex::new(&r.pattern) {
            Ok(re) => Some((re, r.label)),
            Err(e) => {
                eprintln!(
                    "[LocalForge] WARNING: invalid custom pattern {:?}: {e}",
                    r.pattern
                );
                None
            }
        })
        .collect()
}

// ── Public API ────────────────────────────────────────────────────────────────

/// Scan `diff` against all built-in and custom patterns.
/// Returns the matched labels — empty means clean.
/// Only `+` lines (added lines) are tested; `-` lines are never scanned.
pub fn scan_findings(diff: &str) -> Vec<String> {
    let target: String = {
        let added: Vec<&str> = diff
            .lines()
            .filter(|l| l.starts_with('+') && !l.starts_with("+++"))
            .collect();
        if added.is_empty() {
            diff.to_string()
        } else {
            added.join("\n")
        }
    };

    let mut findings = Vec::new();

    for (re, label) in COMPILED.iter() {
        if re.is_match(&target) {
            findings.push(label.to_string());
        }
    }

    for (re, label) in load_custom_patterns() {
        if re.is_match(&target) {
            findings.push(label);
        }
    }

    if scan_entropy_fallback(&target) {
        findings.push("High-Entropy Secret (unrecognized format)".to_string());
    }

    findings
}

/// Returns true (blocked) if any pattern matches a `+` line in the diff.
/// Prints each matched label to stderr. Calls `scan_findings` internally.
pub fn scan(diff: &str) -> bool {
    let findings = scan_findings(diff);
    for label in &findings {
        eprintln!("[LocalForge] BLOCKED — secret detected: {label}");
    }
    !findings.is_empty()
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── key builders — never embed real patterns as literals ──────────────────
    fn aws_key() -> String {
        format!("AKIA{}", "I".repeat(16))
    }
    fn aws_secret() -> String {
        format!("aws_secret = '{}'", "a".repeat(40))
    }
    fn gcp_key() -> String {
        format!("AIza{}", "B".repeat(35))
    }
    fn stripe_key() -> String {
        format!("sk_live_{}", "a".repeat(24))
    }
    fn stripe_rk() -> String {
        format!("rk_live_{}", "a".repeat(24))
    }
    fn github_pat() -> String {
        format!("ghp_{}", "A".repeat(36))
    }
    fn github_fine() -> String {
        format!("github_pat_{}", "A".repeat(82))
    }
    fn github_action() -> String {
        format!("ghs_{}", "A".repeat(36))
    }
    fn slack_bot() -> String {
        format!("xoxb-{}", "1".repeat(12))
    }
    fn twilio_sid() -> String {
        format!("AC{}", "a".repeat(32))
    }
    fn sendgrid_key() -> String {
        format!("SG.{}.{}", "a".repeat(22), "b".repeat(43))
    }
    fn npm_token() -> String {
        format!("npm_{}", "A".repeat(36))
    }
    fn pypi_token() -> String {
        format!("pypi-{}", "A".repeat(40))
    }
    fn hf_token() -> String {
        format!("hf_{}", "A".repeat(34))
    }
    fn anthropic_key() -> String {
        format!("sk-ant-{}", "A".repeat(40))
    }
    fn openai_key() -> String {
        format!("sk-{}", "A".repeat(48))
    }
    fn openai_project_key() -> String {
        format!("sk-proj-{}", "A".repeat(20))
    }
    fn shopify_secret() -> String {
        format!("shpss_{}", "A".repeat(32))
    }
    fn bearer_token() -> String {
        format!("Bearer {}", "A".repeat(65))
    }

    // ── Layer 1 detection tests ───────────────────────────────────────────────
    #[test]
    fn detects_aws_access_key() {
        assert!(scan(&aws_key()));
    }
    #[test]
    fn detects_aws_secret() {
        assert!(scan(&aws_secret()));
    }
    #[test]
    fn detects_gcp_api_key() {
        assert!(scan(&gcp_key()));
    }
    #[test]
    fn detects_stripe_live() {
        assert!(scan(&stripe_key()));
    }
    #[test]
    fn detects_stripe_restricted() {
        assert!(scan(&stripe_rk()));
    }
    #[test]
    fn detects_github_pat() {
        assert!(scan(&github_pat()));
    }
    #[test]
    fn detects_github_fine_grained() {
        assert!(scan(&github_fine()));
    }
    #[test]
    fn detects_github_actions() {
        assert!(scan(&github_action()));
    }
    #[test]
    fn detects_slack_token() {
        assert!(scan(&slack_bot()));
    }
    #[test]
    fn detects_twilio_sid() {
        assert!(scan(&twilio_sid()));
    }
    #[test]
    fn detects_sendgrid_key() {
        assert!(scan(&sendgrid_key()));
    }
    #[test]
    fn detects_npm_token() {
        assert!(scan(&npm_token()));
    }
    #[test]
    fn detects_pypi_token() {
        assert!(scan(&pypi_token()));
    }
    #[test]
    fn detects_hf_token() {
        assert!(scan(&hf_token()));
    }
    #[test]
    fn detects_anthropic_key() {
        assert!(scan(&anthropic_key()));
    }
    #[test]
    fn detects_openai_key() {
        assert!(scan(&openai_key()));
    }
    #[test]
    fn detects_openai_project_key() {
        assert!(scan(&openai_project_key()));
    }
    #[test]
    fn detects_shopify_secret() {
        assert!(scan(&shopify_secret()));
    }
    #[test]
    fn detects_private_key_block() {
        assert!(scan("-----BEGIN RSA PRIVATE KEY-----"));
    }
    #[test]
    fn detects_openssh_key() {
        assert!(scan("-----BEGIN OPENSSH PRIVATE KEY-----"));
    }
    #[test]
    fn detects_high_entropy_bearer() {
        assert!(scan(&bearer_token()));
    }

    #[test]
    fn detects_env_file_secret() {
        assert!(scan("+DATABASE_PASSWORD=supersecretvalue123abc"));
    }

    #[test]
    fn detects_high_entropy_secret_unrecognized_format() {
        // Not shaped like any provider-specific rule above — this is exactly
        // the gap the entropy fallback exists to catch.
        assert!(scan(
            "internal_api_key = 'Xk9mQzT4wPl7Rj2Nc8Vb5Yd1Hs6Fg3Kw'"
        ));
    }

    #[test]
    fn detects_gcp_service_account() {
        assert!(scan(
            r#"{ "type": "service_account", "project_id": "my-proj" }"#
        ));
    }

    // ── Only added lines are scanned ──────────────────────────────────────────
    #[test]
    fn ignores_removed_secret_lines() {
        let diff = format!("-token = '{}'\n+token = os.environ['TOKEN']", aws_key());
        assert!(!scan(&diff), "should not block removal of a secret");
    }

    #[test]
    fn blocks_added_secret_lines() {
        let diff = format!("+token = '{}'", aws_key());
        assert!(scan(&diff));
    }

    // ── scan_findings returns labels ──────────────────────────────────────────
    #[test]
    fn scan_findings_returns_matched_labels() {
        let findings = scan_findings(&aws_key());
        assert!(!findings.is_empty());
        assert!(findings.iter().any(|l| l.contains("AWS")));
    }

    #[test]
    fn scan_findings_empty_on_clean_diff() {
        assert!(scan_findings("fn main() {}").is_empty());
    }

    // ── False positive guards ─────────────────────────────────────────────────
    #[test]
    fn passes_clean_rust() {
        assert!(!scan("fn main() { println!(\"hello\"); }"));
    }
    #[test]
    fn passes_clean_python() {
        assert!(!scan("def greet(n): return f'Hello, {n}'"));
    }
    #[test]
    fn passes_clean_typescript() {
        assert!(!scan("const add = (a: number, b: number) => a + b;"));
    }
    #[test]
    fn passes_clean_go() {
        assert!(!scan("func main() { fmt.Println(\"hello\") }"));
    }
    #[test]
    fn passes_clean_java() {
        assert!(!scan(
            "public class Main { public static void main(String[] args) {} }"
        ));
    }
    #[test]
    fn passes_clean_swift() {
        assert!(!scan(
            "func greet(_ name: String) -> String { return \"Hello \\(name)\" }"
        ));
    }
    #[test]
    fn passes_short_bearer() {
        assert!(!scan("Authorization: Bearer short"));
    }
    #[test]
    fn passes_env_var_ref() {
        assert!(!scan("API_KEY=$MY_API_KEY"));
    }
    #[test]
    fn passes_env_getenv() {
        assert!(!scan("api_key = os.getenv('API_KEY')"));
    }
    #[test]
    fn passes_sk_test_stripe() {
        assert!(!scan("key = sk_test_abc123"));
    }
    #[test]
    fn passes_entropy_env_var_dotted_ref() {
        // 23 chars, no quotes needed to match the char class — must be
        // excluded by the env-ref marker check, not just length.
        assert!(!scan("token: process.env.SECRET_ACCESS_TOKEN_VALUE"));
    }
    #[test]
    fn passes_entropy_numeric_only_value() {
        // Long and passes length/charset, but has no letters — e.g. a PIN
        // or numeric ID mistakenly named "secret". Uses a variable name
        // outside the pre-existing broad .env rule's keyword list (SECRET,
        // PASSWORD, PASSWD, PWD, API_KEY, AUTH_TOKEN, CREDENTIAL) so this
        // isolates the entropy fallback's own has_alpha gate.
        assert!(!scan("access_key = 20240101120000998877665544"));
    }
    #[test]
    fn passes_entropy_low_diversity_repetition() {
        // Mixed alnum (passes the has_digit/has_alpha gate) but only two
        // distinct symbols — entropy is far below the threshold. Uses a
        // variable name outside the pre-existing .env rule's keyword list
        // to isolate the entropy fallback's own threshold check.
        assert!(!scan("signing_key=A1A1A1A1A1A1A1A1A1A1A1A1"));
    }
}
