//! Entry point: read the configuration, find a cluster, start serving.

use compote3::config;
use compote3::github;
use compote3::k3s;
use compote3::server;
use compote3::server::Cluster;
use compote3::server::State;
use compote3::sys::capability;
use compote3::CliError;
use compote3::Invocation;
use compote3::DEFAULT_PORT;
use compote3::USAGE;
use compote3::WORKERS;
use std::path::Path;
use std::time::Duration;
use ureq::Agent;

/// Ceiling on any single outbound request, so a hung GitHub or API server
/// call cannot pin a worker thread indefinitely.
const OUTBOUND_TIMEOUT: Duration = Duration::from_secs(20);

fn main() -> Result<(), CliError> {
    let arguments: Vec<String> = capability::args().into_iter().skip(1).collect();
    let invocation = compote3::parse_arguments(&arguments)?;

    let config_path = match invocation {
        Invocation::Help => {
            println!("{USAGE}");
            return Ok(());
        }
        Invocation::Serve { config } => config,
    };

    // A missing or broken config file is not fatal: the dashboard still shows
    // whatever the cluster and GitHub can tell it.
    let config = match config::load(Path::new(&config_path)) {
        Ok(config) => config,
        Err(error) => {
            eprintln!("warning: {error}. Using defaults.");
            config::Config::default()
        }
    };

    let cluster = connect_cluster();
    let github = github::Client::new(outbound_agent(), capability::env_var("GITHUB_TOKEN"));

    let port = capability::env_var("PORT")
        .filter(|port| !port.is_empty())
        .unwrap_or_else(|| DEFAULT_PORT.to_owned());

    let state = State {
        config,
        github,
        cluster,
    };

    server::serve(state, &format!("0.0.0.0:{port}"), WORKERS)?;
    Ok(())
}

fn outbound_agent() -> Agent {
    Agent::config_builder()
        .timeout_global(Some(OUTBOUND_TIMEOUT))
        .build()
        .into()
}

/// Resolves cluster credentials once at startup. Failing to find any is a
/// supported configuration, not an error.
fn connect_cluster() -> Option<Cluster> {
    let (access, source) = k3s::discover_access();
    let access = access?;

    match k3s::agent_for(&access) {
        Ok(agent) => {
            eprintln!("Using Kubernetes API at {} ({source:?})", access.server);
            Some(Cluster {
                agent,
                access,
                source,
            })
        }
        Err(error) => {
            eprintln!("warning: cannot use cluster credentials: {error}");
            None
        }
    }
}
