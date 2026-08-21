//! Every filesystem, environment and process effect compote3 performs.
//!
//! Keeping them behind one boundary is what lets the rest of the crate be
//! read as pure data transformation, and it is what `strictrs` enforces with
//! its `capability_boundary` rule.

// strictrs: capability
pub mod capability {
    use std::path::Path;
    use std::path::PathBuf;

    /// Reads a UTF-8 file, mapping IO failures to a message that names the path.
    pub fn read_to_string(path: &Path) -> Result<String, String> {
        std::fs::read_to_string(path)
            .map_err(|error| format!("failed to read {}: {error}", path.display()))
    }

    /// Reads a file as bytes, mapping IO failures to a message that names the path.
    pub fn read_bytes(path: &Path) -> Result<Vec<u8>, String> {
        std::fs::read(path).map_err(|error| format!("failed to read {}: {error}", path.display()))
    }

    /// True when `path` names something the process can stat.
    pub fn exists(path: &Path) -> bool {
        std::fs::metadata(path).is_ok()
    }

    /// A process environment variable, absent when unset or not UTF-8.
    pub fn env_var(key: &str) -> Option<String> {
        std::env::var(key).ok()
    }

    /// The process arguments, including argv[0].
    pub fn args() -> Vec<String> {
        std::env::args().collect()
    }

    /// The current user's home directory, used to locate a default kubeconfig.
    pub fn home_dir() -> Option<PathBuf> {
        env_var("HOME").map(PathBuf::from)
    }
}
