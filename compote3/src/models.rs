//! Wire types shared by the HTTP API and the frontend.
//!
//! Field names and `serde` renames are load-bearing: `templates/index.html`
//! reads `stargazers_count`, `full_name` and `html_url` straight off the JSON.

use serde::Deserialize;
use serde::Serialize;

/// A dashboard tile: an application discovered from an ingress, or a
/// configured link. Both render through the same frontend component.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct Application {
    pub name: String,
    pub url: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub description: String,
}

/// A GitHub repository as the dashboard displays it.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct GitHubRepo {
    pub name: String,
    pub full_name: String,
    pub description: String,
    pub html_url: String,
    #[serde(rename = "stargazers_count")]
    pub star_count: i64,
    pub language: String,
    /// RFC 3339 UTC timestamp exactly as GitHub returned it, or empty when the
    /// API omitted it. Only used for sorting; the frontend ignores it.
    pub updated_at: String,
}

/// The whole payload behind `GET /api/data`.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ApiResponse {
    pub applications: Vec<Application>,
    pub links: Vec<Application>,
    pub github_daily: Vec<GitHubRepo>,
    pub github_weekly: Vec<GitHubRepo>,
    pub github_watched: Vec<GitHubRepo>,
}

/// Request body of `POST /api/templates/parse`.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TemplateParseRequest {
    pub template: String,
}

/// Response body of `POST /api/templates/parse`.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TemplateParseResponse {
    pub variables: Vec<String>,
}
