# Helm Validation

This project includes automated Helm chart validation through pre-commit hooks and CI/CD.

## Local Setup (Pre-commit)

To automatically validate the Helm chart before each commit:

```bash
# Install pre-commit framework
pip install pre-commit

# Install the git hooks
pre-commit install

# (Optional) Run on all files to check
pre-commit run --all-files
```

Now every commit will:
- Run `helm lint apps-chart/ --strict`
- Fail the commit if validation fails
- Only run if `apps-chart/` files changed

## Manual Testing

To validate the Helm chart manually:

```bash
# Lint the chart
helm lint apps-chart/ --strict

# Template rendering (dry-run)
helm template homelab apps-chart/ --values apps-chart/values.yaml

# Validate YAML syntax
python3 -c "
import yaml
with open('apps-chart/values.yaml', 'r') as f:
    yaml.safe_load(f)
    print('✅ YAML is valid')
"
```

## CI/CD

The `.github/workflows/helm-lint.yml` automatically:
- Runs on push/PR to `main` when `apps-chart/` changes
- Validates Helm chart syntax
- Validates `values.yaml` YAML syntax
- Fails the CI if validation fails

## Common Issues

**"helm: command not found"** - Install Helm
```bash
# macOS
brew install helm

# Linux
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

**YAML errors in values.yaml** - Check indentation and structure:
- Use 2 spaces (not tabs)
- Ensure proper nesting
- Watch for trailing spaces
