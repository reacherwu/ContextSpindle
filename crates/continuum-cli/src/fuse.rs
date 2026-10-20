//! Compact fuse: keep the working thread of an agent session across context compaction.
//!
//! * `fuse save`    — run before compaction (Claude Code `PreCompact` hook). Reads the hook
//!   payload on stdin (or `--transcript PATH`), extracts the goal, open tasks, recent
//!   decisions/constraints, subagent results and touched files from the transcript, and
//!   appends a checksummed entry to `.contextspindle/fuse/ledger.jsonl`.
//! * `fuse restore` — run after compaction (Claude Code `SessionStart` with matcher
//!   `compact`). Prints the latest snapshot for the session as `additionalContext`
//!   (or plain text with `--plain` for other tools), within a byte budget.
//! * `fuse setup`   — previews (default) or writes (`--write`) the hook config.
//! * `fuse demo`    — offline demo on a bundled synthetic transcript; no API key.
//!
//! Extraction is heuristic and deterministic. It never calls a model.

use crate::json::{parse_json, JsonValue as J};
use std::collections::HashMap;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub const DEFAULT_BUDGET: usize = 6000; // bytes; Claude Code caps hook context at 10,000 chars
const DEMO_TRANSCRIPT: &str = include_str!("../../../examples/fuse/session.jsonl");
const DEMO_PROBES: &str = include_str!("../../../examples/fuse/probes.txt");

const DECISION_MARKERS: &[&str] = &[
    "decided", "decision", "we chose", "i chose", "chose ", "going with", "root cause",
    "because", "instead of", "trade-off", "tradeoff", "conclusion", "confirmed", "ruled out",
    "the fix is", "turns out", "won't work", "doesn't work",
];
const CONSTRAINT_MARKERS: &[&str] = &[
    "don't", "do not", "never", "always", "must", "only ", "keep ", "avoid", "without",
];

#[derive(Debug, Default, Clone, PartialEq)]
pub struct Snapshot {
    pub goal: String,
    pub recent_requests: Vec<String>,
    pub open_tasks: Vec<String>,
    pub done_tasks: usize,
    pub decisions: Vec<String>,
    pub constraints: Vec<String>,
    pub subagent_results: Vec<String>,
    pub files: Vec<String>,
    pub last_assistant: String,
    pub messages_seen: usize,
}

fn clip(s: &str, max: usize) -> String {
    let s = s.trim();
    if s.len() <= max {
        return s.to_string();
    }
    let mut end = max;
    while !s.is_char_boundary(end) {
        end -= 1;
    }
    format!("{}…", &s[..end])
}

fn one_line(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn block_text(v: &J) -> String {
    match v {
        J::String(s) => s.clone(),
        J::Array(items) => items
            .iter()
            .filter_map(|b| match b {
                J::String(s) => Some(s.clone()),
                _ if b.get("type").and_then(J::as_str) == Some("text") => {
                    b.get("text").and_then(J::as_str).map(str::to_string)
                }
                _ => None,
            })
            .collect::<Vec<_>>()
            .join("\n"),
        _ => String::new(),
    }
}

fn sentences(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    for line in text.lines() {
        let line = line.trim().trim_start_matches(['-', '*', '#', '>', ' ']);
        let mut cur = String::new();
        let chars: Vec<char> = line.chars().collect();
        for (i, &ch) in chars.iter().enumerate() {
            cur.push(ch);
            let at_break = chars.get(i + 1).map_or(true, |n| n.is_whitespace());
            if (matches!(ch, '。' | '！' | '？') || (matches!(ch, '.' | '!' | '?') && at_break)) && cur.trim().len() > 1 {
                out.push(cur.trim().to_string());
                cur.clear();
            }
        }
        if !cur.trim().is_empty() {
            out.push(cur.trim().to_string());
        }
    }
    out
}

fn has_marker(s: &str, markers: &[&str]) -> bool {
    let l = s.to_lowercase();
    markers.iter().any(|m| l.contains(m))
}

fn push_unique_tail(v: &mut Vec<String>, item: String, cap: usize) {
    if item.is_empty() {
        return;
    }
    v.retain(|x| x != &item);
    v.push(item);
    if v.len() > cap {
        v.remove(0);
    }
}

/// Extract a snapshot from a JSONL transcript. Accepts Claude Code transcript lines
/// (`{"type":"user","message":{...}}`) and generic `{"role":..,"content":..}` lines.
pub fn extract(transcript: &str, previous_goal: Option<&str>) -> Snapshot {
    let mut s = Snapshot::default();
    let mut todos: Vec<(String, String)> = Vec::new(); // (content, status) from TodoWrite
    let mut tasks: Vec<(String, String, String)> = Vec::new(); // (id, subject, status) from TaskCreate/TaskUpdate
    let mut pending_agents: HashMap<String, String> = HashMap::new();
    let mut first_prompt: Option<String> = None;

    for line in transcript.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Ok(v) = parse_json(line) else { continue };
        if v.get("isCompactSummary").and_then(J::as_bool) == Some(true)
            || v.get("isMeta").and_then(J::as_bool) == Some(true)
        {
            continue;
        }
        let msg = v.get("message").unwrap_or(&v);
        let role = msg
            .get("role")
            .and_then(J::as_str)
            .or_else(|| v.get("type").and_then(J::as_str))
            .unwrap_or("");
        let Some(content) = msg.get("content") else { continue };
        s.messages_seen += 1;

        // Structured blocks: tool_use / tool_result
        if let Some(blocks) = content.as_array() {
            for b in blocks {
                match b.get("type").and_then(J::as_str) {
                    Some("tool_use") => {
                        let name = b.get("name").and_then(J::as_str).unwrap_or("");
                        let id = b.get("id").and_then(J::as_str).unwrap_or("").to_string();
                        let input = b.get("input");
                        match name {
                            "TodoWrite" => {
                                if let Some(list) = input.and_then(|i| i.get("todos")).and_then(J::as_array) {
                                    todos = list
                                        .iter()
                                        .map(|t| {
                                            (
                                                t.get("content").and_then(J::as_str).unwrap_or("").to_string(),
                                                t.get("status").and_then(J::as_str).unwrap_or("pending").to_string(),
                                            )
                                        })
                                        .collect();
                                }
                            }
                            "TaskCreate" => {
                                let subj = input
                                    .and_then(|i| i.get("subject").or_else(|| i.get("description")))
                                    .and_then(J::as_str)
                                    .unwrap_or("")
                                    .to_string();
                                let tid = (tasks.len() + 1).to_string();
                                tasks.push((tid, subj, "pending".into()));
                            }
                            "TaskUpdate" => {
                                let tid = input
                                    .and_then(|i| i.get("taskId"))
                                    .map(|x| x.as_str().map(str::to_string).unwrap_or_else(|| x.to_json_string()))
                                    .unwrap_or_default();
                                let st = input.and_then(|i| i.get("status")).and_then(J::as_str);
                                if let (Some(st), Some(t)) = (st, tasks.iter_mut().find(|t| t.0 == tid)) {
                                    t.2 = st.to_string();
                                }
                            }
                            "Task" | "Agent" => {
                                let d = input
                                    .and_then(|i| i.get("description").or_else(|| i.get("prompt")))
                                    .and_then(J::as_str)
                                    .unwrap_or("subagent");
                                pending_agents.insert(id, clip(&one_line(d), 120));
                            }
                            "Edit" | "Write" | "MultiEdit" | "NotebookEdit" => {
                                if let Some(p) = input
                                    .and_then(|i| i.get("file_path").or_else(|| i.get("notebook_path")))
                                    .and_then(J::as_str)
                                {
                                    push_unique_tail(&mut s.files, p.to_string(), 15);
                                }
                            }
                            _ => {}
                        }
                    }
                    Some("tool_result") => {
                        let id = b.get("tool_use_id").and_then(J::as_str).unwrap_or("");
                        if let Some(desc) = pending_agents.remove(id) {
                            let txt = b.get("content").map(block_text).unwrap_or_default();
                            push_unique_tail(
                                &mut s.subagent_results,
                                format!("[{}] {}", desc, clip(&one_line(&txt), 700)),
                                6,
                            );
                        }
                    }
                    _ => {}
                }
            }
        }

        let text = block_text(content);
        if text.trim().is_empty() {
            continue;
        }
        match role {
            "user" | "human" => {
                if text.starts_with("<command-") || text.starts_with("<local-command") {
                    continue;
                }
                if first_prompt.is_none() {
                    first_prompt = Some(clip(&one_line(&text), 700));
                }
                push_unique_tail(&mut s.recent_requests, clip(&one_line(&text), 400), 3);
                for sen in sentences(&text) {
                    if has_marker(&sen, CONSTRAINT_MARKERS) && sen.len() > 12 {
                        push_unique_tail(&mut s.constraints, clip(&sen, 300), 8);
                    }
                }
            }
            "assistant" => {
                s.last_assistant = clip(&one_line(&text), 600);
                for sen in sentences(&text) {
                    if has_marker(&sen, DECISION_MARKERS) && sen.len() > 20 {
                        push_unique_tail(&mut s.decisions, clip(&sen, 300), 10);
                    }
                }
            }
            _ => {}
        }
    }

    s.goal = previous_goal
        .map(str::to_string)
        .filter(|g| !g.is_empty())
        .or(first_prompt)
        .unwrap_or_default();
    for (c, st) in &todos {
        if st == "completed" { s.done_tasks += 1 } else { s.open_tasks.push(format!("[{st}] {c}")) }
    }
    for (_, subj, st) in &tasks {
        if st == "completed" || st == "deleted" { s.done_tasks += 1 } else { s.open_tasks.push(format!("[{st}] {subj}")) }
    }
    s
}

/// Render a snapshot as Markdown within `budget` bytes. Sections are dropped from the
/// lowest priority upward; the goal and open tasks are kept first.
pub fn render(s: &Snapshot, budget: usize) -> (String, Vec<&'static str>) {
    let header = "## ContextSpindle compact fuse\nThe conversation was compacted. This is a deterministic extract of the pre-compaction transcript (not a model summary); verify before relying on it.\n";
    let list = |title: &str, items: &[String]| -> String {
        if items.is_empty() { return String::new() }
        let mut o = format!("\n### {title}\n");
        for i in items { o.push_str(&format!("- {i}\n")); }
        o
    };
    let mut sections: Vec<(&'static str, String)> = vec![
        ("goal", format!("\n### Goal (first user request)\n{}\n", s.goal)),
        ("open_tasks", {
            let mut t = list("Open tasks", &s.open_tasks);
            if s.done_tasks > 0 { t.push_str(&format!("({} task(s) already completed)\n", s.done_tasks)); }
            t
        }),
        ("constraints", list("User constraints", &s.constraints)),
        ("decisions", list("Recent decisions and findings", &s.decisions)),
        ("subagents", list("Subagent results", &s.subagent_results)),
        ("recent_requests", list("Latest user requests", &s.recent_requests.iter().filter(|r| **r != s.goal).cloned().collect::<Vec<_>>())),
        ("last_assistant", if s.last_assistant.is_empty() { String::new() } else { format!("\n### Where the assistant left off\n{}\n", s.last_assistant) }),
        ("files", list("Files edited", &s.files)),
    ];
    let mut dropped = Vec::new();
    loop {
        let total: usize = header.len() + sections.iter().map(|(_, t)| t.len()).sum::<usize>();
        if total <= budget || sections.len() <= 1 { break }
        let (name, _) = sections.pop().unwrap();
        dropped.push(name);
    }
    let mut out = String::from(header);
    for (_, t) in &sections { out.push_str(t); }
    if out.len() > budget { out = clip(&out, budget.saturating_sub(4)); }
    (out, dropped)
}

fn fnv1a(s: &str) -> String {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in s.as_bytes() { h ^= *b as u64; h = h.wrapping_mul(0x100000001b3); }
    format!("{h:016x}")
}

fn fuse_dir(cwd: &str) -> PathBuf {
    if let Ok(d) = std::env::var("CONTEXTSPINDLE_FUSE_DIR") { return PathBuf::from(d) }
    Path::new(cwd).join(".contextspindle").join("fuse")
}

fn now_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0)
}

fn snapshot_json(s: &Snapshot) -> J {
    let arr = |v: &[String]| J::Array(v.iter().map(|x| J::String(x.clone())).collect());
    J::Object(vec![
        ("goal".into(), J::String(s.goal.clone())),
        ("recent_requests".into(), arr(&s.recent_requests)),
        ("open_tasks".into(), arr(&s.open_tasks)),
        ("done_tasks".into(), J::Number(s.done_tasks as f64)),
        ("decisions".into(), arr(&s.decisions)),
        ("constraints".into(), arr(&s.constraints)),
        ("subagent_results".into(), arr(&s.subagent_results)),
        ("files".into(), arr(&s.files)),
        ("last_assistant".into(), J::String(s.last_assistant.clone())),
        ("messages_seen".into(), J::Number(s.messages_seen as f64)),
    ])
}

fn snapshot_from_json(v: &J) -> Snapshot {
    let arr = |k: &str| v.get(k).and_then(J::as_array).map(|a| a.iter().filter_map(J::as_str).map(str::to_string).collect()).unwrap_or_default();
    let st = |k: &str| v.get(k).and_then(J::as_str).unwrap_or("").to_string();
    Snapshot {
        goal: st("goal"), recent_requests: arr("recent_requests"), open_tasks: arr("open_tasks"),
        done_tasks: v.get("done_tasks").and_then(J::as_u64).unwrap_or(0) as usize,
        decisions: arr("decisions"), constraints: arr("constraints"), subagent_results: arr("subagent_results"),
        files: arr("files"), last_assistant: st("last_assistant"),
        messages_seen: v.get("messages_seen").and_then(J::as_u64).unwrap_or(0) as usize,
    }
}

/// Ledger entries, oldest first. Entries whose checksum does not match are skipped.
pub fn read_ledger(dir: &Path) -> Vec<(String, Snapshot)> {
    let Ok(raw) = std::fs::read_to_string(dir.join("ledger.jsonl")) else { return vec![] };
    raw.lines().filter_map(|l| {
        let v = parse_json(l).ok()?;
        let snap = v.get("snapshot")?;
        if v.get("sha").and_then(J::as_str)? != fnv1a(&snap.to_json_string()) { return None }
        Some((v.get("session_id").and_then(J::as_str).unwrap_or("").to_string(), snapshot_from_json(snap)))
    }).collect()
}

pub fn save(dir: &Path, session_id: &str, trigger: &str, transcript: &str) -> Result<Snapshot, String> {
    let prev = read_ledger(dir).into_iter().rev().find(|(sid, _)| sid == session_id).map(|(_, s)| s.goal);
    let snap = extract(transcript, prev.as_deref());
    std::fs::create_dir_all(dir).map_err(|e| format!("create {}: {e}", dir.display()))?;
    let sj = snapshot_json(&snap);
    let entry = J::Object(vec![
        ("ts_ms".into(), J::Number(now_ms() as f64)),
        ("session_id".into(), J::String(session_id.into())),
        ("trigger".into(), J::String(trigger.into())),
        ("sha".into(), J::String(fnv1a(&sj.to_json_string()))),
        ("snapshot".into(), sj),
    ]);
    use std::io::Write;
    let mut f = std::fs::OpenOptions::new().create(true).append(true).open(dir.join("ledger.jsonl"))
        .map_err(|e| format!("open ledger: {e}"))?;
    writeln!(f, "{}", entry.to_json_string()).map_err(|e| format!("write ledger: {e}"))?;
    let _ = std::fs::write(dir.join("latest.md"), render(&snap, usize::MAX / 2).0);
    Ok(snap)
}

pub fn restore_text(dir: &Path, session_id: Option<&str>, budget: usize) -> Option<String> {
    let entries = read_ledger(dir);
    let found = match session_id {
        Some(sid) if !sid.is_empty() => entries.iter().rev().find(|(s, _)| s == sid).or(entries.last()),
        _ => entries.last(),
    }?;
    let mut text = render(&found.1, budget).0;
    // Optional: point at the durable task ledger's top open task, if this workspace has one.
    if let Ok(store) = crate::tasks::Store::discover() {
        if let Ok(top) = store.inbox(1) {
            if let Some(t) = top.first() {
                let line = format!("\n### Durable task ledger\nTop open task {}: {} (next: {}). Run `contextspindle task context {}` for details.\n", t.id, clip(&t.goal, 200), clip(&t.next, 200), t.id);
                if text.len() + line.len() <= budget { text.push_str(&line) }
            }
        }
    }
    Some(text)
}

fn read_stdin_json() -> J {
    let mut buf = String::new();
    use std::io::IsTerminal;
    if std::io::stdin().is_terminal() { return J::Object(vec![]) }
    let _ = std::io::stdin().read_to_string(&mut buf);
    parse_json(buf.trim()).unwrap_or(J::Object(vec![]))
}

fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).map(String::as_str)
}

fn hook_output(text: &str) -> String {
    J::Object(vec![("hookSpecificOutput".into(), J::Object(vec![
        ("hookEventName".into(), J::String("SessionStart".into())),
        ("additionalContext".into(), J::String(text.into())),
    ]))]).to_json_string()
}

// ---------------------------------------------------------------- setup

fn pretty(v: &J, ind: usize, out: &mut String) {
    let pad = "  ".repeat(ind + 1);
    match v {
        J::Array(a) if !a.is_empty() => {
            out.push_str("[\n");
            for (i, x) in a.iter().enumerate() {
                out.push_str(&pad); pretty(x, ind + 1, out);
                if i + 1 < a.len() { out.push(',') } out.push('\n');
            }
            out.push_str(&"  ".repeat(ind)); out.push(']');
        }
        J::Object(o) if !o.is_empty() => {
            out.push_str("{\n");
            for (i, (k, x)) in o.iter().enumerate() {
                out.push_str(&pad); out.push_str(&J::String(k.clone()).to_json_string()); out.push_str(": ");
                pretty(x, ind + 1, out);
                if i + 1 < o.len() { out.push(',') } out.push('\n');
            }
            out.push_str(&"  ".repeat(ind)); out.push('}');
        }
        _ => out.push_str(&v.to_json_string()),
    }
}

fn obj_set(o: &mut Vec<(String, J)>, k: &str, v: J) {
    if let Some(slot) = o.iter_mut().find(|(kk, _)| kk == k) { slot.1 = v } else { o.push((k.into(), v)) }
}

fn hook_entry(matcher: &str, exe: &str, sub: &str) -> J {
    J::Object(vec![
        ("matcher".into(), J::String(matcher.into())),
        ("hooks".into(), J::Array(vec![J::Object(vec![
            ("type".into(), J::String("command".into())),
            ("command".into(), J::String(exe.into())),
            ("args".into(), J::Array(vec![J::String("fuse".into()), J::String(sub.into())])),
            ("timeout".into(), J::Number(30.0)),
        ])])),
    ])
}

/// Merge fuse hooks into a Claude Code settings document. Returns (new_json, changed).
pub fn merge_settings(existing: &str, exe: &str) -> Result<(String, bool), String> {
    let mut root = if existing.trim().is_empty() { J::Object(vec![]) } else { parse_json(existing)? };
    let J::Object(ref mut top) = root else { return Err("settings root is not an object".into()) };
    let mut hooks = match top.iter().find(|(k, _)| k == "hooks").map(|(_, v)| v.clone()) {
        Some(J::Object(h)) => h, None => vec![], Some(_) => return Err("`hooks` is not an object".into()),
    };
    let mut changed = false;
    for (event, matcher, sub) in [("PreCompact", "manual|auto", "save"), ("SessionStart", "compact", "restore")] {
        let mut list = match hooks.iter().find(|(k, _)| k == event).map(|(_, v)| v.clone()) {
            Some(J::Array(a)) => a, _ => vec![],
        };
        let present = list.iter().any(|e| e.to_json_string().contains(&format!("\"fuse\",\"{sub}\"")));
        if !present { list.push(hook_entry(matcher, exe, sub)); changed = true; }
        obj_set(&mut hooks, event, J::Array(list));
    }
    obj_set(top, "hooks", J::Object(hooks));
    let mut out = String::new(); pretty(&root, 0, &mut out); out.push('\n');
    Ok((out, changed))
}

fn settings_path(args: &[String]) -> PathBuf {
    if let Some(p) = flag(args, "--settings") { return PathBuf::from(p) }
    if args.iter().any(|a| a == "--project") { return PathBuf::from(".claude/settings.json") }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    Path::new(&home).join(".claude").join("settings.json")
}

fn run_setup(args: &[String]) -> Result<String, String> {
    let path = settings_path(args);
    let exe = std::env::current_exe().map(|p| p.display().to_string()).unwrap_or_else(|_| "contextspindle".into());
    let existing = std::fs::read_to_string(&path).unwrap_or_default();
    let (merged, changed) = merge_settings(&existing, &exe)?;
    if !changed { return Ok(format!("Fuse hooks already present in {}. Nothing to do.", path.display())) }
    if !args.iter().any(|a| a == "--write") {
        return Ok(format!("Preview: {} would become\n\n{merged}\nRe-run with --write to apply (a .bak copy of the old file is kept).", path.display()));
    }
    if let Some(parent) = path.parent() { std::fs::create_dir_all(parent).map_err(|e| e.to_string())? }
    if !existing.is_empty() { std::fs::write(path.with_extension("json.bak"), &existing).map_err(|e| e.to_string())? }
    std::fs::write(&path, merged).map_err(|e| e.to_string())?;
    Ok(format!("Wrote PreCompact + SessionStart(compact) fuse hooks to {}.", path.display()))
}

// ---------------------------------------------------------------- demo

pub struct DemoResult { pub probes: usize, pub hits: Vec<bool>, pub transcript_bytes: usize, pub context_bytes: usize, pub save_ms: f64, pub restore_ms: f64, pub dropped: Vec<&'static str> }

pub fn run_demo_measure(budget: usize) -> Result<DemoResult, String> {
    let dir = std::env::temp_dir().join(format!("cs-fuse-demo-{}-{}", std::process::id(), now_ms()));
    let t0 = Instant::now();
    let snap = save(&dir, "demo-session", "auto", DEMO_TRANSCRIPT)?;
    let save_ms = t0.elapsed().as_secs_f64() * 1e3;
    let t1 = Instant::now();
    let ctx = render(&read_ledger(&dir).last().ok_or("empty ledger")?.1, budget);
    let restore_ms = t1.elapsed().as_secs_f64() * 1e3;
    let _ = snap;
    let probes: Vec<&str> = DEMO_PROBES.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')).collect();
    let low = ctx.0.to_lowercase();
    let hits = probes.iter().map(|p| low.contains(&p.to_lowercase())).collect();
    let _ = std::fs::remove_dir_all(&dir);
    Ok(DemoResult { probes: probes.len(), hits, transcript_bytes: DEMO_TRANSCRIPT.len(), context_bytes: ctx.0.len(), save_ms, restore_ms, dropped: ctx.1 })
}

fn run_demo(args: &[String]) -> Result<String, String> {
    let budget = flag(args, "--budget").and_then(|b| b.parse().ok()).unwrap_or(DEFAULT_BUDGET);
    let r = run_demo_measure(budget)?;
    let probes: Vec<&str> = DEMO_PROBES.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')).collect();
    let snap = extract(DEMO_TRANSCRIPT, None);
    let (ctx, _) = render(&snap, budget);
    let mut o = String::new();
    o.push_str("ContextSpindle compact fuse — offline demo (synthetic transcript, no API key)\n");
    o.push_str(&format!("Transcript: {} bytes, {} messages. Re-injected context: {} bytes (budget {}).\n", r.transcript_bytes, snap.messages_seen, r.context_bytes, budget));
    o.push_str(&format!("save {:.2} ms, restore {:.2} ms (in-process, this machine)\n\n", r.save_ms, r.restore_ms));
    o.push_str("---- context injected after compaction ----\n");
    o.push_str(&ctx);
    o.push_str("\n---- probe facts (stated once in the transcript) ----\n");
    for (p, h) in probes.iter().zip(&r.hits) { o.push_str(&format!("{} {}\n", if *h { "[kept]" } else { "[LOST]" }, p)); }
    o.push_str(&format!("\n{}/{} probe facts present in re-injected context.", r.hits.iter().filter(|h| **h).count(), r.probes));
    if !r.dropped.is_empty() { o.push_str(&format!(" Sections dropped to fit budget: {}.", r.dropped.join(", "))) }
    Ok(o)
}

// ---------------------------------------------------------------- CLI

pub fn run_cli(args: &[String]) -> Result<String, String> {
    let sub = args.first().map(String::as_str).unwrap_or("help");
    let rest = if args.is_empty() { &[][..] } else { &args[1..] };
    match sub {
        "save" => {
            let payload = if flag(rest, "--transcript").is_some() { J::Object(vec![]) } else { read_stdin_json() };
            let tpath = flag(rest, "--transcript").map(str::to_string)
                .or_else(|| payload.get("transcript_path").and_then(J::as_str).map(str::to_string))
                .ok_or("no transcript: pass --transcript PATH or a hook payload with transcript_path on stdin")?;
            let cwd = payload.get("cwd").and_then(J::as_str).map(str::to_string)
                .unwrap_or_else(|| std::env::current_dir().map(|p| p.display().to_string()).unwrap_or(".".into()));
            let sid = flag(rest, "--session").or(payload.get("session_id").and_then(J::as_str)).unwrap_or("default").to_string();
            let trig = payload.get("trigger").and_then(J::as_str).unwrap_or("manual").to_string();
            let transcript = std::fs::read_to_string(&tpath).map_err(|e| format!("read {tpath}: {e}"))?;
            let snap = save(&fuse_dir(&cwd), &sid, &trig, &transcript)?;
            // Never block compaction: print nothing on stdout for the hook; summary to stderr.
            eprintln!("contextspindle fuse: saved goal + {} open task(s), {} decision(s), {} subagent result(s)", snap.open_tasks.len(), snap.decisions.len(), snap.subagent_results.len());
            Ok(String::new())
        }
        "restore" => {
            let payload = read_stdin_json();
            let cwd = payload.get("cwd").and_then(J::as_str).map(str::to_string)
                .unwrap_or_else(|| std::env::current_dir().map(|p| p.display().to_string()).unwrap_or(".".into()));
            let sid = flag(rest, "--session").or(payload.get("session_id").and_then(J::as_str)).map(str::to_string);
            let budget = flag(rest, "--budget").and_then(|b| b.parse().ok()).unwrap_or(DEFAULT_BUDGET).min(9_500);
            match restore_text(&fuse_dir(&cwd), sid.as_deref(), budget) {
                None => Ok(String::new()),
                Some(t) if rest.iter().any(|a| a == "--plain") => Ok(t),
                Some(t) => Ok(hook_output(&t)),
            }
        }
        "setup" => run_setup(rest),
        "demo" => run_demo(rest),
        _ => Ok("contextspindle fuse save [--transcript PATH] [--session ID]   (PreCompact hook; reads hook JSON on stdin)\ncontextspindle fuse restore [--plain] [--budget BYTES]         (SessionStart compact hook)\ncontextspindle fuse setup [--project|--settings PATH] [--write] (preview, then write hook config)\ncontextspindle fuse demo [--budget BYTES]                       (offline demo)".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn demo_keeps_all_probes_at_default_budget() {
        let r = run_demo_measure(DEFAULT_BUDGET).unwrap();
        let missing: Vec<_> = DEMO_PROBES.lines().filter(|l| !l.trim().is_empty() && !l.starts_with('#')).zip(&r.hits).filter(|(_, h)| !**h).map(|(p, _)| p).collect();
        assert!(missing.is_empty(), "missing probes: {missing:?}");
        assert!(r.context_bytes <= DEFAULT_BUDGET);
    }

    #[test]
    fn budget_is_enforced_and_goal_survives() {
        let s = extract(DEMO_TRANSCRIPT, None);
        for b in [400, 1000, 2000, 4000] {
            let (t, _) = render(&s, b);
            assert!(t.len() <= b, "budget {b}: {}", t.len());
        }
        let (t, dropped) = render(&s, 1500);
        assert!(t.contains("### Goal"));
        assert!(!dropped.contains(&"goal"));
    }

    #[test]
    fn todo_and_subagent_extraction() {
        let t = r#"{"type":"user","message":{"role":"user","content":"Fix the flaky login test. Don't touch the CI config."}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"a1","name":"Task","input":{"description":"scan auth module"}},{"type":"tool_use","id":"t1","name":"TodoWrite","input":{"todos":[{"content":"reproduce","status":"completed"},{"content":"patch retry","status":"in_progress"}]}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"a1","content":[{"type":"text","text":"Token refresh races with logout in session.rs:88"}]}]}}
{"type":"assistant","message":{"role":"assistant","content":"Root cause is the refresh race, so we chose a mutex instead of retries."}}"#;
        let s = extract(t, None);
        assert_eq!(s.goal, "Fix the flaky login test. Don't touch the CI config.");
        assert_eq!(s.open_tasks, vec!["[in_progress] patch retry".to_string()]);
        assert_eq!(s.done_tasks, 1);
        assert!(s.subagent_results[0].contains("session.rs:88"));
        assert!(s.decisions[0].contains("mutex"));
        assert!(s.constraints.iter().any(|c| c.contains("CI config")));
    }

    #[test]
    fn goal_carries_over_across_compactions_and_ledger_checksums() {
        let dir = std::env::temp_dir().join(format!("cs-fuse-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        save(&dir, "s1", "auto", r#"{"role":"user","content":"Original goal: migrate billing to v2"}"#).unwrap();
        let s2 = save(&dir, "s1", "auto", r#"{"role":"user","content":"continue please"}"#).unwrap();
        assert_eq!(s2.goal, "Original goal: migrate billing to v2");
        // tamper with the second entry; it must be ignored
        let p = dir.join("ledger.jsonl");
        let raw = std::fs::read_to_string(&p).unwrap();
        std::fs::write(&p, raw.replacen("continue please", "evil", 1)).unwrap();
        assert_eq!(read_ledger(&dir).len(), 1);
        let txt = restore_text(&dir, Some("s1"), 3000).unwrap();
        assert!(txt.contains("migrate billing"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn setup_merge_is_idempotent_and_preserves_existing() {
        let existing = r#"{"model":"opus","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"x"}]}]}}"#;
        let (a, changed) = merge_settings(existing, "/bin/cs").unwrap();
        assert!(changed);
        assert!(a.contains("\"PreToolUse\"") && a.contains("\"model\": \"opus\""));
        assert!(a.contains("\"compact\"") && a.contains("\"PreCompact\""));
        let (b, changed2) = merge_settings(&a, "/bin/cs").unwrap();
        assert!(!changed2);
        assert_eq!(a, b);
    }

    #[test]
    fn hook_output_is_valid_json() {
        let out = hook_output("line \"1\"\nline 2");
        let v = parse_json(&out).unwrap();
        assert_eq!(v.get_path(&["hookSpecificOutput", "additionalContext"]).and_then(J::as_str), Some("line \"1\"\nline 2"));
    }
}
