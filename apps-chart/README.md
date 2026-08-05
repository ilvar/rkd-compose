# Applications Helm Chart

This Helm chart is configured for deployment using Fleet CD, allowing GitOps-based deployment and management.

## Included Applications

This chart includes the following applications, organized by category:

### DNS & Networking
- **Blocky** - DNS server with ad-blocking capabilities

### Management & Monitoring
- **Portainer** - Container management UI
- **Kuma (Uptime Kuma)** - Uptime monitoring dashboard
- **Changes** - Website change detection and monitoring

### Media & Entertainment
- **Jellyfin** - Media server for streaming movies, TV shows, and music
- **Jackett** - Torrent indexer
- **FlareSolverr** - Proxy service for solving Cloudflare and anti-bot challenges
- **Radarr** - Movie collection manager
- **Deluge** - BitTorrent client
- **Immich** - Self-hosted photo and video backup solution

### Productivity & Collaboration
- **Nextcloud** - File sharing and collaboration platform (includes MariaDB database)
- **Paperless** - Document management system (includes Redis)
- **Hoarder** - Web scraping and automation tool (includes Chrome and Meilisearch)
- **Miniflux** - RSS feed reader (includes PostgreSQL database)
- **Archive** - Archive application

### Home Automation
- **Home Assistant** - Home automation platform

### Security
- **Vaultwarden** - Lightweight Bitwarden-compatible password manager

### Development & Tools
- **Bugsink** - Bug tracking and issue management
- **IT-Tools** - Collection of useful IT tools

### Web Applications
- **RKD.PW** - Main website (rkd.pw, www.rkd.pw)
- **Blog** - Blog application
- **Irish Schools** - Irish Schools application

## Chart Structure

```
apps-chart/
├── Chart.yaml          # Chart metadata
├── values.yaml         # Default configuration values
├── app-readme.md       # Documentation
├── README.md           # This file
├── templates/          # Kubernetes manifests
└── config/             # Configuration files
    └── blocky.yaml
```

## Chart Files

### app-readme.md
Documentation for the chart. Provides:
- Overview of all applications
- Prerequisites
- Installation instructions
- Configuration guidance

### Chart.yaml
Contains chart metadata including version, description, and maintainer information.

## Deploying with Fleet CD

This chart is configured for Fleet CD deployment using the `fleet.yaml` file at the repository root.

1. **Push chart to Git repository:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-git-repo-url>
   git push -u origin main
   ```

2. **Configure Fleet in Rancher:**
   - Navigate to **☰ > Cluster Management > Fleet**
   - Create a new GitRepo resource pointing to your repository
   - Fleet will automatically detect and deploy the chart using `fleet.yaml`

3. **Customize deployment:**
   - Edit `fleet.yaml` to add targetCustomizations for different clusters/environments
   - Override values per target using the `helm.values` section in targetCustomizations

## Customization

### Modifying Default Values

Edit `values.yaml` to change default configurations. Values can be overridden using Fleet CD's targetCustomizations or by modifying the values files referenced in `fleet.yaml`.

### Adding Applications

1. Add application configuration to `values.yaml`
2. Create deployment/service/ingress templates
3. Update `app-readme.md` with application details
4. Update this README.md to include the new application in the list above

## Testing

Before deploying, test the chart locally:

```bash
# Validate chart
helm lint apps-chart

# Dry run
helm install test-apps apps-chart --dry-run --debug

# Test template rendering
helm template test-apps apps-chart
```

## Troubleshooting

### Chart not appearing in Fleet
- Verify Git repository is properly configured in Fleet
- Check Chart.yaml has correct metadata
- Ensure fleet.yaml is present at repository root

### Installation fails
- Check cluster resources
- Verify ingress controller is installed
- Review pod logs: `kubectl logs -l app=<app-name>`

## Versioning

When updating the chart:
1. Update `version` in Chart.yaml
2. Update `appVersion` if needed
3. Tag Git repository with version
4. Update chart repository index

## Support

For issues:
1. Check application logs
2. Review Fleet/GitRepo logs
3. Verify cluster resources
4. Check ingress controller status
