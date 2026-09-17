//! Explicit backup/check/restore; no automatic corruption fallback.
//! CLI callers must obtain explicit user confirmation before passing overwrite=true.
use std::{fs, io::{self, Write}, path::{Path, PathBuf}, time::Duration};
use crate::{ContinuumEngine, FileLockGuard};
use crate::persistence::{atomic_write, decode, parent, read_snapshot_bytes};

/// Structural check result, NOT cryptographic integrity verification.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SnapshotInfo {
    pub format: &'static str,
    pub bytes: u64,
    pub step_count: u64,
    pub hot_records: usize,
    pub cold_records: usize,
    pub checksum_verified: bool,
}
fn info(e: &ContinuumEngine, bytes: usize) -> SnapshotInfo {
    SnapshotInfo { format: "CTNM0001", bytes: bytes as u64, step_count: e.step_count,
        hot_records: e.hot_memory.len(), cold_records: e.cold_memory.len(), checksum_verified: false }
}
/// Check a snapshot while holding its lock. Does not rewrite the snapshot.
pub fn check_snapshot(path: impl AsRef<Path>) -> io::Result<SnapshotInfo> {
    let path = path.as_ref();
    let _lock = FileLockGuard::acquire(path, Duration::from_secs(2))?;
    let bytes = read_snapshot_bytes(path)?;
    Ok(info(&decode(&bytes)?, bytes.len()))
}
fn normalized(path: &Path) -> io::Result<PathBuf> {
    let name = path.file_name().ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "Snapshot requires a filename"))?;
    Ok(fs::canonicalize(parent(path))?.join(name))
}
fn copy_validated(source: &Path, target: &Path, overwrite: bool) -> io::Result<SnapshotInfo> {
    // Recover destinations may not be symlinks: replacement should be unambiguous.
    fs::create_dir_all(parent(target))?;
    let source = normalized(source)?;
    let target = normalized(target)?;
    let mut source_lock = source.as_os_str().to_os_string(); source_lock.push(".lock");
    let mut target_lock = target.as_os_str().to_os_string(); target_lock.push(".lock");
    if source == target
        || source.as_os_str() == target_lock.as_os_str()
        || target.as_os_str() == source_lock.as_os_str()
    {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "Source and destination (including lock sidecars) must differ"));
    }
    // Consistent order prevents A->B / B->A lock inversion.
    let (first, second) = if source < target { (&source, &target) } else { (&target, &source) };
    let _first = FileLockGuard::acquire(first, Duration::from_secs(3))?;
    let _second = FileLockGuard::acquire(second, Duration::from_secs(3))?;
    for path in [&source, &target] {
        match fs::symlink_metadata(path) {
            Ok(m) if m.file_type().is_symlink() => return Err(io::Error::new(io::ErrorKind::InvalidInput, "Recovery paths must not be symlinks")),
            Ok(_) => {},
            Err(e) if e.kind() == io::ErrorKind::NotFound => {},
            Err(e) => return Err(e),
        }
    }
    #[cfg(unix)] {
        use std::os::unix::fs::MetadataExt;
        if let (Ok(a), Ok(b)) = (fs::metadata(&source), fs::metadata(&target))
            && a.dev() == b.dev()
            && a.ino() == b.ino()
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Recovery paths refer to the same file",
            ));
        }
    }
    let bytes = read_snapshot_bytes(&source)?;
    let report = info(&decode(&bytes)?, bytes.len());
    // Validation completes before any destination data is touched. Copy exact
    // original bytes for rollback compatibility and never move/delete the backup.
    atomic_write(&target, !overwrite, |file| file.write_all(&bytes))?;
    Ok(report)
}
/// Create a validated exact-byte backup. Existing backup paths are never replaced.
pub fn backup_engine(source: impl AsRef<Path>, backup: impl AsRef<Path>) -> io::Result<SnapshotInfo> {
    copy_validated(source.as_ref(), backup.as_ref(), false)
}
/// Validate backup, then atomically restore target without changing backup.
/// Existing targets require overwrite=true; CLI MUST require explicit confirmation.
/// With false, publication is atomic no-clobber even if another process creates target.
pub fn restore_engine(backup: impl AsRef<Path>, target: impl AsRef<Path>, overwrite: bool) -> io::Result<SnapshotInfo> {
    copy_validated(backup.as_ref(), target.as_ref(), overwrite)
}
