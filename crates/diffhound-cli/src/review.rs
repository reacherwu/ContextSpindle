//! Zero-Noise Regression Review Engine for DiffHound.
//!
//! Evaluates code diffs against historical causal anchors in bounded memory.
//! Enforces Zero-Noise: 100% silent on safe diffs, laser-focused on regressions.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};

use continuum_core::{
    ContinuumEngine, RealTextEmbedder,
};

use crate::diff::FileDiff;

#[derive(Debug, Clone)]
pub struct RegressionAlert {
    pub file_path: String,
    pub line_number: usize,
    pub score: f32,
    pub provenance: String,
    pub risk_summary: String,
    pub remediation: String,
}

#[derive(Debug, Clone)]
pub struct ReviewReport {
    pub files_scanned: usize,
    pub hunks_scanned: usize,
    pub lines_added: usize,
    pub lines_deleted: usize,
    pub alerts: Vec<RegressionAlert>,
    pub latency_us: f64,
}

impl ReviewReport {
    pub fn is_clean(&self) -> bool {
        self.alerts.is_empty()
    }

    pub fn to_markdown(&self) -> String {
        let mut md = String::new();
        if self.is_clean() {
            md.push_str("### 🐕 DiffHound AI PR Guard: Passed\n\n");
            md.push_str("> **Verdict**: ✅ **0 Regressions Detected** (Zero Noise). Clean to merge.\n\n");
            md.push_str(&format!("- **Files Analyzed**: {} files ({} hunks)\n", self.files_scanned, self.hunks_scanned));
            md.push_str(&format!("- **Code Volume**: +{} / -{} lines\n", self.lines_added, self.lines_deleted));
            md.push_str(&format!("- **Analysis Latency**: {:.2} μs (< 1 ms)\n\n", self.latency_us));
            md.push_str("<sub>⚡ Powered by DiffHound Zero-Noise Anti-Regression Engine</sub>\n");
        } else {
            md.push_str("### 🐕 DiffHound AI PR Guard: ⚠️ Regression Warning\n\n");
            md.push_str("> **Attention**: DiffHound detected changes touching sensitive historical bug fixes.\n\n");
            md.push_str("| File & Location | Causal Score | Historical Commit & Provenance | Remediation Guidance |\n");
            md.push_str("| :--- | :---: | :--- | :--- |\n");

            for a in &self.alerts {
                let loc = format!("`{}:{}`", a.file_path, a.line_number);
                let prov = &a.provenance;
                md.push_str(&format!(
                    "| {} | `{:.4}` | `{}` | **{}**<br><sub>{}</sub> |\n",
                    loc, a.score, prov, a.risk_summary, a.remediation
                ));
            }

            md.push_str("\n> 💡 **Why this matters**: AI coding assistants (Cursor, Claude) frequently delete legacy fallbacks or timing pragmas during refactoring. Verify these constraints before merging.\n\n");
            md.push_str("<sub>⚡ Powered by DiffHound Zero-Noise Anti-Regression Engine</sub>\n");
        }
        md
    }

    pub fn write_github_step_summary(&self) {
        if let Ok(path_str) = std::env::var("GITHUB_STEP_SUMMARY") {
            if !path_str.trim().is_empty() {
                let path = Path::new(&path_str);
                if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
                    let md = self.to_markdown();
                    let _ = writeln!(f, "{}", md);
                }
            }
        }
    }
}

pub fn locate_memory_state() -> Option<PathBuf> {
    // Check .diffhound/memory.state first, then .continuum/memory.state
    let candidates = [
        ".diffhound/memory.state",
        ".continuum/memory.state",
        "../.diffhound/memory.state",
        "../.continuum/memory.state",
    ];
    for c in candidates {
        let p = PathBuf::from(c);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

pub fn perform_review(
    files: &[FileDiff],
    engine: &mut ContinuumEngine,
    threshold: f32,
) -> ReviewReport {
    let t0 = std::time::Instant::now();
    let embedder = RealTextEmbedder::new(32, 42);

    let mut alerts = Vec::new();
    let mut hunks_scanned = 0;
    let mut lines_added = 0;
    let mut lines_deleted = 0;

    for f in files {
        hunks_scanned += f.hunks.len();
        for h in &f.hunks {
            lines_added += h.added_lines.len();
            lines_deleted += h.deleted_lines.len();

            // 1. Check deleted lines for removed historical compatibility
            if !h.deleted_lines.is_empty() {
                let del_snippet = h.deleted_lines.join(" ");
                let query = format!("{} deleted: {}", f.path, del_snippet);
                let q_emb = embedder.embed(&query);
                let matches = engine.query(&q_emb, 3);

                if let Some(top) = matches.first() {
                    if top.revision_score >= threshold {
                        alerts.push(RegressionAlert {
                            file_path: f.path.clone(),
                            line_number: h.old_start,
                            score: top.revision_score,
                            provenance: top.provenance.clone(),
                            risk_summary: format!("Deleted code in '{}' has high causal similarity with historical fix.", f.path),
                            remediation: "Verify that legacy fallbacks or safety guards are not unintentionally purged.".to_string(),
                        });
                        continue;
                    }
                }
            }

            // 2. Check added lines for reintroduced known antipatterns
            if !h.added_lines.is_empty() {
                let add_snippet = h.added_lines.join(" ");
                let query = format!("{} added: {}", f.path, add_snippet);
                let q_emb = embedder.embed(&query);
                let matches = engine.query(&q_emb, 3);

                if let Some(top) = matches.first() {
                    if top.revision_score >= threshold {
                        alerts.push(RegressionAlert {
                            file_path: f.path.clone(),
                            line_number: h.new_start,
                            score: top.revision_score,
                            provenance: top.provenance.clone(),
                            risk_summary: format!("Added code in '{}' matches historical failure pattern.", f.path),
                            remediation: "Check historical commit provenance before merging to prevent recurring outages.".to_string(),
                        });
                    }
                }
            }
        }
    }

    let latency_us = t0.elapsed().as_micros() as f64;

    ReviewReport {
        files_scanned: files.len(),
        hunks_scanned,
        lines_added,
        lines_deleted,
        alerts,
        latency_us,
    }
}
