use std::io::Write;
use std::process::{Command, Stdio};

fn get_bin() -> &'static str {
    env!("CARGO_BIN_EXE_continuum-cli")
}

#[test]
fn test_regression_p1_cli_nonzero_exit_on_corrupt_state() {
    let temp_dir = std::env::temp_dir();
    let corrupt_file = temp_dir.join(format!("test_regress_corrupt_{}.state", std::process::id()));
    std::fs::write(&corrupt_file, b"BAD_CORRUPT_MAGIC_HEADER_12345").expect("Failed to write test file");

    let output = Command::new(get_bin())
        .args(["memory", "query", "any_query", corrupt_file.to_str().unwrap()])
        .output()
        .expect("Failed to run CLI");

    // Redline: Must fail with exit code 1, NEVER exit code 0
    assert_eq!(output.status.code(), Some(1), "Corrupted state must exit with code 1");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("Invalid Continuum checkpoint header") || stderr.contains("Error loading snapshot"),
        "stderr should describe the header corruption: {}", stderr);

    let _ = std::fs::remove_file(&corrupt_file);
}

#[test]
fn test_regression_p1_cli_nonzero_exit_on_missing_state() {
    let missing_file = "/tmp/continuum_nonexistent_state_file_99999.state";
    let output = Command::new(get_bin())
        .args(["memory", "query", "any_query", missing_file])
        .output()
        .expect("Failed to run CLI");

    // Redline: Nonexistent target snapshot must exit with code 1
    assert_eq!(output.status.code(), Some(1), "Missing snapshot query must exit with code 1");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("Error loading snapshot"), "stderr should report loading error: {}", stderr);
}

#[test]
fn test_regression_p1_mcp_is_error_flag_and_single_line_on_failure() {
    let mut child = Command::new(get_bin())
        .arg("mcp")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("Failed to spawn continuum mcp");

    let req = r#"{"jsonrpc":"2.0","id":777,"method":"tools/call","params":{"name":"continuum_remember","arguments":{"text":""}}}"#;

    {
        let stdin = child.stdin.as_mut().expect("Failed to open stdin");
        stdin.write_all(req.as_bytes()).unwrap();
        stdin.write_all(b"\n").unwrap();
        stdin.flush().unwrap();
    }

    let output = child.wait_with_output().expect("Failed to wait on child");
    let stdout_raw = String::from_utf8_lossy(&output.stdout);
    let line = stdout_raw.lines().next().expect("No output line received from MCP");

    // Redline 1: Strictly single line (no embedded newlines in stdio protocol mode)
    assert!(!line.contains('\r'), "MCP line must not contain carriage return");
    assert!(!stdout_raw.trim().contains('\n'), "MCP stdio response must be strictly single-line");

    // Redline 2: Must contain isError: true
    assert!(line.contains(r#""isError":true"#), "MCP failure response must contain isError: true! Got: {}", line);
    assert!(line.contains("Error: 'text' parameter is required"), "Must report argument validation failure: {}", line);
}

#[test]
fn test_regression_p4_runner_command_affinity_prevents_misattribution() {
    let temp_dir = std::env::temp_dir().join(format!("continuum_test_runner_{}", std::process::id()));
    
    // Initialize workspace
    let init_res = Command::new(get_bin())
        .args(["init", temp_dir.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(init_res.status.success());

    let continuum_dir = temp_dir.join(".continuum");

    // 1. Run a failing command to record an incident
    let fail_cmd = format!("cd '{}' && '{}' run sh -c 'echo \"Fatal test error in auth\" >&2; exit 1'",
        temp_dir.display(), get_bin());
    let _ = Command::new("sh").arg("-c").arg(&fail_cmd).output().unwrap();

    let incident_file = continuum_dir.join("pending_incident.json");
    assert!(incident_file.exists(), "Pending incident file should be recorded after failure");

    // 2. Run an UNRELATED successful command (e.g. ls or echo)
    let unrelated_cmd = format!("cd '{}' && '{}' run echo 'all good'",
        temp_dir.display(), get_bin());
    let unrelated_res = Command::new("sh").arg("-c").arg(&unrelated_cmd).output().unwrap();
    assert!(unrelated_res.status.success());

    // Redline: Unrelated command must NOT resolve or pair with the prior incident!
    assert!(incident_file.exists(), "Pending incident must NOT be resolved by unrelated command!");

    // 3. Run the SAME command successfully
    let fix_cmd = format!("cd '{}' && '{}' run sh -c 'echo \"All tests passed\"; exit 0'",
        temp_dir.display(), get_bin());
    let fix_res = Command::new("sh").arg("-c").arg(&fix_cmd).output().unwrap();
    assert!(fix_res.status.success());

    // Redline: Matching command must now clear the pending incident and ingest candidate fix
    assert!(!incident_file.exists(), "Pending incident should be cleared after matching command resolves it");

    // Verify memory contains the CANDIDATE_FIX record
    let query_res = Command::new(get_bin())
        .args(["recall", "--json", "Fatal test error", "1"])
        .current_dir(&temp_dir)
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&query_res.stdout);
    assert!(stdout.contains("CANDIDATE_FIX"), "Memory must store fix as CANDIDATE_FIX: {}", stdout);

    let _ = std::fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_regression_p4_sensitive_token_masking() {
    let temp_dir = std::env::temp_dir().join(format!("continuum_test_sanitize_{}", std::process::id()));
    let init_res = Command::new(get_bin())
        .args(["init", temp_dir.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(init_res.status.success());

    let continuum_dir = temp_dir.join(".continuum");

    // Run a command that prints an API token and password in stderr
    let fail_cmd = format!("cd '{}' && '{}' run sh -c 'echo \"Error with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and password=supersecretpassword123\" >&2; exit 1'",
        temp_dir.display(), get_bin());
    let _ = Command::new("sh").arg("-c").arg(&fail_cmd).output().unwrap();

    let incident_file = continuum_dir.join("pending_incident.json");
    assert!(incident_file.exists());
    let incident_content = std::fs::read_to_string(&incident_file).unwrap();

    // Redline: Raw secret must NEVER be persisted in incident or memory
    assert!(!incident_content.contains("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"), "JWT token must be sanitized!");
    assert!(!incident_content.contains("supersecretpassword123"), "Password must be sanitized!");
    assert!(incident_content.contains("[REDACTED_SECRET]"), "Secret should be replaced with [REDACTED_SECRET]");

    let _ = std::fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_regression_p5_recall_json_machine_schema() {
    let temp_dir = std::env::temp_dir().join(format!("continuum_test_json_{}", std::process::id()));
    let continuum_dir = temp_dir.join(".continuum");
    std::fs::create_dir_all(&continuum_dir).unwrap();

    // Ingest 2 distinct constraints
    let init_res = Command::new(get_bin())
        .args(["init", temp_dir.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(init_res.status.success());

    let rem1 = Command::new(get_bin())
        .current_dir(&temp_dir)
        .args(["remember", "RULE: Never commit AWS secret keys to version control"])
        .output()
        .unwrap();
    assert!(rem1.status.success());

    let rem2 = Command::new(get_bin())
        .current_dir(&temp_dir)
        .args(["remember", "RULE: Database pool max connections is set to 20"])
        .output()
        .unwrap();
    assert!(rem2.status.success());

    // Execute recall with --json
    let recall_out = Command::new(get_bin())
        .current_dir(&temp_dir)
        .args(["recall", "--json", "AWS secret keys", "2"])
        .output()
        .unwrap();
    assert!(recall_out.status.success());

    let json_text = String::from_utf8_lossy(&recall_out.stdout);
    let trimmed = json_text.trim();

    // Redline: Must start with [ and end with ]
    assert!(trimmed.starts_with('[') && trimmed.ends_with(']'),
        "Recall --json must output a JSON array! Got: {}", trimmed);

    // Verify field presence
    assert!(trimmed.contains(r#""rank":1"#), "JSON item must have rank");
    assert!(trimmed.contains(r#""score":"#), "JSON item must have score");
    assert!(trimmed.contains(r#""event_id":"#), "JSON item must have event_id");
    assert!(trimmed.contains(r#""provenance":"#), "JSON item must have provenance");
    assert!(trimmed.contains(r#""components":{"sim":"#), "JSON item must have components breakdown");
    assert!(trimmed.contains(r#""state_compat":"#), "JSON components must have state_compat");
    assert!(trimmed.contains(r#""temporal_compat":"#), "JSON components must have temporal_compat");

    let _ = std::fs::remove_dir_all(&temp_dir);
}
