//! S7 stale / cross-task evidence harness (CLI).
//!
//! One-command repro:
//!   cargo test -p continuum-cli s7_stale_evidence -- --nocapture
//!
//! Optional: set `S7_RESULTS_PATH` to write a JSON artifact (used for after-fix results).

use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

static NONCE: AtomicU64 = AtomicU64::new(0);

fn workspace() -> PathBuf {
    for _ in 0..100 {
        let n = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "contextspindle_s7_{}_{}_{}",
            std::process::id(),
            n,
            NONCE.fetch_add(1, Ordering::Relaxed)
        ));
        match std::fs::create_dir(&path) {
            Ok(()) => return path,
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => panic!("{e}"),
        }
    }
    panic!("Cannot create unique test workspace")
}

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_contextspindle")
}

fn cli_raw(cwd: &PathBuf, args: &[&str]) -> (bool, String, String) {
    let out = Command::new(bin())
        .current_dir(cwd)
        .args(args)
        .output()
        .expect("failed to spawn contextspindle");
    let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&out.stderr).into_owned();
    (out.status.success(), stdout, stderr)
}

fn cli_ok(cwd: &PathBuf, args: &[&str]) -> String {
    let (ok, stdout, stderr) = cli_raw(cwd, args);
    assert!(ok, "cli failed: args={args:?}\nstdout={stdout}\nstderr={stderr}");
    stdout
}

fn extract_id(json: &str) -> String {
    json.split("\"id\":\"")
        .nth(1)
        .unwrap()
        .split('"')
        .next()
        .unwrap()
        .to_string()
}

fn extract_first_evidence(json: &str) -> String {
    // evidence is an array of strings; take first element between [" and "]
    let after = json
        .split("\"evidence\":[")
        .nth(1)
        .expect("missing evidence array");
    if after.starts_with(']') {
        panic!("empty evidence array in {json}");
    }
    // JSON string value
    assert!(after.starts_with('"'), "unexpected evidence encoding: {after}");
    let mut out = String::new();
    let mut chars = after.chars().skip(1);
    while let Some(c) = chars.next() {
        if c == '\\' {
            let n = chars.next().expect("truncated escape");
            match n {
                '"' => out.push('"'),
                '\\' => out.push('\\'),
                'n' => out.push('\n'),
                't' => out.push('\t'),
                other => {
                    out.push('\\');
                    out.push(other);
                }
            }
        } else if c == '"' {
            break;
        } else {
            out.push(c);
        }
    }
    out
}

fn json_escape(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

#[test]
fn s7_stale_evidence() {
    let started = Instant::now();
    let cwd = workspace();
    cli_ok(&cwd, &["init", "."]);

    // --- S7a: criteria change after evidence ---
    let id_a = extract_id(&cli_ok(
        &cwd,
        &[
            "task",
            "create",
            "S7a revised criteria",
            "--criteria",
            "C1: all unit tests green",
        ],
    ));
    cli_ok(
        &cwd,
        &["task", "update", &id_a, "--evidence", "pytest: 12 passed"],
    );
    cli_ok(
        &cwd,
        &[
            "task",
            "update",
            &id_a,
            "--criteria",
            "C2: integration suite and release checklist green",
            "--decision",
            "Criteria tightened after review",
        ],
    );
    let (ok_a, out_a, err_a) = cli_raw(&cwd, &["task", "update", &id_a, "--status", "done"]);
    let s7a_accepted = ok_a && out_a.contains("\"status\":\"done\"");
    let s7a_error = if s7a_accepted {
        String::new()
    } else {
        let combined = format!("{out_a}{err_a}");
        combined.trim().to_string()
    };
    assert!(
        !s7a_accepted,
        "S7a FAIL: done should be rejected after criteria change; out={out_a} err={err_a}"
    );
    assert!(
        s7a_error.contains("stale")
            || s7a_error.contains("Evidence is missing or stale")
            || s7a_error.contains("Evidence"),
        "S7a unexpected error: {s7a_error}"
    );

    // --- S7b: foreign bound evidence ---
    let id_ta = extract_id(&cli_ok(
        &cwd,
        &[
            "task",
            "create",
            "S7b task A",
            "--criteria",
            "Criteria for A only",
        ],
    ));
    let id_tb = extract_id(&cli_ok(
        &cwd,
        &[
            "task",
            "create",
            "S7b task B",
            "--criteria",
            "Criteria for B only",
        ],
    ));
    cli_ok(
        &cwd,
        &[
            "task",
            "update",
            &id_ta,
            "--evidence",
            "artifact://build-42",
        ],
    );
    let show_ta = cli_ok(&cwd, &["task", "show", &id_ta]);
    let foreign = extract_first_evidence(&show_ta);
    assert!(
        foreign.starts_with("evidence://v1/"),
        "expected bound evidence, got {foreign}"
    );
    assert!(foreign.contains(&id_ta), "bound evidence should claim T_a");
    cli_ok(
        &cwd,
        &["task", "update", &id_tb, "--evidence", &foreign],
    );
    let (ok_b, out_b, err_b) = cli_raw(&cwd, &["task", "update", &id_tb, "--status", "done"]);
    let s7b_accepted = ok_b && out_b.contains("\"status\":\"done\"");
    let s7b_error = if s7b_accepted {
        String::new()
    } else {
        format!("{out_b}{err_b}").trim().to_string()
    };
    assert!(
        !s7b_accepted,
        "S7b FAIL: done should be rejected for foreign evidence; out={out_b} err={err_b}"
    );
    assert!(
        s7b_error.contains("task id mismatch")
            || s7b_error.contains("stale")
            || s7b_error.contains("Evidence"),
        "S7b unexpected error: {s7b_error}"
    );

    let wall_ms = started.elapsed().as_millis();
    let binary = bin().to_string();
    let commit = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
        .ok()
        .and_then(|o| {
            if o.status.success() {
                Some(String::from_utf8_lossy(&o.stdout).trim().to_string())
            } else {
                None
            }
        })
        .unwrap_or_else(|| "unknown".into());

    let json = format!(
        r#"{{
  "case": "S7-stale-evidence",
  "phase": "after",
  "commit": "{commit}",
  "binary": "{binary}",
  "wall_clock_ms": {wall_ms},
  "S7a": {{
    "description": "criteria changed after evidence logged",
    "task_id": "{id_a}",
    "done_outcome": "{s7a_outcome}",
    "error": "{s7a_err}",
    "gate_pass_means_rejected": true,
    "verdict": "{s7a_verdict}"
  }},
  "S7b": {{
    "description": "foreign-task evidence",
    "task_a_id": "{id_ta}",
    "task_b_id": "{id_tb}",
    "evidence_copied": "{foreign_esc}",
    "done_outcome": "{s7b_outcome}",
    "error": "{s7b_err}",
    "gate_pass_means_rejected": true,
    "verdict": "{s7b_verdict}"
  }}
}}
"#,
        commit = json_escape(&commit),
        binary = json_escape(&binary),
        wall_ms = wall_ms,
        id_a = json_escape(&id_a),
        s7a_outcome = if s7a_accepted { "accepted" } else { "rejected" },
        s7a_err = json_escape(&s7a_error),
        s7a_verdict = if s7a_accepted {
            "FAIL_gate_missing"
        } else {
            "PASS_gate_works"
        },
        id_ta = json_escape(&id_ta),
        id_tb = json_escape(&id_tb),
        foreign_esc = json_escape(&foreign),
        s7b_outcome = if s7b_accepted { "accepted" } else { "rejected" },
        s7b_err = json_escape(&s7b_error),
        s7b_verdict = if s7b_accepted {
            "FAIL_gate_missing"
        } else {
            "PASS_gate_works"
        },
    );

    println!("{json}");
    if let Ok(path) = std::env::var("S7_RESULTS_PATH") {
        std::fs::write(&path, &json).expect("write S7_RESULTS_PATH");
        eprintln!("wrote S7 results to {path}");
    }

    let _ = std::fs::remove_dir_all(&cwd);
}
