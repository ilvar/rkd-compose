//! The HTTP surface: the dashboard page and the two JSON endpoints behind it.

use std::sync::Arc;
use std::thread;
use tiny_http::Header;
use tiny_http::Method;
use tiny_http::Request;
use tiny_http::Response;
use tiny_http::Server;
use ureq::Agent;

use crate::config::Config;
use crate::github;
use crate::github::Period;
use crate::k3s;
use crate::k3s::Source;
use crate::kubeconfig::ClusterAccess;
use crate::models::ApiResponse;
use crate::models::Application;

/// The dashboard page, compiled in rather than read from disk so the runtime
/// image needs nothing but the binary and a config file.
const INDEX_HTML: &str = include_str!("../templates/index.html");
const ERROR_HTML: &str = include_str!("../templates/error.html");

/// Everything a request handler needs, shared across worker threads.
pub struct State {
    pub config: Config,
    pub github: github::Client,
    pub cluster: Option<Cluster>,
}

/// A reachable Kubernetes API server and the credentials for it.
pub struct Cluster {
    pub agent: Agent,
    pub access: ClusterAccess,
    pub source: Source,
}

fn header(name: &str, value: &str) -> Option<Header> {
    Header::from_bytes(name.as_bytes(), value.as_bytes()).ok()
}

fn respond(request: Request, status: u16, content_type: &str, body: String) {
    let mut response = Response::from_string(body).with_status_code(status);
    if let Some(header) = header("Content-Type", content_type) {
        response = response.with_header(header);
    }
    if let Err(error) = request.respond(response) {
        eprintln!("warning: failed to send response: {error}");
    }
}

fn respond_html(request: Request, status: u16, body: String) {
    respond(request, status, "text/html; charset=utf-8", body);
}

fn respond_json(request: Request, status: u16, body: String) {
    respond(request, status, "application/json; charset=utf-8", body);
}

/// Renders `error.html`, whose single placeholder the Go original filled with
/// Go's own template engine.
fn error_page(message: &str) -> String {
    ERROR_HTML.replace("{{.error}}", &escape_html(message))
}

fn escape_html(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// Serializes a payload, falling back to a JSON error object if that fails.
fn to_json<T: serde::Serialize>(value: &T) -> (u16, String) {
    match serde_json::to_string(value) {
        Ok(body) => (200, body),
        Err(error) => (
            500,
            error_json(&format!("failed to serialize response: {error}")),
        ),
    }
}

/// A `{"error": ...}` document whose message cannot break out of its string,
/// however the underlying error happens to be worded.
fn error_json(message: &str) -> String {
    let encoded =
        serde_json::to_string(message).unwrap_or_else(|_| "\"internal error\"".to_owned());
    format!(r#"{{"error":{encoded}}}"#)
}

/// Runs a fetch, degrading a failure to an empty section with a warning —
/// one unreachable source must not blank the whole dashboard.
fn or_empty<T>(label: &str, result: Result<Vec<T>, String>) -> Vec<T> {
    match result {
        Ok(values) => values,
        Err(error) => {
            eprintln!("warning: failed to get {label}: {error}");
            Vec::new()
        }
    }
}

/// A panicking worker is reported like any other failure: the section comes
/// back empty and the rest of the dashboard still renders.
fn panicked<T>(label: &str) -> Result<Vec<T>, String> {
    Err(format!("the {label} fetch panicked"))
}

fn fetch_ingresses(cluster: Option<&Cluster>) -> Result<Vec<Application>, String> {
    let Some(cluster) = cluster else {
        return Ok(Vec::new());
    };

    // Projected service account tokens rotate under a long-running process.
    let mut access = cluster.access.clone();
    if let Some(token) = k3s::refreshed_token(cluster.source) {
        access.token = Some(token);
    }

    k3s::ingresses(&cluster.agent, &access)
}

/// Gathers every section of the dashboard. The four sources are independent,
/// so they are fetched at the same time and the page waits only for the
/// slowest one instead of the sum.
pub fn collect(state: &State) -> ApiResponse {
    let now = std::time::SystemTime::now();

    let (ingresses, daily, weekly, watched) = thread::scope(|scope| {
        let ingresses = scope.spawn(|| fetch_ingresses(state.cluster.as_ref()));
        let daily = scope.spawn(|| github::trending(&state.github, Period::Daily, now));
        let weekly = scope.spawn(|| github::trending(&state.github, Period::Weekly, now));
        let watched = scope.spawn(|| github::watched(&state.github, &state.config.github.watcher));

        (
            ingresses.join(),
            daily.join(),
            weekly.join(),
            watched.join(),
        )
    });

    crate::data::build_response(
        &state.config,
        or_empty(
            "k3s ingresses",
            ingresses.unwrap_or_else(|_| panicked("k3s ingress")),
        ),
        or_empty(
            "GitHub daily trending",
            daily.unwrap_or_else(|_| panicked("GitHub daily trending")),
        ),
        or_empty(
            "GitHub weekly trending",
            weekly.unwrap_or_else(|_| panicked("GitHub weekly trending")),
        ),
        or_empty(
            "watched repos",
            watched.unwrap_or_else(|_| panicked("watched repos")),
        ),
    )
}

fn handle(state: &State, request: Request) {
    // Query strings and fragments are not part of any route compote3 serves.
    let path = request
        .url()
        .split(['?', '#'])
        .next()
        .unwrap_or("")
        .to_owned();

    match (request.method(), path.as_str()) {
        (Method::Get, "/") => respond_html(request, 200, INDEX_HTML.to_owned()),
        (Method::Get, "/api/data") => {
            let (status, body) = to_json(&collect(state));
            respond_json(request, status, body);
        }
        _ => respond_html(request, 404, error_page("Not found")),
    }
}

/// Serves until the process is stopped.
///
/// `workers` threads take requests off the same queue, so one slow dashboard
/// refresh does not hold up the next request.
pub fn serve(state: State, address: &str, workers: usize) -> Result<(), String> {
    let server =
        Server::http(address).map_err(|error| format!("failed to listen on {address}: {error}"))?;
    let server = Arc::new(server);
    let state = Arc::new(state);

    eprintln!("Starting server on {address}");

    thread::scope(|scope| {
        for _ in 0..workers.max(1) {
            let server = Arc::clone(&server);
            let state = Arc::clone(&state);
            let _ = scope.spawn(move || loop {
                match server.recv() {
                    Ok(request) => handle(&state, request),
                    Err(error) => {
                        eprintln!("warning: failed to accept a request: {error}");
                        return;
                    }
                }
            });
        }
    });

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::error_json;
    use super::error_page;
    use super::escape_html;
    use super::ERROR_HTML;
    use super::INDEX_HTML;

    #[test]
    fn the_dashboard_page_is_compiled_into_the_binary() {
        assert!(INDEX_HTML.contains("/api/data"));
        assert!(ERROR_HTML.contains("{{.error}}"));
    }

    #[test]
    fn the_error_page_substitutes_and_escapes_its_message() {
        let page = error_page("<script>alert(1)</script>");

        assert!(!page.contains("{{.error}}"));
        assert!(page.contains("&lt;script&gt;"));
        assert!(!page.contains("<script>"));
    }

    #[test]
    fn html_escaping_covers_the_attribute_delimiters() {
        assert_eq!(escape_html(r#"a&b<c>"d""#), "a&amp;b&lt;c&gt;&quot;d&quot;");
    }

    #[test]
    fn an_error_message_cannot_break_out_of_its_json_string() {
        assert_eq!(
            error_json(r#"a "quoted" \ message"#),
            r#"{"error":"a \"quoted\" \\ message"}"#
        );
    }
}
