//! The configuration compote3 actually runs with lives in the Helm chart, not
//! in this directory. Parsing is strict — an unknown key is an error — so the
//! chart's copy is checked here rather than in production.

use serde::Deserialize;

#[derive(Deserialize)]
struct Values {
    compote3: Compote3Values,
}

#[derive(Deserialize)]
struct Compote3Values {
    config: String,
}

#[test]
fn the_config_shipped_by_the_helm_chart_parses() {
    let values: Values = serde_yaml_ng::from_str(include_str!("../../apps-chart/values.yaml"))
        .expect("apps-chart/values.yaml has a compote3.config block");

    let config =
        compote3::config::parse(&values.compote3.config).expect("the deployed config parses");

    assert!(
        !config.links.is_empty(),
        "the dashboard would have no links"
    );
    assert!(
        !config.descriptions.is_empty(),
        "the dashboard would have no descriptions"
    );
}

#[test]
fn the_committed_config_parses() {
    let config =
        compote3::config::parse(include_str!("../config.yaml")).expect("config.yaml parses");

    assert_eq!(config.github.watcher, "ilvar");
    assert!(!config.exclusions.is_empty());
    assert!(!config.overrides.is_empty());
}
