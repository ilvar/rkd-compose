For prod debugging:
- Use `kubectl` with `KUBECONFIG=local.yaml` in this repo.
- Add `--insecure-skip-tls-verify` for cluster access.

Architecture:
- Fleet deploys the Helm chart at `apps-chart` using `fleet.yaml` and `apps-chart/values.yaml`.
- Workloads are defined in `apps-chart/templates` (apps, backups, notifications).
- Cluster nodes are mixed architecture (amd64 + arm64); ensure images are multi-arch.

Setup:
- Primary values file is `apps-chart/values.yaml`.
- Update chart or values in repo, then Fleet reconciles to the cluster.
- For manual checks: use `kubectl` and read Helm release secrets in `default` if needed.
