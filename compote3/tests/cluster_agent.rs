//! The cluster HTTP agent is assembled from PEM material that only ever comes
//! from a kubeconfig or a mounted service account, so its construction is
//! checked here against real certificates rather than at first request in
//! production.
//!
//! The key pair is generated per run rather than committed: no private key
//! belongs in a repository, however inert.

use compote3::k3s::agent_for;
use compote3::kubeconfig::ClusterAccess;
use std::sync::OnceLock;

/// A throwaway self-signed pair, generated once per test binary.
fn material() -> &'static (Vec<u8>, Vec<u8>) {
    static MATERIAL: OnceLock<(Vec<u8>, Vec<u8>)> = OnceLock::new();
    MATERIAL.get_or_init(|| {
        let issued = rcgen::generate_simple_self_signed(vec!["compote3-test".to_owned()])
            .expect("a self-signed pair is generated");
        (
            issued.cert.pem().into_bytes(),
            issued.signing_key.serialize_pem().into_bytes(),
        )
    })
}

fn cert_pem() -> Vec<u8> {
    material().0.clone()
}

fn key_pem() -> Vec<u8> {
    material().1.clone()
}

fn access() -> ClusterAccess {
    ClusterAccess {
        server: "https://127.0.0.1:6443".to_owned(),
        ..ClusterAccess::default()
    }
}

#[test]
fn a_bearer_token_cluster_needs_no_tls_material() {
    let access = ClusterAccess {
        token: Some("service-account-token".to_owned()),
        ..access()
    };

    assert!(agent_for(&access).is_ok());
}

#[test]
fn a_custom_certificate_authority_is_accepted() {
    let access = ClusterAccess {
        certificate_authority: Some(cert_pem()),
        token: Some("token".to_owned()),
        ..access()
    };

    assert!(agent_for(&access).is_ok());
}

#[test]
fn a_client_certificate_and_key_are_accepted() {
    let access = ClusterAccess {
        certificate_authority: Some(cert_pem()),
        client_certificate: Some(cert_pem()),
        client_key: Some(key_pem()),
        ..access()
    };

    assert!(agent_for(&access).is_ok());
}

#[test]
fn a_client_certificate_without_its_key_is_ignored_rather_than_half_applied() {
    let access = ClusterAccess {
        client_certificate: Some(cert_pem()),
        client_key: None,
        ..access()
    };

    assert!(agent_for(&access).is_ok());
}

#[test]
fn unusable_pem_is_reported_at_startup_and_names_what_is_wrong() {
    let bad_ca = ClusterAccess {
        certificate_authority: Some(b"not a certificate".to_vec()),
        ..access()
    };
    let error = agent_for(&bad_ca).expect_err("a broken CA is rejected");
    assert!(
        error.contains("certificate authority"),
        "unexpected error: {error}"
    );

    let bad_key = ClusterAccess {
        client_certificate: Some(cert_pem()),
        client_key: Some(b"not a key".to_vec()),
        ..access()
    };
    let error = agent_for(&bad_key).expect_err("a broken key is rejected");
    assert!(error.contains("client key"), "unexpected error: {error}");
}

#[test]
fn skipping_verification_is_carried_into_the_agent() {
    let access = ClusterAccess {
        insecure_skip_tls_verify: true,
        ..access()
    };

    assert!(agent_for(&access).is_ok());
}
