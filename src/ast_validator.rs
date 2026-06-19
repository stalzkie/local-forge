use once_cell::sync::Lazy;
use regex::Regex;

struct Rule {
    pattern: &'static str,
    label:   &'static str,
}

const RULES: &[Rule] = &[
    // ── AWS ───────────────────────────────────────────────────────────────────
    Rule { pattern: r"AKIA[0-9A-Z]{16}",
           label: "AWS Access Key ID" },
    Rule { pattern: r#"(?i)(aws_secret|secret_access_key)\s*[=:]\s*['"]?[A-Za-z0-9/+=]{40}['"]?"#,
           label: "AWS Secret Access Key" },

    // ── GCP ───────────────────────────────────────────────────────────────────
    Rule { pattern: r#""type"\s*:\s*"service_account""#,
           label: "GCP Service Account JSON" },
    Rule { pattern: r"AIza[0-9A-Za-z\-_]{35}",
           label: "GCP API Key" },

    // ── Azure ─────────────────────────────────────────────────────────────────
    Rule { pattern: r"(?i)(AccountKey|SharedAccessSignature)\s*=\s*[A-Za-z0-9+/=]{40,}",
           label: "Azure Storage Key / SAS Token" },

    // ── Stripe ────────────────────────────────────────────────────────────────
    Rule { pattern: r"sk_live_[0-9a-zA-Z]{24,}",
           label: "Stripe Live Secret Key" },
    Rule { pattern: r"rk_live_[0-9a-zA-Z]{24,}",
           label: "Stripe Live Restricted Key" },

    // ── GitHub ────────────────────────────────────────────────────────────────
    Rule { pattern: r"ghp_[A-Za-z0-9]{36}",
           label: "GitHub PAT (classic)" },
    Rule { pattern: r"github_pat_[A-Za-z0-9_]{82}",
           label: "GitHub Fine-Grained PAT" },
    Rule { pattern: r"ghs_[A-Za-z0-9]{36}",
           label: "GitHub Actions Secret" },

    // ── Slack ─────────────────────────────────────────────────────────────────
    Rule { pattern: r"xox[bpars]-[0-9A-Za-z\-]{10,}",
           label: "Slack Token" },
    Rule { pattern: r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+",
           label: "Slack Webhook URL" },

    // ── Twilio ────────────────────────────────────────────────────────────────
    Rule { pattern: r"AC[0-9a-f]{32}",
           label: "Twilio Account SID" },
    Rule { pattern: r"SK[0-9a-f]{32}",
           label: "Twilio API Key" },

    // ── SendGrid ──────────────────────────────────────────────────────────────
    Rule { pattern: r"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}",
           label: "SendGrid API Key" },

    // ── npm / PyPI / HuggingFace / Anthropic / OpenAI ────────────────────────
    Rule { pattern: r"npm_[A-Za-z0-9]{36}",
           label: "npm Access Token" },
    Rule { pattern: r"pypi-[A-Za-z0-9\-_]{40,}",
           label: "PyPI API Token" },
    Rule { pattern: r"hf_[A-Za-z0-9]{34,}",
           label: "HuggingFace API Token" },
    Rule { pattern: r"sk-ant-[A-Za-z0-9\-_]{40,}",
           label: "Anthropic API Key" },
    Rule { pattern: r"sk-[A-Za-z0-9]{48}",
           label: "OpenAI API Key" },

    // ── Shopify ───────────────────────────────────────────────────────────────
    Rule { pattern: r"shpss_[A-Za-z0-9]{32}",
           label: "Shopify Shared Secret" },
    Rule { pattern: r"shpat_[A-Za-z0-9]{32}",
           label: "Shopify Access Token" },

    // ── Generic private keys ──────────────────────────────────────────────────
    Rule { pattern: r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY(?: BLOCK)?-----",
           label: "Private Key Block" },
    Rule { pattern: r"PuTTY-User-Key-File-[23]:",
           label: "PuTTY Private Key File" },

    // ── .env literal assignments (KEY=bare_secret_value) ─────────────────────
    // Matches lines like  SECRET_KEY=abc123longvalue  in .env file hunks.
    // Value must be 16+ alphanum chars (excludes $VAR references by char class).
    Rule { pattern: r#"(?i)(SECRET|PASSWORD|PASSWD|PWD|API_KEY|AUTH_TOKEN|CREDENTIAL)[A-Z0-9_]*\s*=\s*[A-Za-z0-9/+=_\-]{16,}"#,
           label: "Hardcoded Secret in .env Assignment" },

    // ── High-entropy bearer tokens (exclude docs / test fixtures) ────────────
    // Requires 60+ chars to reduce false positives on example tokens in comments.
    Rule { pattern: r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{60,}",
           label: "High-Entropy Bearer Token" },
];

static COMPILED: Lazy<Vec<(Regex, &'static str)>> = Lazy::new(|| {
    RULES.iter()
        .map(|r| (Regex::new(r.pattern).expect("invalid regex in RULES"), r.label))
        .collect()
});

/// Returns true (blocked) if any known secret pattern matches a `+` line in the diff.
/// Only scans added lines (lines starting with `+` but not `+++`) to avoid
/// flagging secrets that were already present and are being removed.
pub fn scan(diff: &str) -> bool {
    // Extract only added lines from the diff for pattern matching.
    // Fall back to scanning the whole input if it doesn't look like a diff.
    let target: String = {
        let added: Vec<&str> = diff.lines()
            .filter(|l| l.starts_with('+') && !l.starts_with("+++"))
            .collect();
        if added.is_empty() { diff.to_string() } else { added.join("\n") }
    };

    for (re, label) in COMPILED.iter() {
        if re.is_match(&target) {
            eprintln!("[LocalForge] BLOCKED — secret detected: {label}");
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── key builders — never embed real patterns as literals ──────────────────
    fn aws_key()        -> String { format!("AKIA{}", "I".repeat(16)) }
    fn aws_secret()     -> String { format!("aws_secret = '{}'", "a".repeat(40)) }
    fn gcp_key()        -> String { format!("AIza{}", "B".repeat(35)) }
    fn stripe_key()     -> String { format!("sk_live_{}", "a".repeat(24)) }
    fn stripe_rk()      -> String { format!("rk_live_{}", "a".repeat(24)) }
    fn github_pat()     -> String { format!("ghp_{}", "A".repeat(36)) }
    fn github_fine()    -> String { format!("github_pat_{}", "A".repeat(82)) }
    fn github_action()  -> String { format!("ghs_{}", "A".repeat(36)) }
    fn slack_bot()      -> String { format!("xoxb-{}", "1".repeat(12)) }
    fn twilio_sid()     -> String { format!("AC{}", "a".repeat(32)) }
    fn sendgrid_key()   -> String { format!("SG.{}.{}", "a".repeat(22), "b".repeat(43)) }
    fn npm_token()      -> String { format!("npm_{}", "A".repeat(36)) }
    fn pypi_token()     -> String { format!("pypi-{}", "A".repeat(40)) }
    fn hf_token()       -> String { format!("hf_{}", "A".repeat(34)) }
    fn anthropic_key()  -> String { format!("sk-ant-{}", "A".repeat(40)) }
    fn openai_key()     -> String { format!("sk-{}", "A".repeat(48)) }
    fn shopify_secret() -> String { format!("shpss_{}", "A".repeat(32)) }
    fn bearer_token()   -> String { format!("Bearer {}", "A".repeat(65)) }

    // ── Layer 1 detection tests ───────────────────────────────────────────────
    #[test] fn detects_aws_access_key()      { assert!(scan(&aws_key())); }
    #[test] fn detects_aws_secret()          { assert!(scan(&aws_secret())); }
    #[test] fn detects_gcp_api_key()         { assert!(scan(&gcp_key())); }
    #[test] fn detects_stripe_live()         { assert!(scan(&stripe_key())); }
    #[test] fn detects_stripe_restricted()   { assert!(scan(&stripe_rk())); }
    #[test] fn detects_github_pat()          { assert!(scan(&github_pat())); }
    #[test] fn detects_github_fine_grained() { assert!(scan(&github_fine())); }
    #[test] fn detects_github_actions()      { assert!(scan(&github_action())); }
    #[test] fn detects_slack_token()         { assert!(scan(&slack_bot())); }
    #[test] fn detects_twilio_sid()          { assert!(scan(&twilio_sid())); }
    #[test] fn detects_sendgrid_key()        { assert!(scan(&sendgrid_key())); }
    #[test] fn detects_npm_token()           { assert!(scan(&npm_token())); }
    #[test] fn detects_pypi_token()          { assert!(scan(&pypi_token())); }
    #[test] fn detects_hf_token()            { assert!(scan(&hf_token())); }
    #[test] fn detects_anthropic_key()       { assert!(scan(&anthropic_key())); }
    #[test] fn detects_openai_key()          { assert!(scan(&openai_key())); }
    #[test] fn detects_shopify_secret()      { assert!(scan(&shopify_secret())); }
    #[test] fn detects_private_key_block()   { assert!(scan("-----BEGIN RSA PRIVATE KEY-----")); }
    #[test] fn detects_openssh_key()         { assert!(scan("-----BEGIN OPENSSH PRIVATE KEY-----")); }
    #[test] fn detects_high_entropy_bearer() { assert!(scan(&bearer_token())); }

    #[test]
    fn detects_env_file_secret() {
        assert!(scan("+DATABASE_PASSWORD=supersecretvalue123abc"));
    }

    #[test]
    fn detects_gcp_service_account() {
        assert!(scan(r#"{ "type": "service_account", "project_id": "my-proj" }"#));
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

    // ── False positive guards ─────────────────────────────────────────────────
    #[test] fn passes_clean_rust()       { assert!(!scan("fn main() { println!(\"hello\"); }")); }
    #[test] fn passes_clean_python()     { assert!(!scan("def greet(n): return f'Hello, {n}'")); }
    #[test] fn passes_clean_typescript() { assert!(!scan("const add = (a: number, b: number) => a + b;")); }
    #[test] fn passes_clean_go()         { assert!(!scan("func main() { fmt.Println(\"hello\") }")); }
    #[test] fn passes_clean_java()       { assert!(!scan("public class Main { public static void main(String[] args) {} }")); }
    #[test] fn passes_clean_swift()      { assert!(!scan("func greet(_ name: String) -> String { return \"Hello \\(name)\" }")); }
    #[test] fn passes_short_bearer()     { assert!(!scan("Authorization: Bearer short")); }
    #[test] fn passes_env_var_ref()      { assert!(!scan("API_KEY=$MY_API_KEY")); }
    #[test] fn passes_env_getenv()       { assert!(!scan("api_key = os.getenv('API_KEY')")); }
    #[test] fn passes_sk_test_stripe()   { assert!(!scan("key = sk_test_abc123")); }
}
