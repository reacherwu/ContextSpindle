//! Memory CLI parsing, deliberately separate from storage and MCP transport.
use crate::memory_api::{self as api, ApiError, Result};

pub fn arity(args: &[String], min: usize, max: usize, usage: &str) -> Result<()> {
    if args.len() < min || args.len() > max { return Err(ApiError::invalid(usage)); }
    Ok(())
}
pub fn run(args: &[String], machine: bool) -> Result<()> {
    let default = crate::default_snapshot_path();
    let sub = args.first().map(String::as_str).unwrap_or("help");
    match sub {
        "ingest" => {
            arity(args, 2, 3, "memory ingest <text> [snapshot] [--json]")?;
            let path = args.get(2).map(String::as_str).unwrap_or(&default);
            let result = api::ingest(&args[1], path)?;
            if machine { println!("{result}"); }
        }
        "query" => {
            arity(args, 2, 4, "memory query <text> [snapshot] [top_k] [--json]")?;
            let path = args.get(2).map(String::as_str).unwrap_or(&default);
            let k = api::top_k(args.get(3).map(String::as_str), 5)?;
            if machine { println!("{}", api::query(&args[1], path, k)?); }
            else { crate::run_memory_query(&args[1], path, k)?; }
        }
        "inspect" | "stats" => {
            arity(args, 1, 2, "memory inspect [snapshot] [--json]")?;
            let path = args.get(1).map(String::as_str).unwrap_or(&default);
            if machine { println!("{}", api::inspect(path)?); }
            else { api::inspect_human(path)?; }
        }
        "check" => {
            arity(args, 2, 2, "memory check <state> [--json]")?;
            println!("{}", api::check(&args[1])?);
        }
        "backup" => {
            arity(args, 3, 3, "memory backup <state> <backup> [--json] (never overwrites)")?;
            println!("{}", api::backup(&args[1], &args[2])?);
        }
        "restore" => {
            arity(args, 3, 4, "memory restore <backup> <state> [--confirm] [--json]")?;
            let confirmed = match args.get(3).map(String::as_str) {
                None => false,
                Some("--confirm") => true,
                Some(_) => return Err(ApiError::invalid("only --confirm permits replacing an existing state")),
            };
            println!("{}", api::restore(&args[1], &args[2], confirmed)?);
        }
        "sync" => {
            arity(args, 2, 3, "memory sync <transcript> [snapshot]")?;
            if machine { return Err(ApiError::invalid("--json supports ingest/query/inspect")); }
            crate::run_memory_sync(&args[1], args.get(2).map(String::as_str).unwrap_or(&default))?;
        }
        "help" | "--help" | "-h" => crate::print_help(),
        _ => return Err(ApiError::invalid("unknown memory command")),
    }
    Ok(())
}
