# Compote3

A dashboard application that displays your k3s ingresses and GitHub trending repositories.

## Features

- **Applications**: Automatically discovers applications from k3s ingresses
- **Links**: Custom links and bookmarks
- **GitHub Trending**: Shows trending repositories for day and week
- **GitHub Watched**: Displays your watched repositories from config

## Configuration

Create a `config.yaml` file:

```yaml
# Additional links
links:
  - name: Example Link
    url: https://example.com

# GitHub watched repositories (uses starred repos)
github:
  watcher: your-username

# Application descriptions (optional)
descriptions:
  - name: appname
    description: "Description of the app"
```

## Environment Variables

- `PORT`: Server port (default: 9000)
- `GITHUB_TOKEN`: Optional GitHub token for API rate limit (recommended)
- `KUBECONFIG`: Path to kubeconfig file (optional, defaults to ~/.kube/config)

## Running

### Local Development

```bash
go mod download
go run .
```

### Docker

```bash
docker build -t compote3 .
docker run -p 9000:9000 \
  -v /path/to/config.yaml:/root/config.yaml \
  -v /path/to/.kube:/root/.kube \
  -e GITHUB_TOKEN=your_token \
  compote3
```

### Kubernetes

When running in Kubernetes, the application will automatically use in-cluster config to access the Kubernetes API.

## API

- `GET /` - Frontend dashboard
- `GET /api/data` - JSON API with all data

## Dependencies

- Kubernetes client-go for k3s ingress discovery
- GitHub API client for trending repositories
- Gin web framework for HTTP server

