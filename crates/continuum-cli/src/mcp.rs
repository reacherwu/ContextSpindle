//! Native line-delimited stdio MCP. Tool failures are results with isError, not successes.
use crate::json::{self, JsonValue};
use crate::memory_api::{self as api, ApiError, Result, quote};
use std::io::{self, BufRead, Write};

const TOOLS: &str = r#"{"tools":[{"name":"continuum_remember","description":"Store an event in bounded local memory","inputSchema":{"type":"object","properties":{"text":{"type":"string","minLength":1}},"required":["text"],"additionalProperties":false}},{"name":"continuum_recall","description":"Retrieve ranked memory candidates, with complete stored provenance","inputSchema":{"type":"object","properties":{"query":{"type":"string","minLength":1},"top_k":{"type":"integer","minimum":1,"maximum":10000,"default":3}},"required":["query"],"additionalProperties":false}},{"name":"continuum_stats","description":"Inspect actual local memory usage and records","inputSchema":{"type":"object","properties":{},"additionalProperties":false}}]}"#;

fn rpc_error(id: &str, code: i32, message: &str) -> String {
    format!("{{\"jsonrpc\":\"2.0\",\"id\":{id},\"error\":{{\"code\":{code},\"message\":{}}}}}", quote(message))
}
fn required<'a>(args: &'a JsonValue, field: &str) -> Result<&'a str> {
    args.get(field).and_then(JsonValue::as_str).ok_or_else(|| ApiError::invalid(format!("{field} must be a string")))
}
fn tool_call(request: &JsonValue, path: &str) -> Result<String> {
    let params = request.get("params").ok_or_else(|| ApiError::invalid("params required"))?;
    let name = required(params, "name")?;
    let empty = JsonValue::Object(Vec::new());
    let args = params.get("arguments").unwrap_or(&empty);
    let fields = args.as_object().ok_or_else(|| ApiError::invalid("arguments must be an object"))?;
    let allowed: &[&str] = match name {
        "continuum_remember" => &["text"],
        "continuum_recall" => &["query", "top_k"],
        "continuum_stats" => &[],
        _ => return Err(ApiError::invalid("unknown tool")),
    };
    if fields.iter().any(|(field, _)| !allowed.contains(&field.as_str())) {
        return Err(ApiError::invalid("unknown tool argument"));
    }
    match name {
        "continuum_remember" => api::ingest(required(args, "text")?, path),
        "continuum_recall" => {
            let k = match args.get("top_k") {
                None => 3,
                Some(JsonValue::Number(n)) if n.is_finite() && n.fract() == 0.0 && *n >= 1.0 && *n <= api::MAX_TOP_K as f64 => *n as usize,
                _ => return Err(ApiError::invalid("top_k must be an integer in 1..=10000")),
            };
            api::query(required(args, "query")?, path, k)
        }
        "continuum_stats" => api::inspect(path),
        _ => unreachable!(),
    }
}

fn response(line: &str, path: &str) -> Option<String> {
    let request = match json::parse_json(line) {
        Ok(value) => value,
        Err(_) => return Some(rpc_error("null", -32700, "Parse error")),
    };
    let id = request.get("id");
    let valid_id = match id {
        None | Some(JsonValue::Null) | Some(JsonValue::String(_)) => true,
        Some(JsonValue::Number(n)) => n.is_finite() && n.fract() == 0.0 && n.abs() <= 9_007_199_254_740_991.0,
        _ => false,
    };
    let method = request.get("method").and_then(JsonValue::as_str);
    if request.get("jsonrpc").and_then(JsonValue::as_str) != Some("2.0") || method.is_none() || !valid_id {
        return Some(rpc_error("null", -32600, "Invalid Request"));
    }
    // Notifications never receive replies or execute memory mutations.
    let id = id?.to_json_string();
    let result = match method.unwrap() {
        "initialize" => r#"{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"continuum","version":"0.1.0"}}"#.to_owned(),
        "ping" => "{}".to_owned(),
        "tools/list" => TOOLS.to_owned(),
        "tools/call" => {
            let (content, is_error) = match tool_call(&request, path) {
                Ok(content) => (content, false),
                Err(error) => (error.json(), true),
            };
            format!("{{\"isError\":{is_error},\"content\":[{{\"type\":\"text\",\"text\":{}}}]}}", quote(&content))
        }
        _ => return Some(rpc_error(&id, -32601, "Method not found")),
    };
    Some(format!("{{\"jsonrpc\":\"2.0\",\"id\":{id},\"result\":{result}}}"))
}

pub fn run(path: &str) -> Result<()> {
    let stdin = io::stdin();
    let mut stdout = io::stdout().lock();
    for line in stdin.lock().lines() {
        let line = line?;
        if line.trim().is_empty() { continue; }
        if let Some(message) = response(&line, path) {
            writeln!(stdout, "{message}")?;
            stdout.flush()?;
        }
    }
    Ok(())
}
