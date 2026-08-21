//! Property tests for the parts of compote3 that state an invariant more
//! cleanly than any table of examples does.

use compote3::clock::civil_from_days;
use compote3::clock::days_from_civil;
use compote3::config::AppOverride;
use compote3::config::Config;
use compote3::config::LinkConfig;
use compote3::data::build_response;
use compote3::models::Application;
use proptest::collection::vec;
use proptest::prelude::prop_assert;
use proptest::prelude::prop_assert_eq;
use proptest::prelude::proptest;
use proptest::sample::select;

/// Names short enough to keep the generated templates readable, drawn from an
/// alphabet that cannot itself contain a brace.
fn name_strategy() -> impl proptest::strategy::Strategy<Value = String> {
    proptest::string::string_regex("[a-zA-Z]{1,8}").unwrap_or_else(|_| unreachable!())
}

proptest! {
    /// Whatever the calendar does, a date is the same date after a round trip
    /// through the day count the search qualifier is built from.
    #[test]
    fn a_day_number_survives_a_round_trip_through_a_date(days in -800_000i64..800_000i64) {
        prop_assert_eq!(days_from_civil(civil_from_days(days)), days);
    }

    /// Months and days always land in range, for any day number.
    #[test]
    fn every_day_number_is_a_real_calendar_date(days in -800_000i64..800_000i64) {
        let date = civil_from_days(days);

        prop_assert!((1..=12).contains(&date.month), "month out of range: {:?}", date);
        prop_assert!((1..=31).contains(&date.day), "day out of range: {:?}", date);
    }

    /// The ISO rendering is fixed-width for every date the dashboard can ask
    /// about, which is what makes GitHub accept it.
    #[test]
    fn iso_dates_are_fixed_width(days in 0i64..100_000i64) {
        let rendered = civil_from_days(days).to_iso_date();

        prop_assert_eq!(rendered.len(), 10);
        prop_assert_eq!(rendered.matches('-').count(), 2);
    }

    /// Applications always come back sorted, and an excluded name never
    /// appears no matter how the ingresses were ordered or cased.
    #[test]
    fn applications_are_sorted_and_exclusions_hold(
        names in vec(name_strategy(), 0..8),
        excluded in name_strategy(),
    ) {
        let config = Config {
            exclusions: vec![excluded.to_uppercase()],
            ..Config::default()
        };
        let ingresses: Vec<Application> = names
            .iter()
            .map(|name| Application {
                name: name.clone(),
                url: format!("https://{name}.rkd.pw"),
                description: String::new(),
            })
            .collect();

        let response = build_response(&config, ingresses, Vec::new(), Vec::new(), Vec::new());
        let rendered: Vec<String> = response.applications.iter().map(|a| a.name.clone()).collect();

        let mut sorted = rendered.clone();
        sorted.sort();
        prop_assert_eq!(&rendered, &sorted);
        prop_assert!(!rendered.contains(&excluded.to_lowercase()));
    }

    /// A link's URL reaches the payload untouched, and links carry no
    /// description unless one was configured.
    #[test]
    fn configured_links_survive_intact(names in vec(name_strategy(), 1..6)) {
        let config = Config {
            links: names
                .iter()
                .map(|name| LinkConfig {
                    name: name.clone(),
                    url: format!("https://{name}.example.com"),
                })
                .collect(),
            ..Config::default()
        };

        let response = build_response(&config, Vec::new(), Vec::new(), Vec::new(), Vec::new());

        prop_assert_eq!(response.links.len(), names.len());
        for link in &response.links {
            prop_assert_eq!(&link.url, &format!("https://{}.example.com", link.name));
            prop_assert!(link.description.is_empty());
        }
    }

    /// An override that names an application that is not there changes nothing.
    #[test]
    fn an_override_for_an_absent_application_is_inert(
        present in name_strategy(),
        absent in name_strategy(),
        replacement in select(vec!["renamed".to_owned(), String::new()]),
    ) {
        // Override matching is case-insensitive, so two names differing only
        // in case are the *same* application and the override rightly applies.
        // `name_strategy` is ASCII-only, so an ASCII comparison is exact here.
        proptest::prop_assume!(!present.eq_ignore_ascii_case(&absent));

        let ingresses = vec![Application {
            name: present.clone(),
            url: format!("https://{present}.rkd.pw"),
            description: String::new(),
        }];
        let config = Config {
            overrides: vec![AppOverride {
                name: absent,
                new_name: replacement,
                url: "https://elsewhere.example.com".to_owned(),
            }],
            ..Config::default()
        };

        let response = build_response(&config, ingresses, Vec::new(), Vec::new(), Vec::new());

        prop_assert_eq!(response.applications.len(), 1);
        prop_assert_eq!(
            &response.applications.first().unwrap_or_else(|| unreachable!()).url,
            &format!("https://{present}.rkd.pw")
        );
    }
}
