//! Zero-Friction Autonomous Command Runner for Continuum.
//!
//! Wraps build, test, and execution commands (e.g. `continuum run cargo test`).
//! Automatically tracks failure symptoms and pairs them with subsequent successful
//! fixes into causal anchor memories with zero human prompting.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc::channel;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

const INCIDENT_FILE: &str = ".continuum/pending_incident.json";

#[derive(Debug, Clone)]
pub struct PendingIncident {
    pub command: String,
    pub timestamp: u64,
    pub symptom: String,
    pub exit_code: i32,
}

impl PendingIncident {
    pub fn save(&self, path: impl AsRef<Path>) -> std::io::Result<()> {
        let parent = path.as_ref().parent().unwrap_or_else(|| Path::new("."));
        let _ = std::fs::create_dir_all(parent);

        let clean_cmd = self.command.replace('\\', "\\\\").replace('"', "\\\"");
        let clean_sym = self.symptom.replace('\\', "\\\\").replace('"', "\\\"").replace('\n', "\\n");

        let json = format!(
            r#"{{"command":"{}","timestamp":{},"symptom":"{}","exit_code":{}}}"#,
            clean_cmd, self.timestamp, clean_sym, self.exit_code
        );
        std::fs::write(path, json)
    }

    pub fn load(path: impl AsRef<Path>) -> Option<Self> {
        let content = std::fs::read_to_string(path).ok()?;
        let json = crate::json::parse_json(&content).ok()?;
        Some(Self {
            command: json.get("command").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            timestamp: json.get("timestamp").and_then(|v| v.as_u64()).unwrap_or(0),
            symptom: json.get("symptom").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            exit_code: json.get("exit_code").and_then(|v| v.as_i64()).unwrap_or(1) as i32,
        })
    }
}

pub fn run_command(args: &[String], state_path: &str) -> i32 {
    if args.is_empty() {
        eprintln!("Usage: continuum run <command> [args...]");
        return 1;
    }

    let cmd_name = &args[0];
    let cmd_args = &args[1..];
    let full_cmd_str = args.join(" ");

    let mut child = match Command::new(cmd_name)
        .args(cmd_args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to execute '{}': {e}", cmd_name);
            return 127;
        }
    };

    let stdout_pipe = child.stdout.take().expect("Failed to capture stdout");
    let stderr_pipe = child.stderr.take().expect("Failed to capture stderr");

    let (stdout_tx, stdout_rx) = channel();
    let (stderr_tx, stderr_rx) = channel();

    // Spawn thread to stream stdout and retain trailing lines
    let stdout_thread = thread::spawn(move || {
        let reader = BufReader::new(stdout_pipe);
        let mut lines = Vec::new();
        for line_res in reader.lines() {
            if let Ok(line) = line_res {
                println!("{}", line);
                lines.push(line);
                if lines.len() > 30 {
                    lines.remove(0);
                }
            }
        }
        let _ = stdout_tx.send(lines);
    });

    // Spawn thread to stream stderr and retain trailing lines
    let stderr_thread = thread::spawn(move || {
        let reader = BufReader::new(stderr_pipe);
        let mut lines = Vec::new();
        for line_res in reader.lines() {
            if let Ok(line) = line_res {
                eprintln!("{}", line);
                lines.push(line);
                if lines.len() > 30 {
                    lines.remove(0);
                }
            }
        }
        let _ = stderr_tx.send(lines);
    });

    let status = child.wait().expect("Child process wasn't running");
    let _ = stdout_thread.join();
    let _ = stderr_thread.join();

    let stdout_lines = stdout_rx.recv().unwrap_or_default();
    let stderr_lines = stderr_rx.recv().unwrap_or_default();

    let exit_code = status.code().unwrap_or(1);
    let incident_path = PathBuf::from(INCIDENT_FILE);

    if exit_code != 0 {
        // Command failed: extract failure symptom and sanitize immediately
        let raw_symptom = extract_symptom(&stderr_lines, &stdout_lines);
        let symptom = sanitize_log_text(&raw_symptom, 300);
        let sanitized_cmd = sanitize_log_text(&full_cmd_str, 500);
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();

        let incident = PendingIncident {
            command: sanitized_cmd,
            timestamp: now,
            symptom: symptom.clone(),
            exit_code,
        };

        if let Err(e) = incident.save(&incident_path) {
            eprintln!("Warning: Failed to save pending incident: {e}");
        } else {
            eprintln!("\n⚠️  Continuum: Incident captured in '{INCIDENT_FILE}'");
            eprintln!("   Symptom: '{}'", symptom);
            eprintln!("   (Once fixed and re-run successfully, Continuum will auto-ingest the causal pair!)\n");
        }
    } else {
        // Command succeeded: check if resolving a prior failure of the SAME command
        if incident_path.exists() {
            if let Some(prior) = PendingIncident::load(&incident_path) {
                let prior_base = prior.command.split_whitespace().next().unwrap_or("");
                let cur_base = full_cmd_str.split_whitespace().next().unwrap_or("");

                // Only pair if command executable matches (e.g. both are cargo test or both are pytest)
                if !prior_base.is_empty() && prior_base == cur_base {
                    let clean_symptom = sanitize_log_text(&prior.symptom, 220);
                    let causal_pair = format!(
                        "CANDIDATE_FIX: Command '{}' failed with ('{}'), observed resolved via '{}'",
                        prior.command, clean_symptom, full_cmd_str
                    );

                    let _ = crate::run_memory_ingest(&causal_pair, state_path);
                    let _ = std::fs::remove_file(&incident_path);

                    println!("\n🎉 Continuum: Autonomous Causal Candidate Ingested");
                    println!("   Command:        '{}'", prior.command);
                    println!("   Prior Symptom:  '{}'", clean_symptom);
                    println!("   Status:         Observed recovery verified.\n");
                }
            }
        }
    }

    exit_code
}

fn sanitize_log_text(s: &str, max_len: usize) -> String {
    let mut words = Vec::new();
    let mut redact_next = false;

    for word in s.split_whitespace() {
        let clean_word = word.trim_matches(|c| c == '\'' || c == '"' || c == '(' || c == ')' || c == '[' || c == ']');
        let lower = clean_word.to_lowercase();
        if redact_next {
            words.push("[REDACTED_SECRET]".to_string());
            redact_next = false;
            continue;
        }

        if lower == "bearer" || lower == "token" || lower == "password" {
            words.push(word.to_string());
            redact_next = true;
        } else if lower.starts_with("eyj")
            || lower.contains("password=")
            || lower.contains("passwd=")
            || lower.contains("secret=")
            || lower.contains("api_key=")
            || lower.contains("apikey=")
            || lower.contains("token=")
        {
            words.push("[REDACTED_SECRET]".to_string());
        } else {
            words.push(word.to_string());
        }
    }

    let cleaned = words.join(" ");
    if cleaned.chars().count() > max_len {
        format!("{}...", cleaned.chars().take(max_len).collect::<String>())
    } else {
        cleaned
    }
}

fn extract_symptom(stderr: &[String], stdout: &[String]) -> String {
    // Prefer stderr lines containing error markers
    for line in stderr.iter().rev() {
        let lower = line.to_lowercase();
        if lower.contains("error:") || lower.contains("fail") || lower.contains("panic") || lower.contains("fatal:") {
            return line.trim().to_string();
        }
    }
    // Check stdout lines for test failures or assertion errors
    for line in stdout.iter().rev() {
        let lower = line.to_lowercase();
        if lower.contains("failed") || lower.contains("assertionerror") || lower.contains("panic") || lower.contains("error:") {
            return line.trim().to_string();
        }
    }
    // Fallback to last line of stderr or stdout
    if let Some(last) = stderr.last() {
        if !last.trim().is_empty() {
            return last.trim().to_string();
        }
    }
    if let Some(last) = stdout.last() {
        if !last.trim().is_empty() {
            return last.trim().to_string();
        }
    }
    "Unknown command failure".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pending_incident_roundtrip() {
        let temp_dir = std::env::temp_dir();
        let path = temp_dir.join(format!("incident_test_{}.json", std::process::id()));

        let incident = PendingIncident {
            command: "cargo test --test auth".to_string(),
            timestamp: 1789500000,
            symptom: "error[E0432]: unresolved import `crate::auth`".to_string(),
            exit_code: 101,
        };

        incident.save(&path).expect("Failed save");
        let loaded = PendingIncident::load(&path).expect("Failed load");

        assert_eq!(loaded.command, incident.command);
        assert_eq!(loaded.timestamp, incident.timestamp);
        assert_eq!(loaded.symptom, incident.symptom);
        assert_eq!(loaded.exit_code, incident.exit_code);

        let _ = std::fs::remove_file(&path);
    }
}
