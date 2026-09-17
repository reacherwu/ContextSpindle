use continuum_core::{ContinuumConfig, ContinuumEngine, FileLockGuard, load_engine, save_engine, mutate_engine_transactional};
use std::{fs, path::PathBuf, time::{Duration, Instant}, sync::atomic::{AtomicU64, Ordering}};
static NEXT: AtomicU64 = AtomicU64::new(0);
struct Scratch(PathBuf);
impl Scratch {
    fn new() -> Self {
        let p = std::env::temp_dir().join(format!("continuum-storage-{}-{}", std::process::id(), NEXT.fetch_add(1, Ordering::Relaxed)));
        fs::create_dir(&p).unwrap(); Self(p)
    }
    fn state(&self) -> PathBuf { self.0.join("memory.state") }
}
impl Drop for Scratch { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); } }
fn config() -> ContinuumConfig { ContinuumConfig { embedding_dim: 4, state_dim: 4, hot_capacity: 128, cold_capacity: 128, ..Default::default() } }
fn step(e: &mut ContinuumEngine) { e.step(&[1.0, 0.0, 0.0, 0.0], e.step_count as f64, "真实 Unicode 🦀 full text"); }

#[test]
fn save_creates_parent_and_failed_mutation_preserves_snapshot() {
    let dir = Scratch::new(); let p = dir.0.join("nested/memory.state");
    let mut e = ContinuumEngine::new(config()); step(&mut e);
    save_engine(&e, &p).unwrap();
    let before = fs::read(&p).unwrap();
    let result = mutate_engine_transactional(&p, None, |e| -> std::io::Result<()> { step(e); Err(std::io::Error::other("cancel")) });
    assert!(result.is_err()); assert_eq!(fs::read(&p).unwrap(), before);
    let loaded = load_engine(&p).unwrap(); assert_eq!(loaded.hot_memory.records[0].payload_ref, "真实 Unicode 🦀 full text");
    assert_eq!(&before[..8], b"CTNM0001");
}

#[test]
fn save_rejects_inconsistent_state_without_overwrite() {
    let dir = Scratch::new(); let p = dir.state();
    let mut e = ContinuumEngine::new(config()); save_engine(&e, &p).unwrap();
    let before = fs::read(&p).unwrap(); e.temporal_core.state.pop();
    assert!(save_engine(&e, &p).is_err()); assert_eq!(fs::read(&p).unwrap(), before);
}

#[test]
fn backup_check_restore_are_validated_and_no_clobber() {
    use continuum_core::{backup_engine, check_snapshot, restore_engine};
    let dir = Scratch::new(); let p = dir.state(); let backup = dir.0.join("backup.state");
    let mut e = ContinuumEngine::new(config()); step(&mut e); save_engine(&e, &p).unwrap();
    let original = fs::read(&p).unwrap();
    let report = backup_engine(&p, &backup).unwrap();
    assert_eq!(report.step_count, 1); assert!(!report.checksum_verified);
    assert_eq!(check_snapshot(&backup).unwrap(), report);
    assert_eq!(fs::read(&backup).unwrap(), original);
    assert_eq!(backup_engine(&p, &backup).unwrap_err().kind(), std::io::ErrorKind::AlreadyExists);
    step(&mut e); save_engine(&e, &p).unwrap(); let newer = fs::read(&p).unwrap();
    assert_eq!(restore_engine(&backup, &p, false).unwrap_err().kind(), std::io::ErrorKind::AlreadyExists);
    assert_eq!(fs::read(&p).unwrap(), newer);
    restore_engine(&backup, &p, true).unwrap();
    assert_eq!(fs::read(&p).unwrap(), original); assert_eq!(fs::read(&backup).unwrap(), original);
    let other = dir.0.join("new.state"); restore_engine(&backup, &other, false).unwrap();
    assert_eq!(fs::read(&other).unwrap(), original);
    fs::write(&backup, b"CTNM0001").unwrap();
    assert!(restore_engine(&backup, &p, true).is_err()); assert_eq!(fs::read(&p).unwrap(), original);
    assert_eq!(fs::read(&backup).unwrap(), b"CTNM0001");
    assert!(restore_engine(&p, &p, true).is_err());
    assert!(restore_engine(&p, p.with_extension("state.lock"), true).is_err());
}

#[test]
fn failed_atomic_publication_cleans_own_temp() {
    let dir = Scratch::new(); let p = dir.state(); fs::create_dir(&p).unwrap();
    fs::write(p.join("keep"), b"untouched").unwrap();
    assert!(save_engine(&ContinuumEngine::new(config()), &p).is_err());
    assert_eq!(fs::read(p.join("keep")).unwrap(), b"untouched");
    assert!(fs::read_dir(&dir.0).unwrap().all(|entry| !entry.unwrap().file_name().to_string_lossy().contains(".tmp.")));
}

#[test]
fn ordinary_truncation_and_trailing_data_fail_closed() {
    let dir = Scratch::new(); let p = dir.state(); let mut e = ContinuumEngine::new(config());
    step(&mut e); save_engine(&e, &p).unwrap(); let bytes = fs::read(&p).unwrap();
    fs::write(&p, &bytes[..bytes.len() - 1]).unwrap(); assert!(load_engine(&p).is_err());
    let mut extra = bytes.clone(); extra.push(0); fs::write(&p, extra).unwrap(); assert!(load_engine(&p).is_err());
    fs::write(&p, &bytes).unwrap(); let restored = load_engine(&p).unwrap();
    save_engine(&restored, &p).unwrap(); assert_eq!(fs::read(&p).unwrap(), bytes);
}

#[test]
fn legacy_empty_snapshot_roundtrips_byte_exact() {
    let dir = Scratch::new(); let p = dir.state();
    // Independently encode the original CTNM0001 empty layout, no new metadata.
    let c = config(); let mut bytes = b"CTNM0001".to_vec();
    for v in [c.embedding_dim, c.state_dim, c.hot_capacity, c.cold_capacity] { bytes.extend_from_slice(&(v as u64).to_le_bytes()); }
    bytes.extend_from_slice(&c.sim_threshold.to_le_bytes()); bytes.push(0);
    for v in [c.temporal_decay_tau, c.w_sim, c.w_state_compat, c.w_temporal_compat, c.w_provenance_compat] { bytes.extend_from_slice(&v.to_le_bytes()); }
    bytes.extend_from_slice(&0u64.to_le_bytes()); bytes.extend_from_slice(&4u64.to_le_bytes());
    bytes.extend_from_slice(&[0; 16]); bytes.extend_from_slice(&[0; 16]);
    fs::write(&p, &bytes).unwrap(); let restored = load_engine(&p).unwrap();
    assert_eq!(restored.config.causal_exempt_threshold, None);
    save_engine(&restored, &p).unwrap(); assert_eq!(fs::read(&p).unwrap(), bytes);
}

#[test]
fn invalid_normal_state_is_rejected_before_save() {
    use continuum_core::persistence::{MAX_DIMENSION, MAX_TEXT_BYTES};
    let dir = Scratch::new(); let p = dir.state();
    let mut e = ContinuumEngine::new(config()); step(&mut e); save_engine(&e, &p).unwrap();
    let original = fs::read(&p).unwrap();
    let mut inconsistent = e.clone(); inconsistent.config.embedding_dim = MAX_DIMENSION + 1;
    assert!(save_engine(&inconsistent, &p).is_err());
    let mut inconsistent = e.clone(); inconsistent.config.temporal_decay_tau = 0.0;
    assert!(save_engine(&inconsistent, &p).is_err());
    let mut inconsistent = e.clone(); inconsistent.hot_memory.records[0].embedding[0] = f32::NAN;
    assert!(save_engine(&inconsistent, &p).is_err());
    let mut inconsistent = e.clone(); inconsistent.hot_memory.records.push(inconsistent.hot_memory.records[0].clone());
    assert!(save_engine(&inconsistent, &p).is_err());
    e.hot_memory.records[0].payload_ref = "x".repeat(MAX_TEXT_BYTES + 1);
    assert!(save_engine(&e, &p).is_err()); assert_eq!(fs::read(&p).unwrap(), original);
}

#[test]
fn incomplete_snapshot_is_not_reinitialized() {
    let dir = Scratch::new(); let p = dir.state(); fs::write(&p, b"CTNM0001").unwrap();
    assert!(mutate_engine_transactional(&p, Some(config()), |_| Ok(())).is_err());
    assert_eq!(fs::read(&p).unwrap(), b"CTNM0001");
}

#[test]
fn thread_rmw_has_no_lost_updates() {
    let dir = Scratch::new(); let p = dir.state();
    std::thread::scope(|scope| {
        for _ in 0..4 { let p = &p; scope.spawn(move || {
            for _ in 0..20 { mutate_engine_transactional(p, Some(config()), |e| { step(e); Ok(()) }).unwrap(); }
        }); }
    });
    assert_eq!(load_engine(&p).unwrap().step_count, 80);
}

#[test]
fn stable_lock_times_out_and_reacquires() {
    let dir = Scratch::new(); let p = dir.state();
    let guard = FileLockGuard::acquire(&p, Duration::ZERO).unwrap(); let sidecar = guard.lock_path().to_path_buf();
    #[cfg(unix)] let inode = { use std::os::unix::fs::MetadataExt; fs::metadata(&sidecar).unwrap().ino() };
    let start = Instant::now();
    assert_eq!(FileLockGuard::acquire(&p, Duration::from_millis(60)).unwrap_err().kind(), std::io::ErrorKind::TimedOut);
    assert!(start.elapsed() >= Duration::from_millis(60));
    drop(guard); assert!(sidecar.exists());
    let _again = FileLockGuard::acquire(&p, Duration::ZERO).unwrap();
    #[cfg(unix)] { use std::os::unix::fs::MetadataExt; assert_eq!(fs::metadata(&sidecar).unwrap().ino(), inode); }
}

// The integration-test executable doubles as an isolated cooperating child.
#[test]
fn child_worker() {
    let Some(p) = std::env::var_os("CONTINUUM_STORAGE_CHILD") else { return; };
    let p = PathBuf::from(p);
    if std::env::var_os("CONTINUUM_STORAGE_HOLD").is_some() {
        let _guard = FileLockGuard::acquire(&p, Duration::from_secs(3)).unwrap();
        fs::write(p.with_extension("ready"), b"ready").unwrap();
        std::thread::sleep(Duration::from_secs(60));
    } else {
        for _ in 0..20 { mutate_engine_transactional(&p, Some(config()), |e| { step(e); Ok(()) }).unwrap(); }
    }
}
fn child(p: &std::path::Path, hold: bool) -> std::process::Child {
    let mut c = std::process::Command::new(std::env::current_exe().unwrap());
    c.args(["--exact", "child_worker", "--nocapture"]).env("CONTINUUM_STORAGE_CHILD", p);
    if hold { c.env("CONTINUUM_STORAGE_HOLD", "1"); }
    c.stdout(std::process::Stdio::null()).spawn().unwrap()
}
struct ChildGuard(std::process::Child);
impl Drop for ChildGuard { fn drop(&mut self) { let _ = self.0.kill(); let _ = self.0.wait(); } }
#[test]
fn process_rmw_has_no_lost_updates() {
    let dir = Scratch::new(); let p = dir.state();
    let mut children: Vec<_> = (0..4).map(|_| ChildGuard(child(&p, false))).collect();
    for c in &mut children { assert!(c.0.wait().unwrap().success()); }
    assert_eq!(load_engine(&p).unwrap().step_count, 80);
}
#[test]
fn long_holder_is_not_stolen_and_killed_holder_releases() {
    let dir = Scratch::new(); let p = dir.state(); let mut c = ChildGuard(child(&p, true));
    let start = Instant::now();
    while !p.with_extension("ready").exists() {
        assert!(start.elapsed() < Duration::from_secs(5), "child not ready");
        assert!(c.0.try_wait().unwrap().is_none()); std::thread::sleep(Duration::from_millis(10));
    }
    std::thread::sleep(Duration::from_millis(6100));
    assert_eq!(FileLockGuard::acquire(&p, Duration::from_millis(50)).unwrap_err().kind(), std::io::ErrorKind::TimedOut);
    c.0.kill().unwrap(); c.0.wait().unwrap();
    let _guard = FileLockGuard::acquire(&p, Duration::from_millis(500)).unwrap();
}
