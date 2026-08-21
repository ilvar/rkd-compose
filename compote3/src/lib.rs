//! compote3 — a dashboard for k3s ingresses, custom links and GitHub
//! repositories.
//!
//! The crate is laid out so that everything which decides *what the dashboard
//! shows* is a pure function, and everything which *reaches out to the world*
//! is confined to [`sys::capability`], [`github`] and [`k3s`].

#![cfg_attr(
    not(test),
    deny(clippy::expect_used, clippy::indexing_slicing, clippy::unwrap_used)
)]

pub mod clock;
pub mod config;
pub mod data;
pub mod github;
pub mod k3s;
pub mod kubeconfig;
pub mod models;
pub mod server;
pub mod sys;

/// Default listen port, overridden by `PORT`.
pub const DEFAULT_PORT: &str = "9000";

/// Default configuration file, overridden by `--config`.
pub const DEFAULT_CONFIG: &str = "config.yaml";

/// Worker threads serving HTTP. Requests are IO-bound on Kubernetes and
/// GitHub, so this is about overlapping waits, not about CPU.
pub const WORKERS: usize = 8;

/// An error worth exiting on, rendered as a bare message rather than as the
/// `Debug` of a string.
pub struct CliError(pub String);

impl std::fmt::Debug for CliError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}", self.0)
    }
}

impl std::fmt::Display for CliError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}", self.0)
    }
}

impl From<String> for CliError {
    fn from(message: String) -> Self {
        CliError(message)
    }
}

/// What the command line asked for.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Invocation {
    /// Serve the dashboard, reading configuration from this path.
    Serve { config: String },
    /// Print usage and exit successfully.
    Help,
}

pub const USAGE: &str = "\
compote3 — dashboard for k3s ingresses, links and GitHub repositories

USAGE:
    compote3 [--config <path>]

OPTIONS:
    --config <path>    Configuration file (default: config.yaml)
    -h, --help         Print this help

ENVIRONMENT:
    PORT               Listen port (default: 9000)
    GITHUB_TOKEN       GitHub token, strongly recommended for API rate limits
    KUBECONFIG         Kubeconfig path used outside a cluster
                       (default: $HOME/.kube/config)
";

/// Parses arguments, excluding argv[0].
pub fn parse_arguments(arguments: &[String]) -> Result<Invocation, String> {
    let mut config = DEFAULT_CONFIG.to_owned();
    let mut remaining = arguments.iter();

    while let Some(argument) = remaining.next() {
        match argument.as_str() {
            "-h" | "--help" | "help" => return Ok(Invocation::Help),
            "--config" => {
                config = remaining
                    .next()
                    .ok_or_else(|| "--config requires a path".to_owned())?
                    .clone();
            }
            other => {
                if let Some(value) = other.strip_prefix("--config=") {
                    config = value.to_owned();
                } else {
                    return Err(format!("unrecognized argument: {other}"));
                }
            }
        }
    }

    Ok(Invocation::Serve { config })
}

#[cfg(test)]
mod tests {
    use super::parse_arguments;
    use super::Invocation;
    use super::DEFAULT_CONFIG;

    fn arguments(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    #[test]
    fn no_arguments_serve_the_default_config() {
        assert_eq!(
            parse_arguments(&[]),
            Ok(Invocation::Serve {
                config: DEFAULT_CONFIG.to_owned()
            })
        );
    }

    #[test]
    fn config_accepts_both_spellings() {
        let expected = Ok(Invocation::Serve {
            config: "/etc/compote3.yaml".to_owned(),
        });

        assert_eq!(
            parse_arguments(&arguments(&["--config", "/etc/compote3.yaml"])),
            expected
        );
        assert_eq!(
            parse_arguments(&arguments(&["--config=/etc/compote3.yaml"])),
            expected
        );
    }

    #[test]
    fn help_is_recognized_under_every_alias() {
        for alias in ["-h", "--help", "help"] {
            assert_eq!(parse_arguments(&arguments(&[alias])), Ok(Invocation::Help));
        }
    }

    #[test]
    fn a_config_flag_without_a_value_is_an_error() {
        assert!(parse_arguments(&arguments(&["--config"])).is_err());
    }

    #[test]
    fn an_unknown_flag_is_an_error_rather_than_silently_ignored() {
        let error = parse_arguments(&arguments(&["--nope"])).expect_err("reported");
        assert!(error.contains("--nope"), "unexpected error: {error}");
    }
}
