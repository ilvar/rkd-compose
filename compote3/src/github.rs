//! GitHub sections of the dashboard.
//!
//! "Trending" is not an API GitHub offers, so — as in the Go version — it is
//! approximated with a repository search bounded by recent push activity.

use serde::Deserialize;
use std::time::SystemTime;
use ureq::Agent;

use crate::clock::date_days_before;
use crate::models::GitHubRepo;

/// How many repositories each section shows. The frontend lays them out in a
/// grid that divides evenly at 18.
pub const SECTION_SIZE: usize = 18;

/// How many starred repositories to collect before sorting and truncating, so
/// the newest-updated 18 are chosen from a meaningful pool.
const WATCHED_POOL: usize = 50;

const PER_PAGE_WATCHED: usize = 50;

/// Default REST API root. Overridable so tests can point the client at a stub
/// instead of reaching the real API.
pub const API_ROOT: &str = "https://api.github.com";

/// Which trending window to ask for.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Period {
    Daily,
    Weekly,
}

impl Period {
    /// Days of push activity the window covers.
    fn days(self) -> i64 {
        match self {
            Period::Daily => 1,
            Period::Weekly => 7,
        }
    }
}

/// A repository as the GitHub REST API returns it. Every display field is
/// optional there, and `null` is common for `description` and `language`.
#[derive(Debug, Deserialize)]
struct ApiRepo {
    #[serde(default)]
    name: String,
    #[serde(default)]
    full_name: String,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    html_url: String,
    #[serde(default)]
    stargazers_count: i64,
    #[serde(default)]
    language: Option<String>,
    #[serde(default)]
    updated_at: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SearchResponse {
    #[serde(default)]
    items: Vec<ApiRepo>,
}

impl From<ApiRepo> for GitHubRepo {
    fn from(repo: ApiRepo) -> Self {
        GitHubRepo {
            name: repo.name,
            full_name: repo.full_name,
            description: repo.description.unwrap_or_default(),
            html_url: repo.html_url,
            star_count: repo.stargazers_count,
            language: repo.language.unwrap_or_default(),
            updated_at: repo.updated_at.unwrap_or_default(),
        }
    }
}

/// A GitHub REST client. `token` is optional but strongly recommended: the
/// unauthenticated search endpoint allows only 10 requests a minute.
pub struct Client {
    agent: Agent,
    token: Option<String>,
    root: String,
}

impl Client {
    pub fn new(agent: Agent, token: Option<String>) -> Self {
        Client::with_root(agent, token, API_ROOT)
    }

    /// A client against a specific API root.
    pub fn with_root(agent: Agent, token: Option<String>, root: &str) -> Self {
        Client {
            agent,
            token: token.filter(|token| !token.is_empty()),
            root: root.trim_end_matches('/').to_owned(),
        }
    }

    fn get(&self, url: &str) -> Result<String, String> {
        let mut request = self
            .agent
            .get(url)
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .header("User-Agent", "compote3");

        if let Some(token) = &self.token {
            request = request.header("Authorization", &format!("Bearer {token}"));
        }

        let mut response = request
            .call()
            .map_err(|error| format!("GET {url} failed: {error}"))?;

        response
            .body_mut()
            .read_to_string()
            .map_err(|error| format!("GET {url} returned an unreadable body: {error}"))
    }
}

/// The search query for a trending window: popular repositories pushed to
/// within the window. `now` is injected so the query is testable.
fn trending_query(period: Period, now: SystemTime) -> String {
    let base = "stars:>100";
    match date_days_before(now, period.days()) {
        Some(since) => format!("{base} pushed:>{}", since.to_iso_date()),
        // A clock we cannot make sense of degrades to the unbounded query
        // rather than to no results at all.
        None => base.to_owned(),
    }
}

/// Percent-encodes the characters GitHub's search query syntax collides with.
fn encode_query(query: &str) -> String {
    let mut encoded = String::with_capacity(query.len());
    for byte in query.bytes() {
        let unreserved = byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~');
        if unreserved {
            encoded.push(char::from(byte));
        } else {
            encoded.push_str(&format!("%{byte:02X}"));
        }
    }
    encoded
}

/// Trending repositories for a window, most-starred first.
pub fn trending(
    client: &Client,
    period: Period,
    now: SystemTime,
) -> Result<Vec<GitHubRepo>, String> {
    let query = encode_query(&trending_query(period, now));
    let url = format!(
        "{}/search/repositories?q={query}&sort=stars&order=desc&per_page={SECTION_SIZE}",
        client.root
    );

    let body = client.get(&url)?;
    let response: SearchResponse = serde_json::from_str(&body)
        .map_err(|error| format!("failed to parse GitHub search response: {error}"))?;

    Ok(response
        .items
        .into_iter()
        .map(GitHubRepo::from)
        .take(SECTION_SIZE)
        .collect())
}

/// Repositories `username` has starred, most recently updated first.
///
/// An empty username is not an error — the section is simply not configured.
pub fn watched(client: &Client, username: &str) -> Result<Vec<GitHubRepo>, String> {
    if username.is_empty() {
        return Ok(Vec::new());
    }

    let mut collected: Vec<GitHubRepo> = Vec::new();
    let mut page = 1;
    while collected.len() < WATCHED_POOL {
        let url = format!(
            "{}/users/{}/starred?per_page={PER_PAGE_WATCHED}&page={page}",
            client.root,
            encode_query(username)
        );

        let body = client
            .get(&url)
            .map_err(|error| format!("failed to get starred repos for {username}: {error}"))?;
        let repos: Vec<ApiRepo> = serde_json::from_str(&body)
            .map_err(|error| format!("failed to parse starred repos for {username}: {error}"))?;

        if repos.is_empty() {
            break;
        }

        // A short page is the last page; asking for the next one would only
        // spend rate limit on an empty answer.
        let last_page = repos.len() < PER_PAGE_WATCHED;
        collected.extend(
            repos
                .into_iter()
                .map(GitHubRepo::from)
                .take(WATCHED_POOL - collected.len()),
        );
        if last_page {
            break;
        }
        page += 1;
    }

    Ok(rank_watched(collected))
}

/// Deduplicates by full name, then orders by update time, newest first.
///
/// GitHub returns `updated_at` as an RFC 3339 UTC instant with fixed-width
/// fields, so a byte-wise reverse ordering is a chronological one.
fn rank_watched(repos: Vec<GitHubRepo>) -> Vec<GitHubRepo> {
    let mut seen: Vec<String> = Vec::new();
    let mut unique: Vec<GitHubRepo> = Vec::new();
    for repo in repos {
        if seen.contains(&repo.full_name) {
            continue;
        }
        seen.push(repo.full_name.clone());
        unique.push(repo);
    }

    unique.sort_by(|left, right| right.updated_at.cmp(&left.updated_at));
    unique.truncate(SECTION_SIZE);
    unique
}

#[cfg(test)]
mod tests {
    use super::encode_query;
    use super::rank_watched;
    use super::trending_query;
    use super::ApiRepo;
    use super::Period;
    use super::SECTION_SIZE;
    use crate::models::GitHubRepo;
    use std::time::Duration;
    use std::time::UNIX_EPOCH;

    fn repo(full_name: &str, updated_at: &str) -> GitHubRepo {
        GitHubRepo {
            full_name: full_name.to_owned(),
            updated_at: updated_at.to_owned(),
            ..GitHubRepo::default()
        }
    }

    #[test]
    fn the_daily_window_is_one_day_and_the_weekly_seven() {
        let now = UNIX_EPOCH + Duration::from_secs(20_322 * 86_400);

        assert_eq!(
            trending_query(Period::Daily, now),
            "stars:>100 pushed:>2025-08-21"
        );
        assert_eq!(
            trending_query(Period::Weekly, now),
            "stars:>100 pushed:>2025-08-15"
        );
    }

    #[test]
    fn query_encoding_escapes_the_search_syntax() {
        assert_eq!(
            encode_query("stars:>100 pushed:>2025-08-21"),
            "stars%3A%3E100%20pushed%3A%3E2025-08-21"
        );
    }

    #[test]
    fn watched_repos_are_deduplicated_by_full_name() {
        let ranked = rank_watched(vec![
            repo("user/one", "2025-01-03T00:00:00Z"),
            repo("user/two", "2025-01-02T00:00:00Z"),
            repo("user/one", "2025-01-01T00:00:00Z"),
        ]);

        assert_eq!(ranked.len(), 2);
        assert_eq!(ranked[0].full_name, "user/one");
        assert_eq!(ranked[0].updated_at, "2025-01-03T00:00:00Z");
    }

    #[test]
    fn watched_repos_are_newest_first_and_capped_at_a_section() {
        let repos: Vec<GitHubRepo> = (0..25)
            .map(|index| {
                repo(
                    &format!("user/repo{index}"),
                    &format!("2025-01-{:02}T00:00:00Z", index + 1),
                )
            })
            .collect();

        let ranked = rank_watched(repos);

        assert_eq!(ranked.len(), SECTION_SIZE);
        assert_eq!(ranked[0].full_name, "user/repo24");
        assert_eq!(ranked[1].full_name, "user/repo23");
    }

    #[test]
    fn null_description_and_language_become_empty_strings() {
        let parsed: ApiRepo = serde_json::from_str(
            r#"{"name":"r","full_name":"u/r","description":null,"html_url":"https://x",
                "stargazers_count":7,"language":null,"updated_at":"2025-01-01T00:00:00Z"}"#,
        )
        .expect("repo parses");

        let repo = GitHubRepo::from(parsed);
        assert_eq!(repo.description, "");
        assert_eq!(repo.language, "");
        assert_eq!(repo.star_count, 7);
    }

    #[test]
    fn a_search_response_missing_items_is_empty_rather_than_an_error() {
        let parsed: super::SearchResponse =
            serde_json::from_str(r#"{"total_count":0}"#).expect("response parses");
        assert!(parsed.items.is_empty());
    }
}
