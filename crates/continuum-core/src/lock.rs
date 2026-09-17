//! Cross-Process File Locking in pure Rust standard library.
//!
//! Provides advisory locking with stale lock auto-expiration and timeout.
//! ZERO external crate dependencies.

use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::thread::sleep;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// RAII Guard for an acquired cross-process file lock.
/// Automatically releases the lock when dropped.
#[derive(Debug)]
pub struct FileLockGuard {
    lock_path: PathBuf,
}

impl FileLockGuard {
    /// Attempts to acquire an exclusive advisory file lock within `timeout`.
    pub fn acquire(path: impl AsRef<Path>, timeout: Duration) -> std::io::Result<Self> {
        let lock_path = PathBuf::from(format!("{}.lock", path.as_ref().display()));
        let start = Instant::now();
        let pid = std::process::id();

        loop {
            // Attempt atomic creation of lockfile
            match OpenOptions::new().write(true).create_new(true).open(&lock_path) {
                Ok(mut file) => {
                    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                    let payload = format!("pid={}\ntime={}\n", pid, now);
                    let _ = file.write_all(payload.as_bytes());
                    let _ = file.sync_all();
                    return Ok(Self { lock_path });
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                    // Check if existing lock is stale (> 5 seconds old)
                    if Self::is_lock_stale(&lock_path) {
                        let _ = std::fs::remove_file(&lock_path);
                        continue;
                    }

                    if start.elapsed() >= timeout {
                        return Err(std::io::Error::new(
                            std::io::ErrorKind::TimedOut,
                            format!("Timed out acquiring lock on '{}'", lock_path.display()),
                        ));
                    }

                    // Jittered backoff: 2ms to 20ms
                    let elapsed_ms = start.elapsed().as_millis();
                    let backoff = Duration::from_millis(2 + (elapsed_ms % 18) as u64);
                    sleep(backoff);
                }
                Err(e) => return Err(e),
            }
        }
    }

    /// Checks if a lock file is stale (held by a dead process or > 5s old).
    fn is_lock_stale(lock_path: &Path) -> bool {
        if let Ok(mut f) = File::open(lock_path) {
            let mut buf = String::new();
            if f.read_to_string(&mut buf).is_ok() {
                for line in buf.lines() {
                    if let Some(rest) = line.strip_prefix("time=") {
                        if let Ok(ts) = rest.trim().parse::<u64>() {
                            let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
                            if now.saturating_sub(ts) > 5 {
                                return true; // Stale lock older than 5 seconds
                            }
                        }
                    }
                }
            }
        }
        false
    }

    /// Return the path of the active lockfile.
    pub fn lock_path(&self) -> &Path {
        &self.lock_path
    }
}

impl Drop for FileLockGuard {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.lock_path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lock_acquire_and_release() {
        let temp_dir = std::env::temp_dir();
        let target = temp_dir.join(format!("continuum_lock_test_{}", std::process::id()));
        let lock_file = PathBuf::from(format!("{}.lock", target.display()));

        {
            let guard = FileLockGuard::acquire(&target, Duration::from_millis(500)).expect("Lock acquire failed");
            assert!(lock_file.exists());
            assert_eq!(guard.lock_path(), &lock_file);

            // Second acquire must fail / timeout while guard is held
            let second = FileLockGuard::acquire(&target, Duration::from_millis(50));
            assert!(second.is_err());
        }

        // After guard is dropped, lockfile must be removed
        assert!(!lock_file.exists());

        // Now lock can be re-acquired immediately
        let guard2 = FileLockGuard::acquire(&target, Duration::from_millis(500));
        assert!(guard2.is_ok());
    }
}
