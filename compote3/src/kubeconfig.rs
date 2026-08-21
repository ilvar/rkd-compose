//! Enough of the kubeconfig format to reach an API server for local
//! development. In the cluster, compote3 uses its service account instead.

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use serde::Deserialize;
use std::path::Path;
use std::path::PathBuf;

use crate::sys::capability;

/// Everything needed to make an authenticated request to an API server.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct ClusterAccess {
    pub server: String,
    /// PEM-encoded certificate authority, when the cluster is not signed by a
    /// publicly trusted root — which is the normal case for k3s.
    pub certificate_authority: Option<Vec<u8>>,
    pub insecure_skip_tls_verify: bool,
    pub token: Option<String>,
    /// PEM-encoded client certificate chain and key, the default k3s
    /// credential.
    pub client_certificate: Option<Vec<u8>>,
    pub client_key: Option<Vec<u8>>,
}

#[derive(Debug, Deserialize)]
struct KubeConfig {
    #[serde(rename = "current-context", default)]
    current_context: String,
    #[serde(default)]
    contexts: Vec<NamedContext>,
    #[serde(default)]
    clusters: Vec<NamedCluster>,
    #[serde(default)]
    users: Vec<NamedUser>,
}

#[derive(Debug, Deserialize)]
struct NamedContext {
    name: String,
    context: ContextRef,
}

#[derive(Debug, Deserialize)]
struct ContextRef {
    #[serde(default)]
    cluster: String,
    #[serde(default)]
    user: String,
}

#[derive(Debug, Deserialize)]
struct NamedCluster {
    name: String,
    cluster: ClusterSpec,
}

#[derive(Debug, Default, Deserialize)]
struct ClusterSpec {
    #[serde(default)]
    server: String,
    #[serde(rename = "certificate-authority", default)]
    certificate_authority: Option<String>,
    #[serde(rename = "certificate-authority-data", default)]
    certificate_authority_data: Option<String>,
    #[serde(rename = "insecure-skip-tls-verify", default)]
    insecure_skip_tls_verify: bool,
}

#[derive(Debug, Deserialize)]
struct NamedUser {
    name: String,
    user: UserSpec,
}

#[derive(Debug, Default, Deserialize)]
struct UserSpec {
    #[serde(default)]
    token: Option<String>,
    #[serde(rename = "client-certificate", default)]
    client_certificate: Option<String>,
    #[serde(rename = "client-certificate-data", default)]
    client_certificate_data: Option<String>,
    #[serde(rename = "client-key", default)]
    client_key: Option<String>,
    #[serde(rename = "client-key-data", default)]
    client_key_data: Option<String>,
}

/// Resolves a `*-data` (base64) field, else a `*` path field read relative to
/// the kubeconfig's own directory, the way `kubectl` does.
fn resolve_pem(
    inline: Option<&String>,
    path: Option<&String>,
    base: &Path,
) -> Result<Option<Vec<u8>>, String> {
    if let Some(encoded) = inline.filter(|value| !value.is_empty()) {
        let decoded = STANDARD
            .decode(encoded.trim())
            .map_err(|error| format!("kubeconfig contains invalid base64 data: {error}"))?;
        return Ok(Some(decoded));
    }

    if let Some(relative) = path.filter(|value| !value.is_empty()) {
        let resolved = base.join(relative);
        return capability::read_bytes(&resolved).map(Some);
    }

    Ok(None)
}

/// Parses a kubeconfig document and resolves its current context.
///
/// `base` is the directory the kubeconfig lives in, used to resolve the
/// relative file paths kubeconfigs are allowed to contain.
pub fn parse(text: &str, base: &Path) -> Result<ClusterAccess, String> {
    let config: KubeConfig = serde_yaml_ng::from_str(text)
        .map_err(|error| format!("failed to parse kubeconfig: {error}"))?;

    let context = config
        .contexts
        .iter()
        .find(|entry| entry.name == config.current_context)
        .map(|entry| &entry.context)
        .ok_or_else(|| {
            format!(
                "kubeconfig has no context named {:?}",
                config.current_context
            )
        })?;

    let cluster = config
        .clusters
        .iter()
        .find(|entry| entry.name == context.cluster)
        .map(|entry| &entry.cluster)
        .ok_or_else(|| format!("kubeconfig has no cluster named {:?}", context.cluster))?;

    if cluster.server.is_empty() {
        return Err(format!(
            "kubeconfig cluster {:?} has no server URL",
            context.cluster
        ));
    }

    let empty = UserSpec::default();
    let user = config
        .users
        .iter()
        .find(|entry| entry.name == context.user)
        .map(|entry| &entry.user)
        .unwrap_or(&empty);

    Ok(ClusterAccess {
        server: cluster.server.trim_end_matches('/').to_owned(),
        certificate_authority: resolve_pem(
            cluster.certificate_authority_data.as_ref(),
            cluster.certificate_authority.as_ref(),
            base,
        )?,
        insecure_skip_tls_verify: cluster.insecure_skip_tls_verify,
        token: user.token.clone().filter(|token| !token.is_empty()),
        client_certificate: resolve_pem(
            user.client_certificate_data.as_ref(),
            user.client_certificate.as_ref(),
            base,
        )?,
        client_key: resolve_pem(
            user.client_key_data.as_ref(),
            user.client_key.as_ref(),
            base,
        )?,
    })
}

/// Reads the kubeconfig at `path`.
pub fn load(path: &Path) -> Result<ClusterAccess, String> {
    let text = capability::read_to_string(path)?;
    let base = path.parent().unwrap_or(Path::new(".")).to_owned();
    parse(&text, &base)
}

/// The kubeconfig `kubectl` would use: `$KUBECONFIG`, else `~/.kube/config`.
pub fn default_path() -> Option<PathBuf> {
    if let Some(configured) = capability::env_var("KUBECONFIG") {
        if !configured.is_empty() {
            // A `:`-separated list is legal; the first entry is the one that
            // wins for the fields compote3 reads.
            let first = configured.split(':').next().unwrap_or(&configured);
            return Some(PathBuf::from(first));
        }
    }

    capability::home_dir().map(|home| home.join(".kube").join("config"))
}

#[cfg(test)]
mod tests {
    use super::parse;
    use base64::engine::general_purpose::STANDARD;
    use base64::Engine;
    use std::path::Path;

    fn document(extra_user: &str) -> String {
        let ca = STANDARD.encode("-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----\n");
        let mut text = String::from("apiVersion: v1\nkind: Config\ncurrent-context: default\n");
        text.push_str("clusters:\n- name: local\n  cluster:\n");
        text.push_str("    server: https://127.0.0.1:6443/\n");
        text.push_str(&format!("    certificate-authority-data: {ca}\n"));
        text.push_str("contexts:\n- name: default\n  context:\n");
        text.push_str("    cluster: local\n    user: admin\n");
        text.push_str("users:\n- name: admin\n  user:\n");
        text.push_str(extra_user);
        text.push('\n');
        text
    }

    #[test]
    fn a_token_kubeconfig_resolves_its_current_context() {
        let access = parse(&document("    token: secret"), Path::new("/tmp")).expect("parses");

        assert_eq!(access.server, "https://127.0.0.1:6443");
        assert_eq!(access.token.as_deref(), Some("secret"));
        assert!(access.client_certificate.is_none());
        assert!(access
            .certificate_authority
            .expect("ca present")
            .starts_with(b"-----BEGIN CERTIFICATE-----"));
    }

    #[test]
    fn client_certificate_data_is_base64_decoded() {
        let cert = STANDARD.encode("cert-pem");
        let key = STANDARD.encode("key-pem");
        let user = format!("    client-certificate-data: {cert}\n    client-key-data: {key}");

        let access = parse(&document(&user), Path::new("/tmp")).expect("parses");

        assert_eq!(access.client_certificate.as_deref(), Some(&b"cert-pem"[..]));
        assert_eq!(access.client_key.as_deref(), Some(&b"key-pem"[..]));
    }

    #[test]
    fn a_missing_current_context_is_an_error_not_a_silent_default() {
        let text = "current-context: nope\nclusters: []\ncontexts: []\nusers: []\n";
        let error = parse(text, Path::new("/tmp")).expect_err("reported");

        assert!(error.contains("nope"), "unexpected error: {error}");
    }

    #[test]
    fn a_context_pointing_at_an_unknown_cluster_is_an_error() {
        let text = "current-context: default\n\
                    contexts:\n- name: default\n  context:\n    cluster: ghost\n    user: admin\n\
                    clusters: []\nusers: []\n";
        let error = parse(text, Path::new("/tmp")).expect_err("reported");

        assert!(error.contains("ghost"), "unexpected error: {error}");
    }

    #[test]
    fn insecure_skip_tls_verify_is_carried_through() {
        let text = "current-context: default\n\
                    contexts:\n- name: default\n  context:\n    cluster: local\n    user: admin\n\
                    clusters:\n- name: local\n  cluster:\n    server: https://h:6443\n    insecure-skip-tls-verify: true\n\
                    users: []\n";
        let access = parse(text, Path::new("/tmp")).expect("parses");

        assert!(access.insecure_skip_tls_verify);
        assert!(access.token.is_none());
    }
}
