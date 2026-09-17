//! Real subprocess checks; all state and synthetic output stay in isolated temp directories.
#![cfg(unix)]

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

const PENDING: &str = ".continuum/pending_observation.json";
const RECOVERY: &str = ".continuum/recovery_observation.json";
static NEXT: AtomicU64 = AtomicU64::new(0);

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "continuum-runner-safety-{}-{}",
            std::process::id(), NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        fs::create_dir(path.join("home")).unwrap();
        Self(path)
    }
    fn run(&self, cwd: &Path, args: &[&str]) -> Output {
        Command::new(env!("CARGO_BIN_EXE_continuum-cli"))
            .arg("run").args(args).current_dir(cwd)
            .env_clear().env("HOME", self.0.join("home"))
            .env("PATH", "/usr/bin:/bin")
            .env("SYNTHETIC_RUNNER_VALUE", "synthetic-environment-value")
            .output().unwrap()
    }
    fn shell(&self, script: &str) -> Output {
        self.run(&self.0, &["/bin/sh", "-c", script])
    }
    fn read(&self, name: &str) -> String {
        fs::read_to_string(self.0.join(name)).unwrap()
    }
    fn assert_no_memory(&self) {
        assert!(!self.0.join(".continuum/memory.state").exists());
        assert!(!self.0.join("home/.continuum/agent_memory.state").exists());
    }
}
impl Drop for Workspace {
    fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
}

#[test]
fn unrelated_success_never_becomes_a_fix() {
    let w = Workspace::new();
    assert_eq!(w.shell("exit 23").status.code(), Some(23));
    assert!(w.shell("exit 0").status.success());
    w.assert_no_memory();
    assert!(w.0.join(PENDING).exists());
    assert!(!w.0.join(RECOVERY).exists());
}

#[test]
fn identical_command_recovery_is_only_an_observation() {
    let w = Workspace::new();
    let command = "test -f ready";
    assert_eq!(w.shell(command).status.code(), Some(1));
    fs::write(w.0.join("ready"), b"").unwrap();
    assert!(w.shell(command).status.success());
    let recovery = w.read(RECOVERY);
    assert!(recovery.contains("\"kind\":\"recovery_observation\""));
    assert!(recovery.contains("\"verified_cause\":false"));
    assert!(!w.0.join(PENDING).exists());
    w.assert_no_memory();
}

#[test]
fn output_is_byte_exact_and_not_retained_or_repeated_in_diagnostics() {
    let w = Workspace::new();
    let output = w.shell("printf 'synthetic-output\\377'; printf 'synthetic-stderr' >&2; exit 7");
    assert_eq!(output.status.code(), Some(7));
    assert_eq!(output.stdout, b"synthetic-output\xff");
    assert_eq!(String::from_utf8_lossy(&output.stderr).matches("synthetic-stderr").count(), 1);
    let incident = w.read(PENDING);
    for raw in ["synthetic-output", "synthetic-stderr", "synthetic-environment-value", "printf", "exit 7"] {
        assert!(!incident.contains(raw));
    }
    assert!(incident.len() <= 1024);
    w.assert_no_memory();
}

#[test]
fn executes_exact_arguments_once_without_shell_reinterpretation() {
    let w = Workspace::new();
    let output = w.run(&w.0, &["/usr/bin/printf", "%s|%s", "one two", "$SYNTHETIC_RUNNER_VALUE"]);
    assert!(output.status.success());
    assert_eq!(output.stdout, b"one two|$SYNTHETIC_RUNNER_VALUE");
    let failed = w.shell("printf x >> attempts; exit 19");
    assert_eq!(failed.status.code(), Some(19));
    assert_eq!(fs::read(w.0.join("attempts")).unwrap(), b"x");
}

#[test]
fn copied_observation_cannot_correlate_across_projects() {
    let a = Workspace::new();
    let b = Workspace::new();
    let command = "test -f ready";
    assert!(!a.shell(command).status.success());
    fs::create_dir(b.0.join(".continuum")).unwrap();
    fs::copy(a.0.join(PENDING), b.0.join(PENDING)).unwrap();
    fs::write(b.0.join("ready"), b"").unwrap();
    assert!(b.shell(command).status.success());
    assert!(!b.0.join(RECOVERY).exists());
    b.assert_no_memory();
}

#[test]
fn canonical_project_alias_correlates_but_different_working_directory_does_not() {
    let w = Workspace::new();
    let command = "test -f ready";
    assert!(!w.shell(command).status.success());
    let subdir = w.0.join("subdir");
    fs::create_dir(&subdir).unwrap();
    fs::write(subdir.join("ready"), b"").unwrap();
    assert!(w.run(&subdir, &["/bin/sh", "-c", command]).status.success());
    assert!(!w.0.join(RECOVERY).exists());
    let alias = w.0.join("alias");
    std::os::unix::fs::symlink(&w.0, &alias).unwrap();
    fs::write(w.0.join("ready"), b"").unwrap();
    assert!(w.run(&alias, &["/bin/sh", "-c", command]).status.success());
    assert!(w.0.join(RECOVERY).exists());
}

#[test]
fn observation_storage_failure_does_not_override_child_status() {
    let w = Workspace::new();
    fs::write(w.0.join(".continuum"), b"not a directory").unwrap();
    assert_eq!(w.shell("exit 31").status.code(), Some(31));
    assert!(w.shell("exit 0").status.success());
    w.assert_no_memory();
}

#[test]
fn argument_boundaries_are_part_of_identity() {
    let w = Workspace::new();
    let command = "test -f ready";
    assert!(!w.run(&w.0, &["/bin/sh", "-c", command, "one two"]).status.success());
    fs::write(w.0.join("ready"), b"").unwrap();
    assert!(w.run(&w.0, &["/bin/sh", "-c", command, "one", "two"]).status.success());
    assert!(!w.0.join(RECOVERY).exists());
    assert!(w.run(&w.0, &["/bin/sh", "-c", command, "one two"]).status.success());
    assert!(w.0.join(RECOVERY).exists());
}

#[test]
fn expired_and_oversize_observations_are_discarded_without_recovery() {
    let w = Workspace::new();
    let command = "test -f ready";
    assert!(!w.shell(command).status.success());
    let mut pending = w.read(PENDING);
    let start = pending.find("\"failed_at\":").unwrap() + "\"failed_at\":".len();
    let end = start + pending[start..].find(',').unwrap();
    pending.replace_range(start..end, "1");
    fs::write(w.0.join(PENDING), pending).unwrap();
    fs::write(w.0.join("ready"), b"").unwrap();
    assert!(w.shell(command).status.success());
    assert!(!w.0.join(PENDING).exists());
    assert!(!w.0.join(RECOVERY).exists());
    fs::write(w.0.join(PENDING), vec![b' '; 2048]).unwrap();
    assert!(w.shell(command).status.success());
    assert!(!w.0.join(PENDING).exists());
    assert!(!w.0.join(RECOVERY).exists());
    w.assert_no_memory();
}

#[test]
fn legacy_raw_incident_is_discarded_not_migrated() {
    let w = Workspace::new();
    fs::create_dir(w.0.join(".continuum")).unwrap();
    let legacy = w.0.join(".continuum/pending_incident.json");
    fs::write(&legacy, b"synthetic old observation").unwrap();
    assert!(w.shell("exit 0").status.success());
    assert!(!legacy.exists());
    assert!(!w.0.join(RECOVERY).exists());
    w.assert_no_memory();
}

#[test]
fn missing_program_returns_127_without_echoing_its_argument() {
    let w = Workspace::new();
    let output = w.run(&w.0, &["/synthetic-nonexistent-program", "synthetic-argument"]);
    assert_eq!(output.status.code(), Some(127));
    assert!(!String::from_utf8_lossy(&output.stderr).contains("synthetic-argument"));
    assert!(!w.0.join(PENDING).exists());
    w.assert_no_memory();
}

#[test]
fn many_failures_have_bounded_retained_size() {
    let w = Workspace::new();
    for i in 0..40 {
        assert_eq!(w.shell(&format!("exit 3 # synthetic-{i}")).status.code(), Some(3));
    }
    let files: Vec<_> = fs::read_dir(w.0.join(".continuum")).unwrap().map(Result::unwrap).collect();
    assert!(files.len() <= 4);
    assert!(files.iter().map(|f| f.metadata().unwrap().len()).sum::<u64>() <= 2048);
    assert!(w.read(PENDING).contains("\"kind\":\"failure_observation\""));
    w.assert_no_memory();
}
