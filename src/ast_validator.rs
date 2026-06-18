use regex::Regex;

struct Rule {
    pattern: &'static str,
    label: &'static str,
}

const RULES: &[Rule] = &[
    Rule { pattern: r"AKIA[0-9A-Z]{16}",                                                   label: "AWS Access Key ID"           },
    Rule { pattern: r#"(?i)(aws_secret|secret_key)\s*[=:]\s*['"]?[A-Za-z0-9/+=]{40}['"]?"#, label: "AWS Secret Key"              },
    Rule { pattern: r"sk_live_[0-9a-zA-Z]{24,}",                                           label: "Stripe Live Secret Key"      },
    Rule { pattern: r"ghp_[A-Za-z0-9]{36}",                                                label: "GitHub PAT (classic)"        },
    Rule { pattern: r"github_pat_[A-Za-z0-9_]{82}",                                        label: "GitHub Fine-Grained PAT"     },
    Rule { pattern: r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{40,}",                              label: "High-Entropy Bearer Token"   },
    Rule { pattern: r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",                    label: "Private Key Block"           },
];

/// Returns true (blocked) if a known high-entropy secret pattern is found.
/// Prints the matched rule label to stderr so the pre-commit hook can surface it.
pub fn scan(diff: &str) -> bool {
    for rule in RULES {
        let re = Regex::new(rule.pattern).expect("invalid regex in RULES");
        if re.is_match(diff) {
            eprintln!("[LocalForge] BLOCKED — secret detected: {}", rule.label);
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a fake AWS key at runtime so the literal never appears in source.
    fn fake_aws_key() -> String { format!("AKIA{}", "I" .repeat(16)) }
    /// Build a fake Stripe key at runtime.
    fn fake_stripe_key() -> String { format!("sk{}_live_{}", "", "a".repeat(24)) }
    /// Build a fake GitHub PAT at runtime.
    fn fake_github_pat() -> String { format!("ghp_{}", "A".repeat(36)) }

    #[test]
    fn detects_aws_access_key() {
        assert!(scan(&format!("token = '{}'", fake_aws_key())));
    }

    #[test]
    fn detects_stripe_key() {
        assert!(scan(&format!("key = {}", fake_stripe_key())));
    }

    #[test]
    fn detects_private_key_header() {
        assert!(scan("-----BEGIN RSA PRIVATE KEY-----"));
    }

    #[test]
    fn detects_github_pat() {
        assert!(scan(&format!("token = {}", fake_github_pat())));
    }

    #[test]
    fn passes_clean_rust_code() {
        assert!(!scan("fn main() { println!(\"hello world\"); }"));
    }

    #[test]
    fn passes_clean_python_code() {
        assert!(!scan("def greet(name):\n    return f'Hello, {name}'"));
    }

    #[test]
    fn passes_short_token() {
        // Should not trigger the high-entropy bearer rule (too short)
        assert!(!scan("Authorization: Bearer short"));
    }
}
