// Phase 2 unit tests for JSON parser, GitHub dispatcher escaping, and Webhook request handling.

#[path = "../src/json.rs"]
mod json;
#[path = "../src/github.rs"]
mod github;

use json::parse_json;
use github::escape_json_str;

#[test]
fn test_json_parser_on_github_webhook_payload() {
    let payload = r#"{
        "action": "opened",
        "number": 42,
        "repository": {
            "name": "continuum",
            "full_name": "reacherwu/continuum",
            "private": false
        },
        "pull_request": {
            "id": 1001,
            "number": 42,
            "title": "Refactor connection pool",
            "head": {
                "sha": "4b8e21a89c9",
                "ref": "feature/net-modernize"
            },
            "base": {
                "sha": "7a6f1d002e1",
                "ref": "main"
            }
        }
    }"#;

    let parsed = parse_json(payload).expect("Failed to parse GitHub webhook payload");
    assert_eq!(parsed.get("action").and_then(|v| v.as_str()), Some("opened"));
    assert_eq!(parsed.get_path(&["repository", "full_name"]).and_then(|v| v.as_str()), Some("reacherwu/continuum"));
    assert_eq!(parsed.get_path(&["pull_request", "number"]).and_then(|v| v.as_i64()), Some(42));
    assert_eq!(parsed.get_path(&["pull_request", "head", "sha"]).and_then(|v| v.as_str()), Some("4b8e21a89c9"));
}

#[test]
fn test_github_escape_json_str() {
    let raw = "### 🐕 DiffHound Warning\n| File | Score |\n| :--- | :--- |\n| `test.rs:10` | 0.85 |";
    let escaped = escape_json_str(raw);
    assert!(escaped.contains("\\n"));
    assert!(!escaped.contains('\n'));
}

#[path = "../src/diff.rs"]
mod diff;
#[path = "../src/review.rs"]
mod review;
#[path = "../src/server.rs"]
mod server;

use server::{handle_request_bytes, ServerConfig};

#[test]
fn test_server_healthcheck_endpoint() {
    let config = ServerConfig {
        port: 8080,
        webhook_secret: None,
        github_token: None,
        threshold: 0.5,
    };

    let req = b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n";
    let (code, content_type, body) = handle_request_bytes(req, &config);

    assert_eq!(code, 200);
    assert_eq!(content_type, "application/json");
    assert!(body.contains("\"status\":\"healthy\""));
}

#[test]
fn test_server_webhook_secret_validation() {
    let config = ServerConfig {
        port: 8080,
        webhook_secret: Some("my-secret-key".into()),
        github_token: None,
        threshold: 0.5,
    };

    // 1. Missing or invalid signature
    let req_unauth = b"POST /webhook HTTP/1.1\r\nHost: localhost\r\nx-hub-signature-256: sha256=invalid\r\n\r\n{}";
    let (code_unauth, _, _) = handle_request_bytes(req_unauth, &config);
    assert_eq!(code_unauth, 401);

    // 2. Valid signature
    let req_auth = b"POST /webhook HTTP/1.1\r\nHost: localhost\r\nx-hub-signature-256: sha256=my-secret-key\r\n\r\n{}";
    let (code_auth, _, body) = handle_request_bytes(req_auth, &config);
    assert_eq!(code_auth, 200);
    assert!(body.contains("\"status\":\"processed\""));
}
