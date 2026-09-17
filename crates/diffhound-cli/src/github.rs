//! Zero-Dependency GitHub REST API Client for DiffHound.
//!
//! Interacts with GitHub Pull Requests and Checks API via standard curl invocation,
//! ensuring robust TLS connection without linking bulky external C/SSL libraries.

use std::process::Command;

pub fn escape_json_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 16);
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if c < ' ' => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

pub fn post_pr_comment(
    token: &str,
    repo: &str,
    pr_number: u64,
    body: &str,
) -> Result<(), String> {
    let url = format!("https://api.github.com/repos/{}/issues/{}/comments", repo, pr_number);
    let payload = format!(r#"{{"body":"{}"}}"#, escape_json_str(body));

    let out = Command::new("curl")
        .args(&[
            "-s",
            "-X", "POST",
            "-H", &format!("Authorization: Bearer {}", token),
            "-H", "Accept: application/vnd.github+json",
            "-H", "User-Agent: DiffHound-App",
            "-H", "Content-Type: application/json",
            "--data", &payload,
            &url,
        ])
        .output()
        .map_err(|e| format!("Failed to execute curl: {e}"))?;

    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("curl error posting comment: {err}"));
    }

    let resp = String::from_utf8_lossy(&out.stdout);
    if resp.contains(r#""message""#) && resp.contains(r#""Not Found""#) {
        return Err(format!("GitHub API error: {resp}"));
    }

    Ok(())
}

pub fn create_check_run(
    token: &str,
    repo: &str,
    head_sha: &str,
    title: &str,
    summary: &str,
    conclusion: &str, // "success" or "failure"
) -> Result<(), String> {
    let url = format!("https://api.github.com/repos/{}/check-runs", repo);
    let payload = format!(
        r#"{{"name":"DiffHound Regression Gate","head_sha":"{}","status":"completed","conclusion":"{}","output":{{"title":"{}","summary":"{}"}}}}"#,
        head_sha,
        conclusion,
        escape_json_str(title),
        escape_json_str(summary)
    );

    let out = Command::new("curl")
        .args(&[
            "-s",
            "-X", "POST",
            "-H", &format!("Authorization: Bearer {}", token),
            "-H", "Accept: application/vnd.github+json",
            "-H", "User-Agent: DiffHound-App",
            "-H", "Content-Type: application/json",
            "--data", &payload,
            &url,
        ])
        .output()
        .map_err(|e| format!("Failed to execute curl: {e}"))?;

    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("curl error creating check run: {err}"));
    }

    Ok(())
}

pub fn fetch_pr_diff(
    token: &str,
    repo: &str,
    pr_number: u64,
) -> Result<String, String> {
    let url = format!("https://api.github.com/repos/{}/pulls/{}", repo, pr_number);

    let mut cmd = Command::new("curl");
    cmd.args(&[
        "-s",
        "-L",
        "-H", "Accept: application/vnd.github.v3.diff",
        "-H", "User-Agent: DiffHound-App",
    ]);

    if !token.is_empty() {
        cmd.arg("-H").arg(format!("Authorization: Bearer {}", token));
    }
    cmd.arg(&url);

    let out = cmd.output().map_err(|e| format!("Failed to execute curl: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("curl error fetching diff: {err}"));
    }

    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_escape_json_str() {
        let s = "line 1\nline 2 \"quoted\" \\ slash";
        let escaped = escape_json_str(s);
        assert_eq!(escaped, "line 1\\nline 2 \\\"quoted\\\" \\\\ slash");
    }
}
