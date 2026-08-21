//! Discovery of dashboard tiles from Kubernetes ingresses.
//!
//! The Go original used `client-go`; all compote3 actually needs is one
//! authenticated `GET` against a single collection, so this speaks to the API
//! server directly.

use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::Path;
use std::time::Duration;
use ureq::tls::Certificate;
use ureq::tls::ClientCert;
use ureq::tls::PrivateKey;
use ureq::tls::RootCerts;
use ureq::tls::TlsConfig;
use ureq::Agent;

use crate::kubeconfig;
use crate::kubeconfig::ClusterAccess;
use crate::models::Application;
use crate::sys::capability;

/// Where the kubelet projects a pod's service account credentials.
const SERVICE_ACCOUNT_DIR: &str = "/var/run/secrets/kubernetes.io/serviceaccount";
const INGRESS_PATH: &str = "/apis/networking.k8s.io/v1/ingresses";
const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);

/// How compote3 authenticated to the API server, for logging.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Source {
    /// The pod's own service account.
    InCluster,
    /// A kubeconfig on disk.
    KubeConfig,
    /// Neither is available; the dashboard runs without an applications section.
    Unavailable,
}

#[derive(Debug, Deserialize)]
struct IngressList {
    #[serde(default)]
    items: Vec<Ingress>,
}

#[derive(Debug, Deserialize)]
struct Ingress {
    #[serde(default)]
    metadata: Metadata,
    #[serde(default)]
    spec: IngressSpec,
}

#[derive(Debug, Default, Deserialize)]
struct Metadata {
    #[serde(default)]
    name: String,
}

#[derive(Debug, Default, Deserialize)]
struct IngressSpec {
    #[serde(default)]
    rules: Vec<IngressRule>,
    /// Only the presence of a TLS block matters: it decides the scheme.
    #[serde(default)]
    tls: Vec<serde_json::Value>,
}

#[derive(Debug, Default, Deserialize)]
struct IngressRule {
    #[serde(default)]
    host: String,
}

/// Turns an ingress list into dashboard tiles.
///
/// One tile per host URL: an ingress that serves several hosts contributes
/// several, and the first ingress to claim a URL names it. The result is
/// ordered by URL so the same cluster always produces the same list.
fn applications_from(list: IngressList) -> Vec<Application> {
    let mut by_url: BTreeMap<String, Application> = BTreeMap::new();

    for ingress in list.items {
        let secured = !ingress.spec.tls.is_empty();
        for rule in ingress.spec.rules {
            if rule.host.is_empty() {
                continue;
            }
            let scheme = if secured { "https" } else { "http" };
            let url = format!("{scheme}://{}", rule.host);
            let name = if ingress.metadata.name.is_empty() {
                rule.host.clone()
            } else {
                ingress.metadata.name.clone()
            };
            let _ = by_url.entry(url.clone()).or_insert(Application {
                name,
                url,
                description: String::new(),
            });
        }
    }

    by_url.into_values().collect()
}

/// The pod's own credentials, when running inside a cluster.
fn in_cluster_access() -> Option<ClusterAccess> {
    let host = capability::env_var("KUBERNETES_SERVICE_HOST")?;
    let port = capability::env_var("KUBERNETES_SERVICE_PORT")?;
    let directory = Path::new(SERVICE_ACCOUNT_DIR);
    let token = capability::read_to_string(&directory.join("token")).ok()?;

    Some(ClusterAccess {
        server: format!("https://{host}:{port}"),
        certificate_authority: capability::read_bytes(&directory.join("ca.crt")).ok(),
        insecure_skip_tls_verify: false,
        token: Some(token.trim().to_owned()),
        client_certificate: None,
        client_key: None,
    })
}

/// Locates cluster credentials: the service account first, a kubeconfig
/// second, and nothing at all as a supported outcome — the GitHub and links
/// sections of the dashboard do not need Kubernetes.
pub fn discover_access() -> (Option<ClusterAccess>, Source) {
    if let Some(access) = in_cluster_access() {
        return (Some(access), Source::InCluster);
    }

    let Some(path) = kubeconfig::default_path() else {
        return (None, Source::Unavailable);
    };
    if !capability::exists(&path) {
        return (None, Source::Unavailable);
    }

    match kubeconfig::load(&path) {
        Ok(access) => (Some(access), Source::KubeConfig),
        Err(error) => {
            eprintln!(
                "warning: ignoring unusable kubeconfig {}: {error}",
                path.display()
            );
            (None, Source::Unavailable)
        }
    }
}

/// Builds an HTTP agent that trusts — and authenticates to — this cluster.
pub fn agent_for(access: &ClusterAccess) -> Result<Agent, String> {
    let mut tls = TlsConfig::builder().disable_verification(access.insecure_skip_tls_verify);

    if let Some(pem) = &access.certificate_authority {
        let certificate = Certificate::from_pem(pem)
            .map_err(|error| format!("cluster certificate authority is not valid PEM: {error}"))?;
        tls = tls.root_certs(RootCerts::new_with_certs(&[certificate]));
    }

    if let (Some(cert_pem), Some(key_pem)) = (&access.client_certificate, &access.client_key) {
        let certificate = Certificate::from_pem(cert_pem)
            .map_err(|error| format!("client certificate is not valid PEM: {error}"))?;
        let key = PrivateKey::from_pem(key_pem)
            .map_err(|error| format!("client key is not valid PEM: {error}"))?;
        tls = tls.client_cert(Some(ClientCert::new_with_certs(&[certificate], key)));
    }

    Ok(Agent::config_builder()
        .tls_config(tls.build())
        .timeout_global(Some(REQUEST_TIMEOUT))
        .build()
        .into())
}

/// Re-reads the projected service account token.
///
/// Projected tokens are short-lived and rotated in place, so the value read at
/// startup goes stale while the process keeps running.
pub fn refreshed_token(source: Source) -> Option<String> {
    match source {
        Source::InCluster => {
            let path = Path::new(SERVICE_ACCOUNT_DIR).join("token");
            capability::read_to_string(&path)
                .ok()
                .map(|token| token.trim().to_owned())
        }
        Source::KubeConfig => None,
        Source::Unavailable => None,
    }
}

/// Lists ingresses across all namespaces and renders them as tiles.
pub fn ingresses(agent: &Agent, access: &ClusterAccess) -> Result<Vec<Application>, String> {
    let url = format!("{}{INGRESS_PATH}", access.server);
    let mut request = agent.get(&url).header("Accept", "application/json");
    if let Some(token) = &access.token {
        request = request.header("Authorization", &format!("Bearer {token}"));
    }

    let mut response = request
        .call()
        .map_err(|error| format!("failed to list ingresses: {error}"))?;
    let body = response
        .body_mut()
        .read_to_string()
        .map_err(|error| format!("failed to read the ingress list: {error}"))?;

    let list: IngressList = serde_json::from_str(&body)
        .map_err(|error| format!("failed to parse the ingress list: {error}"))?;

    Ok(applications_from(list))
}

#[cfg(test)]
mod tests {
    use super::applications_from;
    use super::IngressList;

    fn parse(json: &str) -> Vec<super::Application> {
        let list: IngressList = serde_json::from_str(json).expect("ingress list parses");
        applications_from(list)
    }

    #[test]
    fn a_tls_ingress_becomes_an_https_tile_named_after_the_ingress() {
        let apps = parse(
            r#"{"items":[{"metadata":{"name":"blog"},
                 "spec":{"rules":[{"host":"blog.rkd.pw"}],"tls":[{"hosts":["blog.rkd.pw"]}]}}]}"#,
        );

        assert_eq!(apps.len(), 1);
        assert_eq!(apps[0].name, "blog");
        assert_eq!(apps[0].url, "https://blog.rkd.pw");
    }

    #[test]
    fn an_ingress_without_tls_is_served_over_http() {
        let apps =
            parse(r#"{"items":[{"metadata":{"name":"nas"},"spec":{"rules":[{"host":"nas"}]}}]}"#);
        assert_eq!(apps[0].url, "http://nas");
    }

    #[test]
    fn every_host_on_an_ingress_becomes_its_own_tile() {
        let apps = parse(
            r#"{"items":[{"metadata":{"name":"multi"},
                 "spec":{"rules":[{"host":"a.rkd.pw"},{"host":"b.rkd.pw"}]}}]}"#,
        );

        assert_eq!(apps.len(), 2);
        assert_eq!(apps[0].url, "http://a.rkd.pw");
        assert_eq!(apps[1].url, "http://b.rkd.pw");
    }

    #[test]
    fn rules_without_a_host_are_skipped() {
        let apps = parse(r#"{"items":[{"metadata":{"name":"x"},"spec":{"rules":[{"host":""}]}}]}"#);
        assert!(apps.is_empty());
    }

    #[test]
    fn the_first_ingress_to_claim_a_url_names_it() {
        let apps = parse(
            r#"{"items":[
                 {"metadata":{"name":"first"},"spec":{"rules":[{"host":"shared"}]}},
                 {"metadata":{"name":"second"},"spec":{"rules":[{"host":"shared"}]}}]}"#,
        );

        assert_eq!(apps.len(), 1);
        assert_eq!(apps[0].name, "first");
    }

    #[test]
    fn an_unnamed_ingress_falls_back_to_its_host() {
        let apps = parse(r#"{"items":[{"spec":{"rules":[{"host":"orphan.rkd.pw"}]}}]}"#);
        assert_eq!(apps[0].name, "orphan.rkd.pw");
    }

    #[test]
    fn tiles_come_back_ordered_by_url() {
        let apps = parse(
            r#"{"items":[
                 {"metadata":{"name":"z"},"spec":{"rules":[{"host":"z.rkd.pw"}]}},
                 {"metadata":{"name":"a"},"spec":{"rules":[{"host":"a.rkd.pw"}]}}]}"#,
        );

        assert_eq!(apps[0].url, "http://a.rkd.pw");
        assert_eq!(apps[1].url, "http://z.rkd.pw");
    }

    #[test]
    fn an_empty_list_yields_no_tiles() {
        assert!(parse(r#"{"items":[]}"#).is_empty());
        assert!(parse(r#"{}"#).is_empty());
    }
}
