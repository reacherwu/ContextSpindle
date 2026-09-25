//! Git hook for ContextSpindle memory engine.
//!
//! Automatically captures git commits, author, messages, and modified files
//! into the bounded memory manifold on every `git commit`.

use std::fs::File;
use std::io::Read;
use std::path::PathBuf;
use std::process::Command;

const HOOK_START_MARKER: &str = "# CONTINUUM_GIT_HOOK_START";
const HOOK_END_MARKER: &str = "# CONTINUUM_GIT_HOOK_END";

const HOOK_SCRIPT_SNIPPET: &str = r#"
# CONTINUUM_GIT_HOOK_START
# ContextSpindle: ingest git commits into bounded memory
if command -v contextspindle >/dev/null 2>&1; then
  contextspindle hook post-commit >/dev/null 2>&1 || true
elif [ -x "$HOME/.cargo/bin/contextspindle" ]; then
  "$HOME/.cargo/bin/contextspindle" hook post-commit >/dev/null 2>&1 || true
elif command -v continuum-cli >/dev/null 2>&1; then
  continuum-cli hook post-commit >/dev/null 2>&1 || true
elif [ -x "$HOME/.cargo/bin/continuum-cli" ]; then
  "$HOME/.cargo/bin/continuum-cli" hook post-commit >/dev/null 2>&1 || true
fi
# CONTINUUM_GIT_HOOK_END
"#;

pub fn find_git_dir(start: &str) -> Option<PathBuf> {
    let mut cur = PathBuf::from(start);
    if cur.is_relative() {
        cur = std::env::current_dir().ok()?.join(cur);
    }
    loop {
        let git_candidate = cur.join(".git");
        if git_candidate.is_dir() {
            return Some(git_candidate);
        }
        if !cur.pop() {
            break;
        }
    }
    None
}

pub fn run_hook_install(target_dir: &str) {
    let git_dir = match find_git_dir(target_dir) {
        Some(d) => d,
        None => {
            eprintln!("Error: No .git repository found in '{}' or its parent directories.", target_dir);
            return;
        }
    };

    let hooks_dir = git_dir.join("hooks");
    if let Err(e) = std::fs::create_dir_all(&hooks_dir) {
        eprintln!("Failed to create hooks directory '{}': {e}", hooks_dir.display());
        return;
    }

    let post_commit_path = hooks_dir.join("post-commit");
    let mut existing = String::new();
    if post_commit_path.exists() {
        if let Ok(mut f) = File::open(&post_commit_path) {
            let _ = f.read_to_string(&mut existing);
        }
    }

    if existing.contains(HOOK_START_MARKER) {
        println!("ContextSpindle Git hook is already installed in '{}'", post_commit_path.display());
        return;
    }

    let mut new_content = existing.clone();
    if new_content.trim().is_empty() {
        new_content = String::from("#!/bin/sh\n");
    } else if !new_content.ends_with('\n') {
        new_content.push('\n');
    }
    new_content.push_str(HOOK_SCRIPT_SNIPPET);

    if let Err(e) = std::fs::write(&post_commit_path, new_content) {
        eprintln!("Failed to write hook file '{}': {e}", post_commit_path.display());
        return;
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let perms = std::fs::Permissions::from_mode(0o755);
        let _ = std::fs::set_permissions(&post_commit_path, perms);
    }

    println!("============================================================================");
    println!("  CONTEXTSPINDLE GIT HOOK INSTALLED");
    println!("============================================================================");
    println!("Hook Path: '{}'", post_commit_path.display());
    println!("Behavior:  Every 'git commit' will now automatically ingest commit hashes,");
    println!("           authors, messages, and modified config files into ContextSpindle memory.");
    println!("Status:    Active (0 prompt friction)");
    println!("============================================================================");
}

pub fn run_hook_uninstall(target_dir: &str) {
    let git_dir = match find_git_dir(target_dir) {
        Some(d) => d,
        None => {
            eprintln!("Error: No .git repository found in '{}'", target_dir);
            return;
        }
    };

    let post_commit_path = git_dir.join("hooks").join("post-commit");
    if !post_commit_path.exists() {
        println!("No post-commit hook found at '{}'", post_commit_path.display());
        return;
    }

    let content = match std::fs::read_to_string(&post_commit_path) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to read hook file: {e}");
            return;
        }
    };

    if !content.contains(HOOK_START_MARKER) {
        println!("Continuum hook not present in '{}'", post_commit_path.display());
        return;
    }

    let start_idx = content.find(HOOK_START_MARKER).unwrap();
    let end_idx = content.find(HOOK_END_MARKER).map(|i| i + HOOK_END_MARKER.len()).unwrap_or(content.len());

    let mut remaining = String::new();
    remaining.push_str(&content[..start_idx]);
    if end_idx < content.len() {
        remaining.push_str(&content[end_idx..]);
    }

    let trimmed = remaining.trim();
    if trimmed.is_empty() || trimmed == "#!/bin/sh" {
        let _ = std::fs::remove_file(&post_commit_path);
        println!("✅ Removed empty hook file '{}'", post_commit_path.display());
    } else {
        let _ = std::fs::write(&post_commit_path, remaining);
        println!("✅ Uninstalled Continuum hook from '{}'", post_commit_path.display());
    }
}

pub fn run_hook_post_commit(state_path: &str) {
    // 1. Extract latest commit metadata via git CLI
    let git_log = Command::new("git")
        .args(&["log", "-1", "--pretty=format:%h%x09%an%x09%s"])
        .output();

    let (hash, author, message) = match git_log {
        Ok(out) if out.status.success() => {
            let s = String::from_utf8_lossy(&out.stdout).to_string();
            let parts: Vec<&str> = s.split('\t').collect();
            if parts.len() >= 3 {
                (parts[0].to_string(), parts[1].to_string(), parts[2].to_string())
            } else {
                ("HEAD".to_string(), "unknown".to_string(), s)
            }
        }
        _ => return,
    };

    // 2. Extract list of modified files
    let git_diff = Command::new("git")
        .args(&["diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD"])
        .output();

    let files_summary = match git_diff {
        Ok(out) if out.status.success() => {
            let raw = String::from_utf8_lossy(&out.stdout);
            let files: Vec<&str> = raw.lines().take(8).collect();
            files.join(", ")
        }
        _ => "none".to_string(),
    };

    let record = format!(
        "GIT_COMMIT: [{}] by {}: '{}' | modified: [{}]",
        hash, author, message, files_summary
    );

    match crate::run_memory_ingest(&record, state_path) {
        Ok(()) => println!("✅ Continuum auto-ingested git commit [{}] into memory manifold", hash),
        Err(e) => eprintln!("⚠️ Continuum failed to ingest git commit [{}]: {}", hash, e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_git_hook_install_and_uninstall() {
        let temp_dir = std::env::temp_dir().join(format!("continuum_git_test_{}", std::process::id()));
        let git_dir = temp_dir.join(".git");
        std::fs::create_dir_all(&git_dir).unwrap();

        run_hook_install(temp_dir.to_str().unwrap());

        let hook_file = git_dir.join("hooks").join("post-commit");
        assert!(hook_file.exists());
        let content = std::fs::read_to_string(&hook_file).unwrap();
        assert!(content.contains(HOOK_START_MARKER));
        assert!(content.contains("contextspindle hook post-commit"));

        // Test uninstall
        run_hook_uninstall(temp_dir.to_str().unwrap());
        assert!(!hook_file.exists());

        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
