use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static NONCE: AtomicU64 = AtomicU64::new(0);

fn workspace() -> PathBuf {
    for _ in 0..100 {
        let n = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "contextspindle_e2e_{}_{}_{}",
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

fn cli(cwd: &PathBuf, args: &[&str]) -> String {
    let out = Command::new(env!("CARGO_BIN_EXE_contextspindle"))
        .current_dir(cwd)
        .args(args)
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8(out.stdout).unwrap()
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

#[test]
fn task_cli_survives_restarts_and_exposes_budgeted_context() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let id = extract_id(&cli(
        &cwd,
        &[
            "task",
            "create",
            "Finish launch",
            "--criteria",
            "Reviewed and published",
        ],
    ));
    cli(
        &cwd,
        &[
            "task",
            "update",
            &id,
            "--status",
            "active",
            "--next",
            "Run final tests",
            "--decision",
            "Do not skip review",
        ],
    );
    for i in 0..20 {
        cli(&cwd, &["task", "create", &format!("Unrelated {i}")]);
    }
    let shown = cli(&cwd, &["task", "show", &id]);
    assert!(shown.contains("Run final tests"));
    assert!(shown.contains("Do not skip review"));
    let context = cli(&cwd, &["task", "context", &id, "512"]);
    assert!(context.len() <= 512);
    assert!(context.contains("Finish launch"));
    assert!(context.contains("Source: durable task ledger"));
    assert!(cli(&cwd, &["task", "verify"]).contains("Verified 21 tasks"));
    let backup = cwd.join("saved-task-ledger");
    cli(&cwd, &["task", "backup", backup.to_str().unwrap()]);
    assert!(backup.join(&id).is_dir());
    let fresh = workspace();
    cli(&fresh, &["init", "."]);
    assert!(
        cli(&fresh, &["task", "restore", backup.to_str().unwrap()])
            .contains("Restored and verified 21 tasks")
    );
    assert!(cli(&fresh, &["task", "show", &id]).contains("Run final tests"));
    std::fs::remove_dir_all(fresh).unwrap();
    std::fs::remove_dir_all(cwd).unwrap();
}

#[test]
fn task_mcp_create_and_list_roundtrip() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let mut child = Command::new(env!("CARGO_BIN_EXE_contextspindle"))
        .current_dir(&cwd)
        .arg("mcp")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let requests = concat!(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"contextspindle_task_create\",\"arguments\":{\"goal\":\"Persist this task\",\"criteria\":\"Done when tested\"}}}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"contextspindle_task_list\",\"arguments\":{}}}\n"
    );
    child
        .stdin
        .take()
        .unwrap()
        .write_all(requests.as_bytes())
        .unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let text = String::from_utf8(output.stdout).unwrap();
    assert_eq!(text.lines().count(), 2);
    assert!(text.contains("Persist this task"));
    assert!(text.contains("Done when tested"));
    std::fs::remove_dir_all(cwd).unwrap();
}

#[test]
fn task_mcp_update_and_context_roundtrip() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let id = extract_id(&cli(
        &cwd,
        &[
            "task",
            "create",
            "Maintain mission",
            "--criteria",
            "Delivered",
        ],
    ));
    let mut child = Command::new(env!("CARGO_BIN_EXE_contextspindle"))
        .current_dir(&cwd)
        .arg("mcp")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let requests = format!(
        "{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{{\"name\":\"contextspindle_task_update\",\"arguments\":{{\"id\":\"{id}\",\"expected_version\":1,\"next\":\"Run audit\"}}}}}}\n{{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{{\"name\":\"contextspindle_task_context\",\"arguments\":{{\"id\":\"{id}\",\"budget_tokens\":512}}}}}}\n"
    );
    child
        .stdin
        .take()
        .unwrap()
        .write_all(requests.as_bytes())
        .unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success());
    let text = String::from_utf8(out.stdout).unwrap();
    assert_eq!(text.lines().count(), 2);
    assert!(text.contains("Run audit"));
    assert!(text.contains("Source: durable task ledger"));
    std::fs::remove_dir_all(cwd).unwrap();
}

#[test]
fn task_mcp_backup_and_restore_roundtrip() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let id = extract_id(&cli(&cwd, &["task", "create", "Recover via MCP"]));
    let backup = cwd.join("mcp-backup");
    let fresh = workspace();
    cli(&fresh, &["init", "."]);
    for (directory, name, argument) in [
        (&cwd, "contextspindle_task_backup", backup.to_str().unwrap()),
        (
            &fresh,
            "contextspindle_task_restore",
            backup.to_str().unwrap(),
        ),
    ] {
        let key = if name.ends_with("backup") {
            "destination"
        } else {
            "source"
        };
        let request = format!(
            "{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{{\"name\":\"{name}\",\"arguments\":{{\"{key}\":\"{argument}\"}}}}}}\n"
        );
        let mut child = Command::new(env!("CARGO_BIN_EXE_contextspindle"))
            .current_dir(directory)
            .arg("mcp")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(request.as_bytes())
            .unwrap();
        let output = child.wait_with_output().unwrap();
        assert!(output.status.success());
        assert!(
            !String::from_utf8(output.stdout)
                .unwrap()
                .contains("\"isError\":true")
        );
    }
    assert!(cli(&fresh, &["task", "show", &id]).contains("Recover via MCP"));
    std::fs::remove_dir_all(fresh).unwrap();
    std::fs::remove_dir_all(cwd).unwrap();
}

#[test]
fn corrupt_retrieval_cache_does_not_hide_durable_task() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let id = extract_id(&cli(&cwd, &["task", "create", "Keep mission visible"]));
    std::fs::write(cwd.join(".continuum").join("memory.state"), b"bad cache").unwrap();
    let context = cli(&cwd, &["task", "context", &id, "1024"]);
    assert!(context.contains("Keep mission visible"));
    std::fs::remove_dir_all(cwd).unwrap();
}

#[test]
fn task_versions_record_declared_agent_actor() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let created = Command::new(env!("CARGO_BIN_EXE_contextspindle"))
        .current_dir(&cwd)
        .env("CONTEXTSPINDLE_ACTOR", "agent-alpha")
        .args(["task", "create", "Shared mission"])
        .output()
        .unwrap();
    assert!(created.status.success());
    let id = extract_id(&String::from_utf8(created.stdout).unwrap());
    let updated = Command::new(env!("CARGO_BIN_EXE_contextspindle"))
        .current_dir(&cwd)
        .env("CONTEXTSPINDLE_ACTOR", "agent-beta")
        .args(["task", "update", &id, "--next", "Continue work"])
        .output()
        .unwrap();
    assert!(updated.status.success());
    let history = cli(&cwd, &["task", "history", &id]);
    assert!(history.contains("agent-alpha"));
    assert!(history.contains("agent-beta"));
    std::fs::remove_dir_all(cwd).unwrap();
}

#[test]
fn separate_agent_processes_do_not_lose_concurrent_updates() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let id = extract_id(&cli(&cwd, &["task", "create", "Shared concurrent goal"]));
    let mut processes = Vec::new();
    for n in 0..8 {
        processes.push(
            Command::new(env!("CARGO_BIN_EXE_contextspindle"))
                .current_dir(&cwd)
                .env("CONTEXTSPINDLE_ACTOR", format!("agent-{n}"))
                .args(["task", "update", &id, "--note", &format!("checkpoint {n}")])
                .stdout(Stdio::null())
                .spawn()
                .unwrap(),
        );
    }
    for mut process in processes {
        assert!(process.wait().unwrap().success());
    }
    let shown = cli(&cwd, &["task", "show", &id]);
    assert!(shown.contains("\"version\":9"));
    for n in 0..8 {
        assert!(shown.contains(&format!("checkpoint {n}")));
    }
    std::fs::remove_dir_all(cwd).unwrap();
}

#[test]
fn task_list_and_history_are_paginated() {
    let cwd = workspace();
    cli(&cwd, &["init", "."]);
    let first = extract_id(&cli(&cwd, &["task", "create", "First task"]));
    for n in 0..30 {
        cli(&cwd, &["task", "create", &format!("Task {n}")]);
    }
    let page = cli(&cwd, &["task", "list", "0", "10"]);
    assert!(page.contains("\"total\":31"));
    assert_eq!(page.matches("\"id\":").count(), 10);
    assert!(page.contains("\"next_offset\":10"));
    cli(&cwd, &["task", "update", &first, "--next", "Continue"]);
    let history = cli(&cwd, &["task", "history", &first, "1", "1"]);
    assert!(history.contains("\"total_versions\":2"));
    assert!(history.contains("\"next_version\":2"));
    std::fs::remove_dir_all(cwd).unwrap();
}
