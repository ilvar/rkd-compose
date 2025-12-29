# Applications Helm Chart

A comprehensive Helm chart for deploying multiple self-hosted applications on Kubernetes.

## Overview

This chart deploys a collection of popular self-hosted applications including media servers, productivity tools, development utilities, and monitoring solutions.

## Applications Included

### DNS & Networking
- **Blocky** - DNS server with ad-blocking capabilities

### Management
- **Portainer** - Container management UI
- **Compote** - Docker management dashboard

### Media
- **Jellyfin** - Media server for streaming movies, TV shows, and music
- **Jackett** - Torrent indexer
- **Radarr** - Movie collection manager
- **Deluge** - BitTorrent client
- **Immich** - Self-hosted photo and video backup solution

### Productivity
- **Hoarder** - Web scraping and automation tool
- **Paperless** - Document management system
- **Nextcloud** - File sharing and collaboration platform

### Home Automation
- **Home Assistant** - Home automation platform

### Monitoring
- **Uptime Kuma** - Uptime monitoring dashboard

### Development
- **Bugsink** - Bug tracking and issue management
- **IT-Tools** - Collection of useful IT tools

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- Ingress Controller (NGINX, Traefik, etc.)
- Persistent Volume provisioner
- Sufficient cluster resources

## Installation

### Via Rancher

1. Add this chart repository to Rancher
2. Navigate to **Apps > Charts**
3. Find "Applications Chart" and click **Install**
4. Configure applications using the provided form
5. Review and deploy

### Via Helm CLI

```bash
helm install my-apps ./apps-chart
```

## Configuration

Each application can be enabled or disabled individually. Key configuration options include:

- **Ingress Hosts**: Configure subdomains for each application
- **Resource Limits**: Adjust memory limits per application
- **Storage**: Persistent volumes are automatically created
- **Environment Variables**: Configure application-specific settings

## Storage

All applications use PersistentVolumeClaims for data persistence. Storage sizes are configured per application and can be adjusted in `values.yaml`.

## Ingress

All applications are configured with Ingress resources. Ensure you have an Ingress Controller installed and DNS records pointing to your cluster.

## Security Notes

- **Nextcloud**: Set a strong admin password during installation
- **Bugsink**: Generate a secure secret key (at least 50 characters)
- **Paperless**: Configure a secure secret key
- Review and update default credentials before production use

## Resource Requirements

Minimum recommended cluster resources:
- **CPU**: 8+ cores
- **Memory**: 32GB+ RAM
- **Storage**: 500GB+ for persistent volumes

## Support

For issues and questions, please refer to the individual application documentation:
- Each application maintains its own documentation
- Check application logs: `kubectl logs -l app=<app-name>`
- Check pod status: `kubectl get pods`

## License

This chart packages various open-source applications. Each application maintains its own license.

