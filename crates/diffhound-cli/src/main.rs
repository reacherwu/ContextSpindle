//! DiffHound CLI & Webhook Server: Zero-Noise AI PR Guard & Anti-Regression Engine.

mod diff;
mod github;
mod json;
mod review;
mod server;

use std::path::{Path, PathBuf};
use std::process::exit;

use continuum_core::{
    ContinuumConfig, ContinuumEngine, RealTextEmbedder,
};

use diff::{get_git_diff, parse_unified_diff};
use review::{locate_memory_state, perform_review};

const DIFFHOUND_BANNER: &str = r#"
  ____  _  __  __ _   _                       _ 
 |  _ \(_)/ _|/ _| | | | ___  _   _ _ __   __| |
 | | | | | |_| |_| |_| |/ _ \| | | | '_ \ / _` |
 | |_| | |  _|  _|  _  | (_) | |_| | | | | (_| |
 |____/|_|_| |_| |_| |_|\___/ \__,_|_| |_|\__,_|
  Zero-Noise AI PR Guard & Anti-Regression Engine
"#;

fn print_help() {
    println!("{}", DIFFHOUND_BANNER);
    println!("Usage:");
    println!("  diffhound review [--base <ref>] [--head <ref>] [--fail-on-regression] [--threshold <float>]");
    println!("                   [--post-comment] [--repo <owner/repo>] [--pr <number>]");
    println!("                                     Inspect git diff for regressions against historical fixes");
    println!("  diffhound server [--port <u16>] [--github-token <token>] [--threshold <float>]");
    println!("                                     Run standalone GitHub App webhook daemon");
    println!("  diffhound init [path]              Initialize .diffhound memory state in repository");
    println!("  diffhound remember <text>          Ingest architectural rule or fix into bounded memory");
    println!("  diffhound recall <query> [k]       Retrospectively query historical memory in < 100 μs");
    println!("  diffhound version                  Display version and engine information");
    println!("  diffhound help                     Show this help message");
    println!();
    println!("Flags for 'review':");
    println!("  --base <ref>              Base branch or commit to diff against (e.g. origin/main, HEAD~1)");
    println!("  --head <ref>              Head branch or commit to diff (default: working tree or HEAD)");
    println!("  --fail-on-regression      Exit with status code 1 if potential regression is detected");
    println!("  --threshold <float>       Sensitivity score threshold (default: 0.45)");
    println!("  --post-comment            Post markdown review directly to GitHub PR via REST API");
    println!("  --repo <owner/repo>       Target GitHub repository (default: $GITHUB_REPOSITORY)");
    println!("  --pr <number>             Target Pull Request number (default: $PR_NUMBER)");
    println!("  --json                    Output machine-readable JSON format");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        print_help();
        return;
    }

    match args[1].as_str() {
        "review" => run_review(&args[2..]),
        "server" => run_server(&args[2..]),
        "init" => run_init(&args[2..]),
        "remember" => run_remember(&args[2..]),
        "recall" => run_recall(&args[2..]),
        "version" | "--version" | "-v" => {
            println!("diffhound v0.2.0 (Zero-Noise AI PR Guard, 100% Native Rust)");
        }
        "help" | "--help" | "-h" => {
            print_help();
        }
        unknown => {
            eprintln!("Unknown command: '{}'. Run 'diffhound help' for usage.", unknown);
            exit(1);
        }
    }
}

fn run_review(args: &[String]) {
    let mut base_ref: Option<String> = None;
    let mut head_ref: Option<String> = None;
    let mut fail_on_regression = false;
    let mut json_output = false;
    let mut post_comment = false;
    let mut repo: Option<String> = std::env::var("GITHUB_REPOSITORY").ok();
    let mut pr_number: Option<u64> = std::env::var("PR_NUMBER").ok().and_then(|s| s.parse::<u64>().ok());
    let mut threshold = 0.45f32;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--base" => {
                if i + 1 < args.len() {
                    base_ref = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--head" => {
                if i + 1 < args.len() {
                    head_ref = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--fail-on-regression" => {
                fail_on_regression = true;
            }
            "--post-comment" => {
                post_comment = true;
            }
            "--repo" => {
                if i + 1 < args.len() {
                    repo = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--pr" => {
                if i + 1 < args.len() {
                    pr_number = args[i + 1].parse::<u64>().ok();
                    i += 1;
                }
            }
            "--json" => {
                json_output = true;
            }
            "--threshold" => {
                if i + 1 < args.len() {
                    if let Ok(t) = args[i + 1].parse::<f32>() {
                        threshold = t;
                    }
                    i += 1;
                }
            }
            _ => {}
        }
        i += 1;
    }

    // 1. Obtain git diff
    let diff_text = match get_git_diff(base_ref.as_deref(), head_ref.as_deref()) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("❌ DiffHound: Failed to obtain git diff: {e}");
            exit(1);
        }
    };

    if diff_text.trim().is_empty() {
        if json_output {
            println!(r#"{{"status":"clean","files_scanned":0,"alerts":[]}}"#);
        } else {
            println!("🐕 DiffHound: No file changes detected in diff. Clean to merge.");
        }
        return;
    }

    let file_diffs = parse_unified_diff(&diff_text);

    // 2. Locate or initialize memory manifold
    let state_file = locate_memory_state();
    let mut engine = match state_file {
        Some(ref p) => ContinuumEngine::load_from_file(p).unwrap_or_else(|_| ContinuumEngine::new(ContinuumConfig::default())),
        None => ContinuumEngine::new(ContinuumConfig::default()),
    };

    // 3. Perform Zero-Noise Review
    let report = perform_review(&file_diffs, &mut engine, threshold);

    // 4. Write GitHub Step Summary (if in GitHub Actions)
    report.write_github_step_summary();

    // 5. Optionally post PR comment directly to GitHub
    if post_comment && !report.is_clean() {
        if let Ok(token) = std::env::var("GITHUB_TOKEN") {
            if let (Some(r), Some(pr)) = (repo.as_ref(), pr_number) {
                match github::post_pr_comment(&token, r, pr, &report.to_markdown()) {
                    Ok(()) => println!("✅ DiffHound successfully posted regression alert to PR #{}", pr),
                    Err(e) => eprintln!("⚠️ DiffHound failed to post PR comment: {e}"),
                }
            }
        }
    }

    // 6. Output to stdout
    if json_output {
        println!(
            r#"{{"status":"{}","files_scanned":{},"alerts_count":{},"latency_us":{:.2}}}"#,
            if report.is_clean() { "clean" } else { "regression_detected" },
            report.files_scanned,
            report.alerts.len(),
            report.latency_us
        );
    } else {
        println!("{}", report.to_markdown());
    }

    if fail_on_regression && !report.is_clean() {
        eprintln!("❌ DiffHound check failed: Potential regression detected. PR blocked.");
        exit(1);
    }
}

fn run_server(args: &[String]) {
    let mut port = 8080u16;
    let mut secret: Option<String> = std::env::var("DIFFHOUND_WEBHOOK_SECRET").ok();
    let mut github_token: Option<String> = std::env::var("GITHUB_TOKEN").ok();
    let mut threshold = 0.45f32;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--port" | "-p" => {
                if i + 1 < args.len() {
                    if let Ok(p) = args[i + 1].parse::<u16>() {
                        port = p;
                    }
                    i += 1;
                }
            }
            "--secret" => {
                if i + 1 < args.len() {
                    secret = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--github-token" => {
                if i + 1 < args.len() {
                    github_token = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--threshold" => {
                if i + 1 < args.len() {
                    if let Ok(t) = args[i + 1].parse::<f32>() {
                        threshold = t;
                    }
                    i += 1;
                }
            }
            _ => {}
        }
        i += 1;
    }

    let cfg = server::ServerConfig {
        port,
        webhook_secret: secret,
        github_token,
        threshold,
    };

    if let Err(e) = server::run_webhook_server(cfg) {
        eprintln!("❌ DiffHound Server Error: {e}");
        exit(1);
    }
}

fn run_init(args: &[String]) {
    let target = args.get(0).map(|s| s.as_str()).unwrap_or(".");
    let diffhound_dir = Path::new(target).join(".diffhound");

    if let Err(e) = std::fs::create_dir_all(&diffhound_dir) {
        eprintln!("Failed to create directory '{}': {e}", diffhound_dir.display());
        exit(1);
    }

    let state_path = diffhound_dir.join("memory.state");
    if !state_path.exists() {
        let cfg = ContinuumConfig::default();
        let engine = ContinuumEngine::new(cfg);
        if let Err(e) = engine.save_to_file(&state_path) {
            eprintln!("Failed to initialize memory state: {e}");
            exit(1);
        }
    }

    println!("============================================================================");
    println!("  DIFFHOUND INITIALIZATION COMPLETE");
    println!("============================================================================");
    println!("Location: '{}'", diffhound_dir.display());
    println!("Status:   Zero-Noise PR Guard active in repository.");
    println!("============================================================================");
}

fn run_remember(args: &[String]) {
    if args.is_empty() {
        eprintln!("Usage: diffhound remember <text>");
        exit(1);
    }
    let text = args.join(" ");
    let state_path = locate_memory_state().unwrap_or_else(|| PathBuf::from(".diffhound/memory.state"));

    let mut engine = if state_path.exists() {
        ContinuumEngine::load_from_file(&state_path).unwrap_or_else(|_| ContinuumEngine::new(ContinuumConfig::default()))
    } else {
        if let Some(parent) = state_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        ContinuumEngine::new(ContinuumConfig::default())
    };

    let embedder = RealTextEmbedder::new(32, 42);
    let emb = embedder.embed(&text);
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();

    engine.step(&emb, now, &text);
    if let Err(e) = engine.save_to_file(&state_path) {
        eprintln!("Failed to save memory: {e}");
        exit(1);
    }

    println!("🐕 DiffHound: Successfully ingested causal anchor into memory manifold.");
}

fn run_recall(args: &[String]) {
    if args.is_empty() {
        eprintln!("Usage: diffhound recall <query> [k]");
        exit(1);
    }
    let query = &args[0];
    let k = args.get(1).and_then(|s| s.parse::<usize>().ok()).unwrap_or(3);

    let state_path = match locate_memory_state() {
        Some(p) => p,
        None => {
            eprintln!("No .diffhound or .continuum memory state found. Run 'diffhound init' first.");
            exit(1);
        }
    };

    let engine = match ContinuumEngine::load_from_file(&state_path) {
        Ok(e) => e,
        Err(e) => {
            eprintln!("Failed to load memory state: {e}");
            exit(1);
        }
    };

    let embedder = RealTextEmbedder::new(32, 42);
    let emb = embedder.embed(query);

    let t0 = std::time::Instant::now();
    let matches = engine.query(&emb, k);
    let lat_us = t0.elapsed().as_micros();

    println!("🐕 DiffHound Retrospective Recall ({lat_us} μs):");
    for (i, m) in matches.iter().enumerate() {
        println!("  #{}: [Score: {:.4}] {}", i + 1, m.revision_score, m.provenance);
    }
}
