//! Standalone Pure-Rust HTTP Webhook Server for DiffHound GitHub App.
//!
//! Listens for GitHub `pull_request` webhooks, parses diffs, evaluates
//! regressions via ContinuumEngine, and dispatches reviews to GitHub.
//! Zero external runtime dependencies (100% standard library).

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::Arc;
use std::thread;

use continuum_core::{ContinuumConfig, ContinuumEngine};

use crate::diff::parse_unified_diff;
use crate::github::{create_check_run, fetch_pr_diff, post_pr_comment};
use crate::json::{parse_json, JsonValue};
use crate::review::{locate_memory_state, perform_review};

pub struct ServerConfig {
    pub port: u16,
    pub webhook_secret: Option<String>,
    pub github_token: Option<String>,
    pub threshold: f32,
}

pub fn run_webhook_server(config: ServerConfig) -> Result<(), String> {
    let addr = format!("0.0.0.0:{}", config.port);
    let listener = TcpListener::bind(&addr).map_err(|e| format!("Failed to bind to {addr}: {e}"))?;

    println!("============================================================================");
    println!("  🐕 DIFFHOUND GITHUB APP WEBHOOK SERVER RUNNING");
    println!("============================================================================");
    println!("Listening on:    http://{}", addr);
    println!("Webhook URL:     http://{}/webhook", addr);
    println!("Healthcheck:     http://{}/healthz", addr);
    println!("Regression Gate: Active (Threshold: {:.2})", config.threshold);
    println!("Status:          Ready for GitHub Pull Request Events");
    println!("============================================================================");

    let shared_cfg = Arc::new(config);

    for stream in listener.incoming() {
        match stream {
            Ok(s) => {
                let cfg = Arc::clone(&shared_cfg);
                thread::spawn(move || {
                    let _ = handle_connection(s, cfg);
                });
            }
            Err(e) => {
                eprintln!("Connection error: {e}");
            }
        }
    }

    Ok(())
}

pub fn handle_request_bytes(raw_req: &[u8], config: &ServerConfig) -> (u16, String, String) {
    let req_str = String::from_utf8_lossy(raw_req);
    let mut lines = req_str.lines();
    let req_line = lines.next().unwrap_or("");
    let parts: Vec<&str> = req_line.split_whitespace().collect();
    if parts.len() < 2 {
        return (400, "text/plain".into(), "Bad Request".into());
    }

    let method = parts[0];
    let path = parts[1];

    if method == "GET" && path == "/healthz" {
        return (
            200,
            "application/json".into(),
            "{\"status\":\"healthy\",\"service\":\"diffhound\"}".into(),
        );
    }

    if method == "POST" && path == "/webhook" {
        let mut event_type = String::new();
        let mut signature = String::new();

        for line in lines {
            if line.is_empty() {
                break;
            }
            let lower = line.to_lowercase();
            if lower.starts_with("x-github-event:") {
                if let Some(val) = line.split(':').nth(1) {
                    event_type = val.trim().to_string();
                }
            } else if lower.starts_with("x-hub-signature-256:") {
                if let Some(val) = line.split(':').nth(1) {
                    signature = val.trim().to_string();
                }
            }
        }

        let body = if let Some(idx) = req_str.find("\r\n\r\n") {
            &req_str[idx + 4..]
        } else {
            ""
        };

        if let Some(ref sec) = config.webhook_secret {
            if !signature.is_empty() && !signature.contains(sec) {
                return (401, "text/plain".into(), "Unauthorized".into());
            }
        }

        if event_type == "pull_request" || event_type.is_empty() {
            if let Ok(json) = parse_json(body) {
                process_pull_request_event(&json, config);
            }
        }

        return (200, "application/json".into(), "{\"status\":\"processed\"}".into());
    }

    (404, "text/plain".into(), "Not Found".into())
}

fn handle_connection(mut stream: TcpStream, config: Arc<ServerConfig>) -> Result<(), String> {
    let mut buf = vec![0u8; 8192];
    let n = stream.read(&mut buf).map_err(|e| e.to_string())?;
    if n == 0 {
        return Ok(());
    }

    let (status_code, content_type, body) = handle_request_bytes(&buf[..n], &config);
    let status_text = match status_code {
        200 => "200 OK",
        400 => "400 Bad Request",
        401 => "401 Unauthorized",
        404 => "404 Not Found",
        _ => "500 Internal Server Error",
    };

    let resp = format!(
        "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\n\r\n{}",
        status_text,
        content_type,
        body.len(),
        body
    );
    let _ = stream.write_all(resp.as_bytes());
    Ok(())
}

fn process_pull_request_event(json: &JsonValue, config: &ServerConfig) {
    let action = json.get("action").and_then(|v| v.as_str()).unwrap_or("");
    if action != "opened" && action != "synchronize" && action != "reopened" {
        println!("ℹ️ Skipping action: '{}' (only reviewing opened/synchronize)", action);
        return;
    }

    let repo = json.get_path(&["repository", "full_name"]).and_then(|v| v.as_str()).unwrap_or("");
    let pr_number = json.get_path(&["pull_request", "number"]).and_then(|v| v.as_i64()).unwrap_or(0) as u64;
    let head_sha = json.get_path(&["pull_request", "head", "sha"]).and_then(|v| v.as_str()).unwrap_or("");

    println!("🐕 DiffHound Processing PR #{}: '{}' on repo '{}' (SHA: {})", pr_number, action, repo, head_sha);

    let token = config.github_token.as_deref().unwrap_or("");
    if token.is_empty() || repo.is_empty() || pr_number == 0 {
        eprintln!("⚠️ Missing GitHub Token or repository metadata, skipping remote dispatch");
        return;
    }

    // 1. Fetch PR diff
    let diff_text = match fetch_pr_diff(token, repo, pr_number) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("Failed to fetch PR diff: {e}");
            return;
        }
    };

    let file_diffs = parse_unified_diff(&diff_text);

    // 2. Load engine
    let state_file = locate_memory_state();
    let mut engine = match state_file {
        Some(ref p) => ContinuumEngine::load_from_file(p).unwrap_or_else(|_| ContinuumEngine::new(ContinuumConfig::default())),
        None => ContinuumEngine::new(ContinuumConfig::default()),
    };

    // 3. Review
    let report = perform_review(&file_diffs, &mut engine, config.threshold);
    println!("✅ PR #{} Review Complete: Clean? {} | Alerts: {}", pr_number, report.is_clean(), report.alerts.len());

    // 4. Update Checks API
    let conclusion = if report.is_clean() { "success" } else { "failure" };
    let title = if report.is_clean() {
        "DiffHound Gate: Passed (Zero Noise)"
    } else {
        "DiffHound Gate: Potential Regression Detected"
    };

    let _ = create_check_run(
        token,
        repo,
        head_sha,
        title,
        &report.to_markdown(),
        conclusion,
    );

    // 5. Post comment on PR if regression detected (Zero-Noise: only post if not clean!)
    if !report.is_clean() {
        let _ = post_pr_comment(token, repo, pr_number, &report.to_markdown());
    }
}
