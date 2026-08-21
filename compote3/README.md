# Compote3

A dashboard that shows your k3s ingresses, your bookmarks, and what GitHub has
been up to. Written in Rust; the whole runtime image is one static binary.

## Features

- **Applications** — discovered automatically from Kubernetes ingresses
- **Links** — bookmarks from `config.yaml`
- **GitHub trending** — popular repositories pushed to in the last day and week
- **GitHub watched** — the repositories a configured user has starred

Every section degrades independently: an unreachable cluster or a GitHub rate
limit empties that section and leaves the rest of the dashboard intact.

## Configuration

```yaml
# Bookmarks, shown in their own section
links:
  - name: Example Link
    url: https://example.com

# The user whose starred repositories fill the "watched" section
github:
  watcher: your-username

# Application names to hide (case-insensitive)
exclusions:
  - compote3

# Rename an application, or point it somewhere other than its ingress host
overrides:
  - name: rkd-compose-grafana
    new_name: grafana
    url: https://grafana.example.com/d/main

# Descriptions, matched against an application or link name
# (case-insensitive)
descriptions:
  - name: appname
    description: "Description of the app"
```

Unknown keys are rejected rather than ignored, so a typo fails loudly at
startup instead of quietly dropping a section. The configuration that actually
runs in the cluster lives in `apps-chart/values.yaml` under `compote3.config`,
and a test in this crate parses it.

## Environment

| Variable       | Meaning                                                   |
| -------------- | --------------------------------------------------------- |
| `PORT`         | Listen port (default `9000`)                               |
| `GITHUB_TOKEN` | GitHub token; strongly recommended for API rate limits     |
| `KUBECONFIG`   | Kubeconfig path used outside a cluster (`~/.kube/config`)  |

Inside a cluster the pod's service account is used instead, and its projected
token is re-read on each request so rotation does not break the dashboard.

## Running

### Local

```bash
cargo run -- --config config.yaml
```

### Docker

```bash
docker build -t compote3 .
docker run -p 9000:9000 \
  -v "$PWD/config.yaml:/root/config.yaml" \
  -e GITHUB_TOKEN="$GITHUB_TOKEN" \
  -e KUBECONFIG=/root/.kube/config \
  -v "$HOME/.kube:/root/.kube" \
  compote3
```

### Kubernetes

Deployed by the `apps-chart` Helm chart in this repository. The ClusterRole it
binds grants `list` and `get` on `networking.k8s.io/ingresses` and nothing else.

## API

- `GET /` — the dashboard
- `GET /api/data` — every section as JSON

## Development

```bash
cargo fmt --check
cargo clippy --all-targets --all-features --locked -- -D warnings
cargo test --all-targets --all-features --locked
```

The crate is also checked against the [strictrs](https://github.com/ilvar/strictrs)
subset, which is why filesystem and process access is confined to
`src/sys.rs`, there are no `as` casts, and nothing outside `#[cfg(test)]` calls
`unwrap` or `expect`:

```bash
strictrs check .
```

## Layout

| Path                | Responsibility                                        |
| ------------------- | ----------------------------------------------------- |
| `src/sys.rs`        | every filesystem, environment and process effect       |
| `src/config.rs`     | `config.yaml`                                          |
| `src/kubeconfig.rs` | kubeconfig parsing, for running outside a cluster      |
| `src/k3s.rs`        | ingress discovery                                      |
| `src/github.rs`     | trending and starred repositories                      |
| `src/clock.rs`      | the calendar arithmetic GitHub's date filters need     |
| `src/data.rs`       | assembling the payload — pure, and the most tested     |
| `src/server.rs`     | routing and concurrent fetching                        |

`templates/index.html` is compiled into the binary, so the runtime image is
`FROM scratch` with nothing but the executable and a default config.
