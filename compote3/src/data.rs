//! Assembly of the `/api/data` payload from the three sources: k3s ingresses,
//! GitHub, and `config.yaml`.
//!
//! Everything here is a pure function of its inputs. Fetching — and the
//! degrade-to-empty-on-failure policy — belongs to the caller, which is what
//! makes every rule below directly testable.

use std::collections::BTreeMap;

use crate::config::AppOverride;
use crate::config::Config;
use crate::models::ApiResponse;
use crate::models::Application;
use crate::models::GitHubRepo;

/// Ranking of the homelab's domain suffixes. When two ingresses expose the
/// same application, the lowest rank wins, so the short public name beats the
/// internal `*.h.` and `*.k.` ones.
fn domain_priority(url: &str) -> u8 {
    if url.contains(".h.rkd.pw") {
        return 2;
    }
    if url.contains(".k.rkd.pw") {
        return 3;
    }
    if url.contains(".rkd.pw") {
        return 1;
    }
    4
}

/// Collapses ingresses that describe the same application, keeping the one on
/// the highest-priority domain. Ties keep the first entry, so callers control
/// the outcome by ordering their input.
fn deduplicate_by_name(ingresses: Vec<Application>) -> BTreeMap<String, Application> {
    let mut by_name: BTreeMap<String, Application> = BTreeMap::new();
    for app in ingresses {
        let key = app.name.to_lowercase();
        match by_name.get(&key) {
            Some(existing) => {
                if domain_priority(&app.url) < domain_priority(&existing.url) {
                    let _ = by_name.insert(key, app);
                }
            }
            None => {
                let _ = by_name.insert(key, app);
            }
        }
    }
    by_name
}

fn lookup_map<'a, T, K, V>(
    entries: &'a [T],
    key: impl Fn(&'a T) -> K,
    value: impl Fn(&'a T) -> V,
) -> BTreeMap<String, V>
where
    K: AsRef<str>,
{
    entries
        .iter()
        .map(|entry| (key(entry).as_ref().to_lowercase(), value(entry)))
        .collect()
}

/// Applies an override's name and URL to an ingress-derived application.
fn apply_override(app: &mut Application, entry: &AppOverride) {
    if !entry.new_name.is_empty() {
        app.name = entry.new_name.to_lowercase();
    }
    if !entry.url.is_empty() {
        app.url = entry.url.clone();
    }
}

/// The application tiles: deduplicated, filtered, renamed and described.
fn build_applications(config: &Config, ingresses: Vec<Application>) -> Vec<Application> {
    let exclusions: BTreeMap<String, ()> = lookup_map(&config.exclusions, |name| name, |_| ());
    let overrides: BTreeMap<String, &AppOverride> =
        lookup_map(&config.overrides, |entry| &entry.name, |entry| entry);
    let descriptions: BTreeMap<String, &str> = lookup_map(
        &config.descriptions,
        |entry| &entry.name,
        |entry| entry.description.as_str(),
    );

    let mut applications = Vec::new();
    for (name, app) in deduplicate_by_name(ingresses) {
        if exclusions.contains_key(&name) {
            continue;
        }

        let mut tile = Application {
            name: name.clone(),
            url: app.url,
            description: String::new(),
        };

        let entry = overrides.get(&name).copied();
        if let Some(entry) = entry {
            apply_override(&mut tile, entry);
        }

        // A description may be filed under either the ingress name or the name
        // the override renamed it to; the original wins when both exist.
        let renamed = entry
            .filter(|entry| !entry.new_name.is_empty())
            .map(|entry| entry.new_name.to_lowercase());
        let description = descriptions
            .get(&name)
            .or_else(|| renamed.as_ref().and_then(|key| descriptions.get(key)));
        if let Some(description) = description {
            tile.description = (*description).to_owned();
        }

        // Dashes read as word separators once the ingress name becomes a label.
        tile.name = tile.name.replace('-', " ");
        applications.push(tile);
    }

    applications.sort_by(|left, right| left.name.cmp(&right.name));
    applications
}

/// The configured link tiles, described and sorted case-insensitively.
fn build_links(config: &Config) -> Vec<Application> {
    let descriptions: BTreeMap<String, &str> = lookup_map(
        &config.descriptions,
        |entry| &entry.name,
        |entry| entry.description.as_str(),
    );

    let mut links: Vec<Application> = config
        .links
        .iter()
        .map(|link| Application {
            name: link.name.clone(),
            url: link.url.clone(),
            description: descriptions
                .get(&link.name.to_lowercase())
                .map(|description| (*description).to_owned())
                .unwrap_or_default(),
        })
        .collect();

    links.sort_by_key(|link| link.name.to_lowercase());
    links
}

/// Everything `GET /api/data` returns, assembled from already-fetched inputs.
pub fn build_response(
    config: &Config,
    ingresses: Vec<Application>,
    github_daily: Vec<GitHubRepo>,
    github_weekly: Vec<GitHubRepo>,
    github_watched: Vec<GitHubRepo>,
) -> ApiResponse {
    ApiResponse {
        applications: build_applications(config, ingresses),
        links: build_links(config),
        github_daily,
        github_weekly,
        github_watched,
    }
}

#[cfg(test)]
mod tests {
    use super::build_response;
    use super::domain_priority;
    use crate::config::AppOverride;
    use crate::config::Config;
    use crate::config::DescriptionConfig;
    use crate::config::LinkConfig;
    use crate::models::Application;

    fn app(name: &str, url: &str) -> Application {
        Application {
            name: name.to_owned(),
            url: url.to_owned(),
            description: String::new(),
        }
    }

    fn link(name: &str, url: &str) -> LinkConfig {
        LinkConfig {
            name: name.to_owned(),
            url: url.to_owned(),
        }
    }

    fn description(name: &str, description: &str) -> DescriptionConfig {
        DescriptionConfig {
            name: name.to_owned(),
            description: description.to_owned(),
        }
    }

    fn assemble(config: &Config, ingresses: Vec<Application>) -> Vec<Application> {
        build_response(config, ingresses, Vec::new(), Vec::new(), Vec::new()).applications
    }

    #[test]
    fn plain_rkd_pw_outranks_the_internal_suffixes() {
        assert_eq!(domain_priority("https://blog.rkd.pw"), 1);
        assert_eq!(domain_priority("https://blog.h.rkd.pw"), 2);
        assert_eq!(domain_priority("https://blog.k.rkd.pw"), 3);
        assert_eq!(domain_priority("https://example.com"), 4);
    }

    #[test]
    fn duplicate_ingresses_collapse_onto_the_best_domain() {
        let applications = assemble(
            &Config::default(),
            vec![
                app("blog", "https://blog.k.rkd.pw"),
                app("Blog", "https://blog.rkd.pw"),
                app("blog", "https://blog.h.rkd.pw"),
            ],
        );

        assert_eq!(applications.len(), 1);
        assert_eq!(applications[0].url, "https://blog.rkd.pw");
        assert_eq!(applications[0].name, "blog");
    }

    #[test]
    fn a_tie_on_priority_keeps_the_first_ingress() {
        let applications = assemble(
            &Config::default(),
            vec![
                app("blog", "https://first.example.com"),
                app("blog", "https://second.example.com"),
            ],
        );

        assert_eq!(applications[0].url, "https://first.example.com");
    }

    #[test]
    fn exclusions_match_regardless_of_case() {
        let config = Config {
            exclusions: vec!["Compote3".to_owned()],
            ..Config::default()
        };

        let applications = assemble(&config, vec![app("compote3", "https://c.rkd.pw")]);
        assert!(applications.is_empty());
    }

    #[test]
    fn overrides_rename_and_relocate_an_application() {
        let config = Config {
            overrides: vec![AppOverride {
                name: "rkd-compose-grafana".to_owned(),
                new_name: "Grafana".to_owned(),
                url: "https://grafana.k.rkd.pw/d/main".to_owned(),
            }],
            ..Config::default()
        };

        let applications = assemble(
            &config,
            vec![app("rkd-compose-grafana", "https://grafana.k.rkd.pw")],
        );

        assert_eq!(applications[0].name, "grafana");
        assert_eq!(applications[0].url, "https://grafana.k.rkd.pw/d/main");
    }

    #[test]
    fn an_override_matches_an_ingress_name_in_a_different_case() {
        let config = Config {
            overrides: vec![AppOverride {
                name: "grafana".to_owned(),
                new_name: String::new(),
                url: "https://elsewhere.example.com".to_owned(),
            }],
            ..Config::default()
        };

        let applications = assemble(&config, vec![app("GRAFANA", "https://g.rkd.pw")]);

        assert_eq!(applications[0].url, "https://elsewhere.example.com");
    }

    #[test]
    fn dashes_in_a_name_become_spaces() {
        let applications = assemble(&Config::default(), vec![app("irish-schools", "https://s")]);
        assert_eq!(applications[0].name, "irish schools");
    }

    #[test]
    fn a_description_can_be_filed_under_the_overridden_name() {
        let config = Config {
            descriptions: vec![description("grafana", "Dashboards")],
            overrides: vec![AppOverride {
                name: "rkd-compose-grafana".to_owned(),
                new_name: "grafana".to_owned(),
                url: String::new(),
            }],
            ..Config::default()
        };

        let applications = assemble(&config, vec![app("rkd-compose-grafana", "https://g")]);
        assert_eq!(applications[0].description, "Dashboards");
    }

    #[test]
    fn the_original_name_wins_when_both_names_have_a_description() {
        let config = Config {
            descriptions: vec![
                description("rkd-compose-grafana", "By ingress name"),
                description("grafana", "By display name"),
            ],
            overrides: vec![AppOverride {
                name: "rkd-compose-grafana".to_owned(),
                new_name: "grafana".to_owned(),
                url: String::new(),
            }],
            ..Config::default()
        };

        let applications = assemble(&config, vec![app("rkd-compose-grafana", "https://g")]);
        assert_eq!(applications[0].description, "By ingress name");
    }

    #[test]
    fn applications_come_back_sorted_by_name() {
        let applications = assemble(
            &Config::default(),
            vec![
                app("zebra", "https://z.rkd.pw"),
                app("apple", "https://a.rkd.pw"),
                app("banana", "https://b.rkd.pw"),
            ],
        );

        let names: Vec<&str> = applications.iter().map(|a| a.name.as_str()).collect();
        assert_eq!(names, vec!["apple", "banana", "zebra"]);
    }

    #[test]
    fn links_keep_their_configured_case_and_sort_case_insensitively() {
        let config = Config {
            links: vec![
                link("zebra", "https://zebra.com"),
                link("Apple", "https://apple.com"),
                link("banana", "https://banana.com"),
            ],
            descriptions: vec![description("apple", "A fruit")],
            ..Config::default()
        };

        let response = build_response(&config, Vec::new(), Vec::new(), Vec::new(), Vec::new());
        let names: Vec<&str> = response.links.iter().map(|l| l.name.as_str()).collect();

        assert_eq!(names, vec!["Apple", "banana", "zebra"]);
        assert_eq!(response.links[0].description, "A fruit");
    }

    #[test]
    fn an_empty_config_and_no_ingresses_yield_empty_sections() {
        let response = build_response(
            &Config::default(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        );

        assert!(response.applications.is_empty());
        assert!(response.links.is_empty());
        assert!(response.github_daily.is_empty());
    }
}
