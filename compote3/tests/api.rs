//! End-to-end tests of the HTTP surface: a real listener, real requests, and
//! a stub standing in for the GitHub REST API.

use compote3::config::AppOverride;
use compote3::config::Config;
use compote3::config::DescriptionConfig;
use compote3::config::LinkConfig;
use compote3::github;
use compote3::k3s::Source;
use compote3::kubeconfig::ClusterAccess;
use compote3::models::ApiResponse;
use compote3::models::TemplateParseResponse;
use compote3::server;
use compote3::server::Cluster;
use compote3::server::State;
use std::io::Read;
use std::io::Write;
use std::net::TcpListener;
use std::net::TcpStream;
use std::thread;
use std::time::Duration;
use std::time::Instant;
use tiny_http::Response;
use tiny_http::Server;
use ureq::Agent;

const SEARCH_BODY: &str = r#"{"items":[
    {"name":"trending","full_name":"user/trending","description":"A trending repo",
     "html_url":"https://github.com/user/trending","stargazers_count":1000,
     "language":"Rust","updated_at":"2025-01-05T00:00:00Z"}]}"#;

const INGRESS_BODY: &str = r#"{"items":[
    {"metadata":{"name":"blog"},
     "spec":{"rules":[{"host":"blog.k.rkd.pw"}],"tls":[{"hosts":["blog.k.rkd.pw"]}]}},
    {"metadata":{"name":"blog"},
     "spec":{"rules":[{"host":"blog.rkd.pw"}],"tls":[{"hosts":["blog.rkd.pw"]}]}},
    {"metadata":{"name":"rkd-compose-grafana"},
     "spec":{"rules":[{"host":"grafana.k.rkd.pw"}],"tls":[{"hosts":["grafana.k.rkd.pw"]}]}},
    {"metadata":{"name":"irish-schools"},"spec":{"rules":[{"host":"schools.rkd.pw"}]}},
    {"metadata":{"name":"compote3"},"spec":{"rules":[{"host":"c.rkd.pw"}]}}]}"#;

const STARRED_BODY: &str = r#"[
    {"name":"watched","full_name":"user/watched","description":null,
     "html_url":"https://github.com/user/watched","stargazers_count":500,
     "language":null,"updated_at":"2025-01-04T00:00:00Z"}]"#;

/// A port the OS picked and then released. Racy in principle; in practice the
/// kernel does not hand the same ephemeral port out twice in a row.
fn free_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("a free port");
    let port = listener.local_addr().expect("a bound address").port();
    drop(listener);
    port
}

/// Serves canned GitHub responses on `port` until the test process exits.
fn spawn_github_stub(port: u16) {
    let server = Server::http(("127.0.0.1", port)).expect("stub listens");
    let _ = thread::spawn(move || {
        while let Ok(request) = server.recv() {
            let url = request.url().to_owned();
            let body = if url.starts_with("/search/repositories") {
                SEARCH_BODY
            } else if url.contains("/starred") {
                // Page 2 onwards is empty, which ends pagination.
                if url.contains("page=1") {
                    STARRED_BODY
                } else {
                    "[]"
                }
            } else {
                "{}"
            };
            let _ = request.respond(Response::from_string(body));
        }
    });
}

/// Serves one canned ingress list on `port`.
fn spawn_kubernetes_stub(port: u16) {
    let server = Server::http(("127.0.0.1", port)).expect("stub listens");
    let _ = thread::spawn(move || {
        while let Ok(request) = server.recv() {
            let body = if request
                .url()
                .starts_with("/apis/networking.k8s.io/v1/ingresses")
            {
                INGRESS_BODY
            } else {
                "{}"
            };
            let _ = request.respond(Response::from_string(body));
        }
    });
}

fn spawn_compote(port: u16, github_root: &str, config: Config) {
    spawn_compote_with_cluster(port, github_root, config, None);
}

fn spawn_compote_with_cluster(
    port: u16,
    github_root: &str,
    config: Config,
    cluster: Option<Cluster>,
) {
    let github = github::Client::with_root(Agent::new_with_defaults(), None, github_root);
    let state = State {
        config,
        github,
        cluster,
    };
    let address = format!("127.0.0.1:{port}");
    let _ = thread::spawn(move || {
        let _ = server::serve(state, &address, 4);
    });
}

/// A minimal HTTP/1.0 client: no keep-alive, so the response ends at EOF.
fn request(port: u16, head: &str, body: &str) -> (u16, String) {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        match TcpStream::connect(("127.0.0.1", port)) {
            Ok(mut stream) => {
                let request = format!(
                    "{head} HTTP/1.0\r\nHost: localhost\r\nContent-Length: {}\r\n\
                     Content-Type: application/json\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                stream.write_all(request.as_bytes()).expect("request sent");
                stream.flush().expect("request flushed");

                let mut raw = String::new();
                let _ = stream.read_to_string(&mut raw).expect("response read");

                let status = raw
                    .split_whitespace()
                    .nth(1)
                    .and_then(|code| code.parse().ok())
                    .unwrap_or(0);
                let body = raw
                    .split_once("\r\n\r\n")
                    .map(|(_, rest)| rest)
                    .unwrap_or("");
                return (status, body.to_owned());
            }
            Err(error) => {
                assert!(Instant::now() < deadline, "server never came up: {error}");
                thread::sleep(Duration::from_millis(20));
            }
        }
    }
}

fn test_config() -> Config {
    Config {
        links: vec![LinkConfig {
            name: "Test Link".to_owned(),
            url: "https://test.com".to_owned(),
        }],
        descriptions: vec![DescriptionConfig {
            name: "test link".to_owned(),
            description: "A configured link".to_owned(),
        }],
        github: compote3::config::GitHubConfig {
            watcher: "testuser".to_owned(),
        },
        ..Config::default()
    }
}

#[test]
fn the_dashboard_serves_every_route_it_advertises() {
    let github_port = free_port();
    let compote_port = free_port();
    spawn_github_stub(github_port);
    spawn_compote(
        compote_port,
        &format!("http://127.0.0.1:{github_port}"),
        test_config(),
    );

    // The dashboard page.
    let (status, body) = request(compote_port, "GET /", "");
    assert_eq!(status, 200);
    assert!(body.contains("/api/data"), "index.html was not served");

    // The data endpoint, assembled from config plus the GitHub stub.
    let (status, body) = request(compote_port, "GET /api/data", "");
    assert_eq!(status, 200, "body: {body}");
    let data: ApiResponse = serde_json::from_str(&body).expect("payload is JSON");

    assert!(
        data.applications.is_empty(),
        "no cluster is configured in this test"
    );
    assert_eq!(data.links.len(), 1);
    assert_eq!(data.links[0].name, "Test Link");
    assert_eq!(data.links[0].url, "https://test.com");
    assert_eq!(data.links[0].description, "A configured link");

    assert_eq!(data.github_daily.len(), 1);
    assert_eq!(data.github_daily[0].full_name, "user/trending");
    assert_eq!(data.github_daily[0].star_count, 1000);
    assert_eq!(data.github_weekly.len(), 1);

    assert_eq!(data.github_watched.len(), 1);
    assert_eq!(data.github_watched[0].full_name, "user/watched");
    // `description: null` and `language: null` must not become the string "null".
    assert_eq!(data.github_watched[0].description, "");
    assert_eq!(data.github_watched[0].language, "");

    // Template parsing.
    let (status, body) = request(
        compote_port,
        "POST /api/templates/parse",
        r#"{"template":"{{ Фамилия }}{{ Имя }}{{ Фамилия }}"}"#,
    );
    assert_eq!(status, 200, "body: {body}");
    let parsed: TemplateParseResponse = serde_json::from_str(&body).expect("payload is JSON");
    assert_eq!(parsed.variables, vec!["Фамилия", "Имя"]);

    // An empty result is an array, never null.
    let (status, body) = request(
        compote_port,
        "POST /api/templates/parse",
        r#"{"template":"nothing here"}"#,
    );
    assert_eq!(status, 200);
    assert_eq!(body, r#"{"variables":[]}"#);

    // A malformed body is rejected, not treated as an empty template.
    let (status, _) = request(compote_port, "POST /api/templates/parse", "not json");
    assert_eq!(status, 400);

    // Unknown routes render the error page.
    let (status, body) = request(compote_port, "GET /nope", "");
    assert_eq!(status, 404);
    assert!(body.contains("Not found"), "error page was not rendered");
}

#[test]
fn an_unconfigured_watcher_leaves_the_watched_section_empty() {
    let github_port = free_port();
    let compote_port = free_port();
    spawn_github_stub(github_port);
    spawn_compote(
        compote_port,
        &format!("http://127.0.0.1:{github_port}"),
        Config::default(),
    );

    let (status, body) = request(compote_port, "GET /api/data", "");
    assert_eq!(status, 200, "body: {body}");

    let data: ApiResponse = serde_json::from_str(&body).expect("payload is JSON");
    assert!(data.github_watched.is_empty());
    assert_eq!(data.github_daily.len(), 1);
}

#[test]
fn an_unreachable_github_empties_only_the_github_sections() {
    // Nothing is listening on this port, so every GitHub call fails.
    let github_port = free_port();
    let compote_port = free_port();
    spawn_compote(
        compote_port,
        &format!("http://127.0.0.1:{github_port}"),
        test_config(),
    );

    let (status, body) = request(compote_port, "GET /api/data", "");
    assert_eq!(status, 200, "body: {body}");

    let data: ApiResponse = serde_json::from_str(&body).expect("payload is JSON");
    assert!(data.github_daily.is_empty());
    assert!(data.github_weekly.is_empty());
    assert!(data.github_watched.is_empty());
    assert_eq!(data.links.len(), 1, "configured links still render");
}

#[test]
fn ingresses_become_application_tiles_through_the_whole_pipeline() {
    let github_port = free_port();
    let kubernetes_port = free_port();
    let compote_port = free_port();
    spawn_github_stub(github_port);
    spawn_kubernetes_stub(kubernetes_port);

    let access = ClusterAccess {
        server: format!("http://127.0.0.1:{kubernetes_port}"),
        ..ClusterAccess::default()
    };
    let cluster = Cluster {
        agent: compote3::k3s::agent_for(&access).expect("agent builds"),
        access,
        source: Source::KubeConfig,
    };

    let config = Config {
        exclusions: vec!["Compote3".to_owned()],
        overrides: vec![AppOverride {
            name: "rkd-compose-grafana".to_owned(),
            new_name: "grafana".to_owned(),
            url: "https://grafana.k.rkd.pw/d/main".to_owned(),
        }],
        descriptions: vec![DescriptionConfig {
            name: "grafana".to_owned(),
            description: "Dashboards".to_owned(),
        }],
        ..Config::default()
    };

    spawn_compote_with_cluster(
        compote_port,
        &format!("http://127.0.0.1:{github_port}"),
        config,
        Some(cluster),
    );

    let (status, body) = request(compote_port, "GET /api/data", "");
    assert_eq!(status, 200, "body: {body}");
    let data: ApiResponse = serde_json::from_str(&body).expect("payload is JSON");

    let names: Vec<&str> = data
        .applications
        .iter()
        .map(|app| app.name.as_str())
        .collect();

    // "compote3" is excluded, the two "blog" ingresses collapse onto the
    // plain domain, "rkd-compose-grafana" is renamed, and dashes became spaces.
    assert_eq!(names, vec!["blog", "grafana", "irish schools"]);

    let blog = data.applications.first().expect("blog tile");
    assert_eq!(blog.url, "https://blog.rkd.pw");

    let grafana = data.applications.get(1).expect("grafana tile");
    assert_eq!(grafana.url, "https://grafana.k.rkd.pw/d/main");
    assert_eq!(grafana.description, "Dashboards");

    let schools = data.applications.get(2).expect("schools tile");
    assert_eq!(schools.url, "http://schools.rkd.pw");
}
