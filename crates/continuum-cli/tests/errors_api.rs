use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

#[path = "../src/json.rs"]
mod json;
use json::{parse_json, JsonValue};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let dir = std::env::temp_dir().join(format!(
            "continuum-errors-api-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(dir.join("home")).unwrap();
        Self(dir)
    }
    fn command(&self) -> Command {
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_continuum-cli"));
        cmd.current_dir(&self.0).env("HOME", self.0.join("home"));
        cmd
    }
    fn cli(&self, args: &[&str]) -> Output {
        self.command().args(args).output().unwrap()
    }
    fn state(&self) -> PathBuf {
        self.0.join(".continuum/memory.state")
    }
    fn corrupt(&self) {
        fs::create_dir_all(self.state().parent().unwrap()).unwrap();
        fs::write(self.state(), b"incomplete snapshot").unwrap();
    }
    fn mcp(&self, requests: &str) -> Vec<JsonValue> {
        let mut child = self
            .command()
            .arg("mcp")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(requests.as_bytes())
            .unwrap();
        let out = child.wait_with_output().unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        String::from_utf8(out.stdout)
            .unwrap()
            .lines()
            .map(|line| parse_json(line).unwrap())
            .collect()
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn machine(out: &Output) -> JsonValue {
    parse_json(std::str::from_utf8(&out.stdout).unwrap()).unwrap()
}

#[test]
fn init_preserves_existing_memory_and_configuration() {
    let w = Workspace::new();
    assert!(w.cli(&["init", "."]).status.success());
    assert!(w.cli(&["remember", "keep existing event"]).status.success());
    let before = fs::read(w.state()).unwrap();
    assert!(w.cli(&["init", "."]).status.success());
    assert_eq!(fs::read(w.state()).unwrap(), before);
    let result = machine(&w.cli(&["--json", "stats"]));
    assert_eq!(
        result.get("step_count").and_then(JsonValue::as_str),
        Some("1")
    );
}

#[test]
fn json_options_preserve_literal_text_and_paths() {
    let w = Workspace::new();
    assert!(w.cli(&["init", "."]).status.success());
    for args in [
        vec!["--json", "remember", "--json"],
        vec!["remember", "--json", "--", "--json"],
        vec!["--json", "remember", "--", "--json"],
        vec!["memory", "ingest", "--json", "state", "--json"],
        vec!["--json", "memory", "ingest", "--", "--json", "--json"],
    ] {
        let out = w.cli(&args);
        assert!(out.status.success(), "{args:?}: {out:?}");
        assert_eq!(
            machine(&out).get("text").and_then(JsonValue::as_str),
            Some("--json")
        );
    }
    assert!(w.0.join("--json").exists());
    assert!(w.cli(&["memory", "ingest", "--json"]).status.success());
    let out = w.cli(&["--json", "memory", "query", "--", "--json", "--json", "5"]);
    assert!(out.status.success());
    assert!(!machine(&out)
        .get("matches")
        .unwrap()
        .as_array()
        .unwrap()
        .is_empty());
}

#[test]
fn unicode_surrogates_follow_json_semantics() {
    for (encoded, decoded) in [
        (r#""\uD83E\uDD80""#, "🦀"),
        (r#""\ud800\udc00""#, "\u{10000}"),
        (r#""\uDBFF\uDFFF""#, "\u{10ffff}"),
        (r#""\u4e2d\u6587 \ud83d\ude00""#, "中文 😀"),
    ] {
        assert_eq!(parse_json(encoded).unwrap().as_str(), Some(decoded));
    }
    for encoded in [
        r#""\ud800""#,
        r#""\udc00""#,
        r#""\ud800\u0041""#,
        r#""\ud800\ud800""#,
        r#""\ud800x""#,
    ] {
        assert!(parse_json(encoded).is_err(), "{encoded}");
    }
    let w = Workspace::new();
    let responses = w.mcp("{\"jsonrpc\":\"2.0\",\"id\":\"\\ud83e\\udd80\",\"method\":\"ping\"}\n");
    assert_eq!(
        responses[0].get("id").and_then(JsonValue::as_str),
        Some("🦀")
    );
}

#[test]
fn recovery_check_backup_and_confirmed_restore() {
    let w = Workspace::new();
    assert!(w
        .cli(&["memory", "ingest", "original event", "state"])
        .status
        .success());
    let original = fs::read(w.0.join("state")).unwrap();
    let out = w.cli(&["memory", "check", "state", "--json"]);
    assert!(out.status.success());
    assert_eq!(
        machine(&out)
            .get("checksum_verified")
            .and_then(JsonValue::as_bool),
        Some(false)
    );
    assert_eq!(fs::read(w.0.join("state")).unwrap(), original);
    assert!(w
        .cli(&["memory", "backup", "state", "backup", "--json"])
        .status
        .success());
    assert_eq!(fs::read(w.0.join("backup")).unwrap(), original);
    assert!(!w
        .cli(&["memory", "backup", "state", "backup", "--json"])
        .status
        .success());
    assert!(w
        .cli(&["memory", "ingest", "later event", "state"])
        .status
        .success());
    let changed = fs::read(w.0.join("state")).unwrap();
    assert!(!w
        .cli(&["memory", "restore", "backup", "state", "--json"])
        .status
        .success());
    assert_eq!(fs::read(w.0.join("state")).unwrap(), changed);
    let out = w.cli(&[
        "memory",
        "restore",
        "backup",
        "state",
        "--confirm",
        "--json",
    ]);
    assert!(out.status.success());
    assert_eq!(
        machine(&out).get("operation").and_then(JsonValue::as_str),
        Some("restore")
    );
    assert_eq!(fs::read(w.0.join("state")).unwrap(), original);
    assert!(w
        .cli(&["memory", "restore", "backup", "new-state", "--json"])
        .status
        .success());
    assert_eq!(fs::read(w.0.join("new-state")).unwrap(), original);
}

#[test]
fn storage_errors_are_nonzero_and_never_claim_success() {
    let w = Workspace::new();
    w.corrupt();
    for args in [
        vec!["remember", "new event"],
        vec!["recall", "event"],
        vec!["stats"],
        vec!["memory", "inspect", ".continuum/memory.state"],
        vec!["restore", ".continuum/memory.state"],
        vec!["init", "."],
    ] {
        let out = w.cli(&args);
        assert!(
            !out.status.success(),
            "{args:?}: {}",
            String::from_utf8_lossy(&out.stdout)
        );
        assert!(!String::from_utf8_lossy(&out.stdout).contains("Stored"));
    }
    assert_eq!(fs::read(w.state()).unwrap(), b"incomplete snapshot");
}

#[test]
fn write_failures_and_missing_transcript_are_nonzero() {
    let w = Workspace::new();
    fs::write(w.0.join("not-directory"), "file").unwrap();
    for args in [
        vec!["memory", "ingest", "event", "not-directory/state"],
        vec!["snapshot", "not-directory/state"],
        vec!["init", "not-directory"],
        vec!["memory", "sync", "missing.jsonl", "state"],
    ] {
        assert!(!w.cli(&args).status.success(), "{args:?}");
    }
}

#[test]
fn machine_roundtrip_preserves_full_unicode_and_step_ids() {
    let w = Workspace::new();
    let text = format!(
        "中文记忆 🦀\n\t\"完整内容\" {}",
        "long provenance 文本 ".repeat(35)
    );
    let out = w.cli(&["memory", "ingest", &text, "state", "--json"]);
    assert!(out.status.success());
    let result = machine(&out);
    assert_eq!(result.get("ok").and_then(JsonValue::as_bool), Some(true));
    assert_eq!(
        result.get("event_id").and_then(JsonValue::as_str),
        Some("0")
    );
    assert_eq!(
        result.get("text").and_then(JsonValue::as_str),
        Some(text.as_str())
    );
    let second = w.cli(&["memory", "ingest", "another event", "state", "--json"]);
    assert_eq!(
        machine(&second).get("event_id").and_then(JsonValue::as_str),
        Some("1")
    );
    let query = w.cli(&["memory", "query", &text, "state", "5", "--json"]);
    let result = machine(&query);
    let rows = result.get("matches").unwrap().as_array().unwrap();
    assert!(rows.iter().any(
        |v| v.get("event_id").and_then(JsonValue::as_str) == Some("0")
            && v.get("text").and_then(JsonValue::as_str) == Some(text.as_str())
    ));
    let inspect = machine(&w.cli(&["memory", "inspect", "state", "--json"]));
    assert_eq!(
        inspect.get("step_count").and_then(JsonValue::as_str),
        Some("2")
    );
    assert!(inspect
        .get("records")
        .unwrap()
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v.get("text").and_then(JsonValue::as_str) == Some(text.as_str())));
    let human = w.cli(&["memory", "inspect", "state"]);
    let human = String::from_utf8(human.stdout).unwrap();
    assert!(human.contains("  Total Steps:      2"));
    assert!(human.contains("  Hot Memory:       "));
}

#[test]
fn invalid_cli_inputs_have_stable_machine_error_codes() {
    let w = Workspace::new();
    for args in [
        vec!["memory", "ingest", "  ", "state", "--json"],
        vec!["memory", "query", "event", "state", "0", "--json"],
        vec!["memory", "query", "event", "state", "1.2", "--json"],
        vec!["memory", "query", "event", "state", "10001", "--json"],
        vec!["--json", "memory", "ingest"],
        vec!["memory", "inspect", "state", "extra", "--json"],
    ] {
        let out = w.cli(&args);
        assert_eq!(out.status.code(), Some(2), "{args:?}");
        assert_eq!(
            machine(&out)
                .get_path(&["error", "code"])
                .and_then(JsonValue::as_str),
            Some("INVALID_INPUT")
        );
    }
    assert!(!w.0.join("state").exists());
    let out = w.cli(&["memory", "inspect", "missing", "--json"]);
    assert_eq!(out.status.code(), Some(1));
    assert_eq!(
        machine(&out)
            .get_path(&["error", "code"])
            .and_then(JsonValue::as_str),
        Some("NOT_FOUND")
    );
}

#[test]
fn mcp_storage_failures_are_tool_errors_without_empty_fallback() {
    let w = Workspace::new();
    w.corrupt();
    let messages = w.mcp(concat!(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"continuum_remember\",\"arguments\":{\"text\":\"hello\"}}}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"continuum_recall\",\"arguments\":{\"query\":\"hello\"}}}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"continuum_stats\"}}\n"
    ));
    assert_eq!(messages.len(), 3);
    for message in messages {
        assert_eq!(
            message
                .get_path(&["result", "isError"])
                .and_then(JsonValue::as_bool),
            Some(true)
        );
        let content = message
            .get_path(&["result", "content"])
            .unwrap()
            .as_array()
            .unwrap();
        assert!(content[0]
            .get("text")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("INVALID_STATE"));
    }
    assert_eq!(fs::read(w.state()).unwrap(), b"incomplete snapshot");
}

#[test]
fn mcp_validates_arguments_and_protocol_and_stays_usable() {
    let w = Workspace::new();
    let requests = concat!(
        "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":\"init\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1\"}}}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"continuum_remember\",\"arguments\":{}}}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"continuum_recall\",\"arguments\":{\"query\":\"hello\",\"top_k\":1.5}}}\n",
        "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"unknown\"}\n",
        "not json\n",
        "{\"jsonrpc\":\"2.0\",\"id\":\"ping\\t\\n\",\"method\":\"ping\"}\n"
    );
    let messages = w.mcp(requests);
    assert_eq!(messages.len(), 7);
    assert_eq!(
        messages[0]
            .get_path(&["result", "protocolVersion"])
            .and_then(JsonValue::as_str),
        Some("2024-11-05")
    );
    assert_eq!(
        messages[1]
            .get_path(&["result", "tools"])
            .unwrap()
            .as_array()
            .unwrap()
            .len(),
        3
    );
    for index in [2, 3] {
        assert_eq!(
            messages[index]
                .get_path(&["result", "isError"])
                .and_then(JsonValue::as_bool),
            Some(true)
        );
    }
    assert_eq!(
        messages[4]
            .get_path(&["error", "code"])
            .and_then(JsonValue::as_i64),
        Some(-32601)
    );
    assert_eq!(
        messages[5]
            .get_path(&["error", "code"])
            .and_then(JsonValue::as_i64),
        Some(-32700)
    );
    assert_eq!(
        messages[6].get("id").and_then(JsonValue::as_str),
        Some("ping\t\n")
    );
    assert!(!w.state().exists());
}

#[test]
fn transcript_read_or_parse_failure_does_not_replace_state() {
    let w = Workspace::new();
    assert!(w
        .cli(&["memory", "ingest", "keep me", "state"])
        .status
        .success());
    let before = fs::read(w.0.join("state")).unwrap();
    fs::write(
        w.0.join("transcript"),
        b"{\"content\":\"valid event\"}\nnot json\n",
    )
    .unwrap();
    assert!(!w
        .cli(&["memory", "sync", "transcript", "state"])
        .status
        .success());
    assert_eq!(fs::read(w.0.join("state")).unwrap(), before);
    fs::write(w.0.join("transcript"), [0xff, 0xfe]).unwrap();
    assert!(!w
        .cli(&["memory", "sync", "transcript", "state"])
        .status
        .success());
    assert_eq!(fs::read(w.0.join("state")).unwrap(), before);
}
