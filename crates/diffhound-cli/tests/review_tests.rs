use continuum_core::{ContinuumConfig, ContinuumEngine, RealTextEmbedder};

#[allow(dead_code)]
#[path = "../src/diff.rs"]
mod diff;
#[allow(dead_code)]
#[path = "../src/review.rs"]
mod review;

use diff::parse_unified_diff;
use review::perform_review;

#[test]
fn test_clean_diff_produces_zero_noise() {
    let clean_diff = r#"
diff --git a/docs/README.md b/docs/README.md
index 1234567..89abcdef 100644
--- a/docs/README.md
+++ b/docs/README.md
@@ -1,3 +1,4 @@
 # Documentation
+Welcome to the developer guide.
 Enjoy reading.
"#;
    let file_diffs = parse_unified_diff(clean_diff);
    assert_eq!(file_diffs.len(), 1);

    let mut engine = ContinuumEngine::new(ContinuumConfig::default());
    let report = perform_review(&file_diffs, &mut engine, 0.45);

    assert!(report.is_clean());
    assert_eq!(report.alerts.len(), 0);

    let md = report.to_markdown();
    assert!(md.contains("✅ **0 Regressions Detected** (Zero Noise)"));
    assert!(md.contains("Clean to merge"));
}

#[test]
fn test_regression_detected_on_purged_compatibility() {
    // 1. Setup engine with historical fix
    let mut engine = ContinuumEngine::new(ContinuumConfig::default());
    let embedder = RealTextEmbedder::new(32, 42);

    let historical_anchor = "FIX: [4b8e21a] crates/net/src/client.rs: preserve legacy cipher fallback handler to prevent SSLV3_ALERT_HANDSHAKE_FAILURE";
    let emb = embedder.embed(historical_anchor);
    engine.step(&emb, 100.0, historical_anchor);

    // 2. Incoming PR diff deletes the fallback handler
    let dangerous_diff = r#"
diff --git a/crates/net/src/client.rs b/crates/net/src/client.rs
index abcdef1..1234567 100644
--- a/crates/net/src/client.rs
+++ b/crates/net/src/client.rs
@@ -50,6 +50,3 @@ impl ClientBuilder {
-    // Remove legacy cipher fallback to enforce TLS 1.3
-    pub fn enable_legacy_cipher_fallback(&mut self) {
-        self.cipher_string = "DEFAULT:@SECLEVEL=1:!aNULL".to_string();
-    }
+    pub fn enforce_tls13_only(&mut self) {
+        self.min_version = TlsVersion::Tls13;
+    }
"#;
    let file_diffs = parse_unified_diff(dangerous_diff);
    assert_eq!(file_diffs.len(), 1);

    // 3. Review should catch the regression
    let report = perform_review(&file_diffs, &mut engine, 0.40);
    assert!(!report.is_clean());
    assert_eq!(report.alerts.len(), 1);

    let alert = &report.alerts[0];
    assert_eq!(alert.file_path, "crates/net/src/client.rs");
    assert!(alert.provenance.contains("4b8e21a"));

    let md = report.to_markdown();
    assert!(md.contains("⚠️ Regression Warning"));
    assert!(md.contains("4b8e21a"));
    assert!(md.contains("SSLV3_ALERT_HANDSHAKE_FAILURE"));
}

#[test]
fn test_github_step_summary_output() {
    let clean_diff = r#"
diff --git a/src/lib.rs b/src/lib.rs
--- a/src/lib.rs
+++ b/src/lib.rs
@@ -1,1 +1,2 @@
+// Just a comment
"#;
    let file_diffs = parse_unified_diff(clean_diff);
    let mut engine = ContinuumEngine::new(ContinuumConfig::default());
    let report = perform_review(&file_diffs, &mut engine, 0.45);

    let temp_file = std::env::temp_dir().join(format!("diffhound_summary_test_{}.md", std::process::id()));
    std::env::set_var("GITHUB_STEP_SUMMARY", temp_file.to_str().unwrap());

    report.write_github_step_summary();

    assert!(temp_file.exists());
    let content = std::fs::read_to_string(&temp_file).unwrap();
    assert!(content.contains("DiffHound AI PR Guard: Passed"));

    let _ = std::fs::remove_file(temp_file);
    std::env::remove_var("GITHUB_STEP_SUMMARY");
}
