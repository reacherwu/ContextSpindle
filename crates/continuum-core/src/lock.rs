//! OS advisory locks for cooperating local processes (Rust 1.89+).
//!
//! The sidecar inode is permanent: never delete it or steal a lock based on age.
//! Stop ALL old create-new-protocol writers before upgrading or rolling back.
//! All participants must use the same path; hard-link aliases are not supported.

use std::fs::{File, OpenOptions, TryLockError};
use std::io;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

/// Exclusive OS lock released by closing its owned file, including on process exit.
#[derive(Debug)]
pub struct FileLockGuard {
    _file: File,
    lock_path: PathBuf,
}

impl FileLockGuard {
    /// Acquire within `timeout`. A zero timeout makes one nonblocking attempt.
    /// The target's parent must already exist. Never remove the sidecar file.
    pub fn acquire(path: impl AsRef<Path>, timeout: Duration) -> io::Result<Self> {
        let mut name = path.as_ref().as_os_str().to_os_string();
        name.push(".lock");
        let lock_path = PathBuf::from(name);
        let start = Instant::now();
        let file = OpenOptions::new().read(true).write(true).create(true)
            .truncate(false).open(&lock_path)?;
        loop {
            match file.try_lock() {
                Ok(()) => return Ok(Self { _file: file, lock_path }),
                Err(TryLockError::WouldBlock) => {
                    let remaining = timeout.saturating_sub(start.elapsed());
                    if remaining.is_zero() {
                        return Err(io::Error::new(io::ErrorKind::TimedOut,
                            format!("Timed out acquiring lock on '{}'", lock_path.display())));
                    }
                    std::thread::sleep(remaining.min(Duration::from_millis(10)));
                }
                Err(TryLockError::Error(e)) if e.kind() == io::ErrorKind::Interrupted => {
                    if start.elapsed() >= timeout {
                        return Err(io::Error::new(io::ErrorKind::TimedOut, "Lock acquisition interrupted until timeout"));
                    }
                }
                Err(TryLockError::Error(e)) => return Err(e),
            }
        }
    }

    /// Path of the permanent sidecar, not evidence that a lock is held.
    pub fn lock_path(&self) -> &Path { &self.lock_path }
}
