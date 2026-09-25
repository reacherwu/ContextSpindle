//! OS-Level Kernel Advisory File Lock in pure Rust standard library.
//!
//! Replaces fragile time-based lock stealing with genuine OS-level kernel locks:
//! - On Unix (macOS, Linux): uses kernel `flock(fd, LOCK_EX)`.
//!   Guarantees that when a process terminates or crashes (even SIGKILL),
//!   the operating system kernel AUTOMATICALLY and INSTANTLY releases the lock.
//! - ZERO external crate dependencies (uses Rust standard library OS FFI).

use std::fs::{File, OpenOptions};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

#[cfg(unix)]
use std::os::unix::io::AsRawFd;

/// RAII Guard for an acquired OS kernel-level advisory file lock.
/// Automatically releases the lock when dropped or when process terminates.
#[derive(Debug)]
pub struct FileLockGuard {
    lock_file: File,
    lock_path: PathBuf,
}

#[cfg(unix)]
#[allow(dead_code)]
mod sys {
    use std::os::raw::c_int;

    pub const LOCK_SH: c_int = 1; // Shared lock
    pub const LOCK_EX: c_int = 2; // Exclusive lock
    pub const LOCK_NB: c_int = 4; // Non-blocking
    pub const LOCK_UN: c_int = 8; // Unlock

    unsafe extern "C" {
        pub fn flock(fd: c_int, operation: c_int) -> c_int;
    }
}

impl FileLockGuard {
    /// Attempts to acquire an exclusive kernel file lock within `timeout`.
    pub fn acquire(path: impl AsRef<Path>, timeout: Duration) -> std::io::Result<Self> {
        let target_path = path.as_ref();
        let lock_path = PathBuf::from(format!("{}.lock", target_path.display()));

        let parent = lock_path.parent().unwrap_or_else(|| Path::new("."));
        if !parent.as_os_str().is_empty() {
            let _ = std::fs::create_dir_all(parent);
        }

        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&lock_path)?;

        let start = Instant::now();

        #[cfg(unix)]
        {
            let fd = file.as_raw_fd();
            loop {
                // Try non-blocking exclusive acquisition
                let res = unsafe { sys::flock(fd, sys::LOCK_EX | sys::LOCK_NB) };
                if res == 0 {
                    return Ok(Self {
                        lock_file: file,
                        lock_path,
                    });
                }

                if start.elapsed() >= timeout {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::TimedOut,
                        format!(
                            "Timed out after {:?} waiting for OS kernel file lock on '{}'",
                            timeout,
                            lock_path.display()
                        ),
                    ));
                }

                // Sleep with backoff (2ms to 20ms)
                let elapsed_ms = start.elapsed().as_millis();
                let backoff = Duration::from_millis(2 + (elapsed_ms % 18) as u64);
                std::thread::sleep(backoff);
            }
        }

        #[cfg(not(unix))]
        {
            let _ = (file, lock_path, start);
            Err(std::io::Error::new(
                std::io::ErrorKind::Unsupported,
                "Durable task writes require an OS file lock; this platform is not yet supported",
            ))
        }
    }

    pub fn lock_path(&self) -> &Path {
        &self.lock_path
    }
}

impl Drop for FileLockGuard {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            let fd = self.lock_file.as_raw_fd();
            unsafe {
                sys::flock(fd, sys::LOCK_UN);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kernel_lock_mutual_exclusion() {
        let temp_dir = std::env::temp_dir();
        let target = temp_dir.join(format!("continuum_flock_test_{}", std::process::id()));

        {
            let guard1 = FileLockGuard::acquire(&target, Duration::from_millis(500))
                .expect("Failed first acquire");

            // Second acquire on the same file from another descriptor must timeout
            let guard2 = FileLockGuard::acquire(&target, Duration::from_millis(50));
            assert!(
                guard2.is_err(),
                "Second acquire should have timed out due to exclusive lock!"
            );
            drop(guard1);
        }

        // Once dropped, acquire must succeed immediately
        let guard3 = FileLockGuard::acquire(&target, Duration::from_millis(500));
        assert!(guard3.is_ok(), "Failed re-acquiring lock after drop");

        let _ = std::fs::remove_file(format!("{}.lock", target.display()));
    }
}
