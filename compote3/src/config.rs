//! `config.yaml` — the operator-supplied half of the dashboard.

use serde::Deserialize;
use std::path::Path;

use crate::sys::capability;

/// Everything the dashboard reads out of `config.yaml`. Every section is
/// optional so a missing or partial file still yields a usable dashboard.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Config {
    /// Descriptions keyed by application or link name, matched case-insensitively.
    #[serde(default)]
    pub descriptions: Vec<DescriptionConfig>,
    #[serde(default)]
    pub github: GitHubConfig,
    #[serde(default)]
    pub links: Vec<LinkConfig>,
    /// Application names to hide, matched case-insensitively.
    #[serde(default)]
    pub exclusions: Vec<String>,
    /// Per-application name and URL rewrites, matched case-insensitively.
    #[serde(default)]
    pub overrides: Vec<AppOverride>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct AppOverride {
    /// Ingress-derived name this override applies to.
    pub name: String,
    #[serde(default)]
    pub new_name: String,
    #[serde(default)]
    pub url: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LinkConfig {
    pub name: String,
    pub url: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DescriptionConfig {
    pub name: String,
    pub description: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct GitHubConfig {
    /// GitHub username whose starred repositories fill the "watched" section.
    #[serde(default)]
    pub watcher: String,
}

/// Parses configuration from YAML text.
pub fn parse(text: &str) -> Result<Config, String> {
    let mut config: Config = serde_yaml_ng::from_str(text)
        .map_err(|error| format!("failed to parse config file: {error}"))?;
    normalize(&mut config);
    Ok(config)
}

/// Reads and parses `config.yaml` from disk.
pub fn load(path: &Path) -> Result<Config, String> {
    parse(&capability::read_to_string(path)?)
}

/// Trims URLs so a YAML block scalar (`url: |`) does not leave a trailing
/// newline inside an `href`.
fn normalize(config: &mut Config) {
    for link in &mut config.links {
        link.url = link.url.trim().to_owned();
    }
    for entry in &mut config.overrides {
        entry.url = entry.url.trim().to_owned();
    }
}

#[cfg(test)]
mod tests {
    use super::parse;

    #[test]
    fn empty_document_is_an_empty_config() {
        let config = parse("{}").expect("empty mapping parses");
        assert!(config.links.is_empty());
        assert!(config.exclusions.is_empty());
        assert_eq!(config.github.watcher, "");
    }

    #[test]
    fn links_and_watcher_round_trip() {
        let config = parse(
            "links:\n  - name: Test Link\n    url: https://test.com\ngithub:\n  watcher: testuser\n",
        )
        .expect("config parses");

        assert_eq!(config.links.len(), 1);
        assert_eq!(config.links[0].name, "Test Link");
        assert_eq!(config.links[0].url, "https://test.com");
        assert_eq!(config.github.watcher, "testuser");
    }

    #[test]
    fn block_scalar_urls_lose_their_trailing_newline() {
        let config = parse("overrides:\n  - name: a\n    url: |\n      https://example.com\n")
            .expect("config parses");

        assert_eq!(config.overrides[0].url, "https://example.com");
    }

    #[test]
    fn unknown_keys_are_rejected_rather_than_silently_ignored() {
        let error = parse("linkz: []\n").expect_err("typo is reported");
        assert!(error.contains("linkz"), "unexpected error: {error}");
    }

    #[test]
    fn the_committed_config_parses() {
        let text = include_str!("../config.yaml");
        let config = parse(text).expect("committed config.yaml parses");

        assert_eq!(config.github.watcher, "ilvar");
        assert!(!config.links.is_empty());
    }
}
