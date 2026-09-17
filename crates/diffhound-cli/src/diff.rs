//! Pure Rust Unified Diff Parser for DiffHound.
//!
//! Parses git diff output into structured files, hunks, and deleted/added blocks
//! with zero external dependencies.

use std::process::Command;

#[derive(Debug, Clone, PartialEq)]
pub struct DiffHunk {
    pub old_start: usize,
    pub old_lines: usize,
    pub new_start: usize,
    pub new_lines: usize,
    pub deleted_lines: Vec<String>,
    pub added_lines: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FileDiff {
    pub path: String,
    pub is_new: bool,
    pub is_deleted: bool,
    pub hunks: Vec<DiffHunk>,
}

#[allow(dead_code)]
impl FileDiff {
    pub fn all_deleted_text(&self) -> String {
        let mut out = String::new();
        for h in &self.hunks {
            for line in &h.deleted_lines {
                out.push_str(line);
                out.push('\n');
            }
        }
        out
    }

    pub fn all_added_text(&self) -> String {
        let mut out = String::new();
        for h in &self.hunks {
            for line in &h.added_lines {
                out.push_str(line);
                out.push('\n');
            }
        }
        out
    }

    pub fn summary(&self) -> String {
        let total_del: usize = self.hunks.iter().map(|h| h.deleted_lines.len()).sum();
        let total_add: usize = self.hunks.iter().map(|h| h.added_lines.len()).sum();
        format!("{}: +{} -{} ({} hunks)", self.path, total_add, total_del, self.hunks.len())
    }
}

pub fn parse_unified_diff(diff_str: &str) -> Vec<FileDiff> {
    let mut files: Vec<FileDiff> = Vec::new();
    let mut cur_file: Option<FileDiff> = None;
    let mut cur_hunk: Option<DiffHunk> = None;

    for line in diff_str.lines() {
        if line.starts_with("diff --git ") {
            // Flush current hunk and file
            if let Some(hunk) = cur_hunk.take() {
                if let Some(ref mut f) = cur_file {
                    f.hunks.push(hunk);
                }
            }
            if let Some(f) = cur_file.take() {
                files.push(f);
            }

            // Parse file path from diff --git a/path b/path
            let parts: Vec<&str> = line.split_whitespace().collect();
            let raw_path = if parts.len() >= 4 {
                parts[3].trim_start_matches("b/")
            } else {
                "unknown"
            };

            cur_file = Some(FileDiff {
                path: raw_path.to_string(),
                is_new: false,
                is_deleted: false,
                hunks: Vec::new(),
            });
        } else if line.starts_with("new file mode ") {
            if let Some(ref mut f) = cur_file {
                f.is_new = true;
            }
        } else if line.starts_with("deleted file mode ") {
            if let Some(ref mut f) = cur_file {
                f.is_deleted = true;
            }
        } else if line.starts_with("@@ ") {
            // New hunk header, e.g. @@ -10,5 +10,8 @@
            if let Some(hunk) = cur_hunk.take() {
                if let Some(ref mut f) = cur_file {
                    f.hunks.push(hunk);
                }
            }

            let (old_start, old_lines, new_start, new_lines) = parse_hunk_header(line);
            cur_hunk = Some(DiffHunk {
                old_start,
                old_lines,
                new_start,
                new_lines,
                deleted_lines: Vec::new(),
                added_lines: Vec::new(),
            });
        } else if let Some(ref mut hunk) = cur_hunk {
            if line.starts_with('+') && !line.starts_with("+++ ") {
                hunk.added_lines.push(line[1..].to_string());
            } else if line.starts_with('-') && !line.starts_with("--- ") {
                hunk.deleted_lines.push(line[1..].to_string());
            }
        }
    }

    if let Some(hunk) = cur_hunk.take() {
        if let Some(ref mut f) = cur_file {
            f.hunks.push(hunk);
        }
    }
    if let Some(f) = cur_file.take() {
        files.push(f);
    }

    files
}

fn parse_hunk_header(header: &str) -> (usize, usize, usize, usize) {
    // Expected format: @@ -old_start,old_lines +new_start,new_lines @@
    let mut old_start = 1;
    let mut old_lines = 1;
    let mut new_start = 1;
    let mut new_lines = 1;

    let parts: Vec<&str> = header.split_whitespace().collect();
    for part in parts {
        if part.starts_with('-') {
            let nums: Vec<&str> = part[1..].split(',').collect();
            if let Some(s) = nums.get(0).and_then(|x| x.parse::<usize>().ok()) {
                old_start = s;
            }
            if let Some(l) = nums.get(1).and_then(|x| x.parse::<usize>().ok()) {
                old_lines = l;
            }
        } else if part.starts_with('+') {
            let nums: Vec<&str> = part[1..].split(',').collect();
            if let Some(s) = nums.get(0).and_then(|x| x.parse::<usize>().ok()) {
                new_start = s;
            }
            if let Some(l) = nums.get(1).and_then(|x| x.parse::<usize>().ok()) {
                new_lines = l;
            }
        }
    }

    (old_start, old_lines, new_start, new_lines)
}

pub fn get_git_diff(base: Option<&str>, head: Option<&str>) -> Result<String, String> {
    let mut cmd = Command::new("git");
    cmd.arg("diff");

    match (base, head) {
        (Some(b), Some(h)) => {
            cmd.arg(format!("{}...{}", b, h));
        }
        (Some(b), None) => {
            cmd.arg(b);
        }
        (None, None) => {
            // Default: staged diff or unstaged diff against HEAD
            cmd.arg("HEAD");
        }
        (None, Some(h)) => {
            cmd.arg("HEAD").arg(h);
        }
    }

    let out = cmd.output().map_err(|e| format!("Failed to execute 'git diff': {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("git diff error: {err}"));
    }

    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_unified_diff() {
        let sample = r#"
diff --git a/crates/net/src/client.rs b/crates/net/src/client.rs
index 1234567..89abcdef 100644
--- a/crates/net/src/client.rs
+++ b/crates/net/src/client.rs
@@ -45,3 +45,2 @@ pub struct ClientBuilder {
-    legacy_cipher_fallback: bool,
-    sec_level: u32,
+    tls_13_only: bool,
"#;
        let files = parse_unified_diff(sample);
        assert_eq!(files.len(), 1);
        let f = &files[0];
        assert_eq!(f.path, "crates/net/src/client.rs");
        assert_eq!(f.hunks.len(), 1);
        let h = &f.hunks[0];
        assert_eq!(h.deleted_lines.len(), 2);
        assert_eq!(h.added_lines.len(), 1);
        assert_eq!(h.deleted_lines[0], "    legacy_cipher_fallback: bool,");
        assert_eq!(h.added_lines[0], "    tls_13_only: bool,");
    }
}
