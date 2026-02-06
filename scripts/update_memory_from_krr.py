#!/usr/bin/env python3
"""
Update memory requests and limits in values.yaml based on KRR (Kubernetes Resource Recommender) CSV output.
"""

import csv
import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple

# Mapping of CSV app names to values.yaml paths
# Format: {csv_app_name: yaml_path}
APP_MAPPINGS = {
    "blog": "blog",
    "bugsink": "bugsink",
    "changes": "changes",
    "compote3": "compote3",
    "deluge": "deluge",
    "frigate": "frigate",
    "hoarder-chrome": "hoarder.chrome",
    "hoarder-meilisearch": "hoarder.meilisearch",
    "hoarder-web": "hoarder.web",
    "homeassistant": "homeassistant",
    "immich-machine-learning": "immich.machineLearning",
    "immich-redis": "immich.redis",
    "immich-server": "immich.server",
    "immich-database": "immich.database",
    "irish-schools": "irishSchools",
    "it-tools": "itTools",
    "jackett": "jackett",
    "jellyfin": "jellyfin",
    "kosmos-backend": "kosmos.backend",
    "kosmos-frontend": "kosmos.frontend",
    "kosmos-db": "kosmos.db",
    "kuma": "kuma",
    "miniflux": "miniflux",
    "miniflux-db": "minifluxDb",
    "nextcloud-app": "nextcloud.app",
    "nextcloud-db": "nextcloud.db",
    "nodered": "nodered",
    "paperless-webserver": "paperless.webserver",
    "paperless-redis": "paperless.redis",
    "pinchflat": "pinchflat",
    "radarr": "radarr",
    "rkd-pw": "rkdPw",
    "termix": "termix",
    "blocky": "blocky",
}


def get_nested_value(data: dict, path: str):
    """Get value from nested dict using dot notation."""
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value


def set_nested_value(data: dict, path: str, value):
    """Set value in nested dict using dot notation."""
    keys = path.split('.')
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        if not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def parse_csv(csv_path: Path) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """
    Parse KRR CSV file and return dict mapping app names to (mem_req_recommended, mem_lim_recommended).
    Returns: {app_name: (mem_req, mem_lim)}
    """
    recommendations = {}
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only process default namespace deployments/statefulsets
            if row.get('namespace') != 'default':
                continue
            
            app_name = row.get('app', '').strip()
            if not app_name:
                continue
            
            mem_req_rec = row.get('mem_req_recommended', '').strip()
            mem_lim_rec = row.get('mem_lim_recommended', '').strip()
            
            # Skip if both are empty or 'none'
            if (not mem_req_rec or mem_req_rec.lower() == 'none') and \
               (not mem_lim_rec or mem_lim_rec.lower() == 'none'):
                continue
            
            # Convert 'none' to None
            mem_req_rec = None if (not mem_req_rec or mem_req_rec.lower() == 'none') else mem_req_rec
            mem_lim_rec = None if (not mem_lim_rec or mem_lim_rec.lower() == 'none') else mem_lim_rec
            
            recommendations[app_name] = (mem_req_rec, mem_lim_rec)
    
    return recommendations


def update_values_yaml(values_path: Path, csv_path: Path):
    """Update values.yaml with memory recommendations from KRR CSV."""
    # Parse CSV
    print(f"Parsing CSV file: {csv_path}")
    recommendations = parse_csv(csv_path)
    
    if not recommendations:
        print("No recommendations found in CSV file.")
        return
    
    print(f"Found {len(recommendations)} app recommendations")
    
    # Load values.yaml
    print(f"Loading {values_path}...")
    with open(values_path, 'r') as f:
        values = yaml.safe_load(f)
    
    if not values:
        print("Failed to load values.yaml")
        return
    
    updates = []
    
    # Update memory settings
    for csv_app_name, (mem_req_rec, mem_lim_rec) in recommendations.items():
        if csv_app_name not in APP_MAPPINGS:
            continue
        
        yaml_path = APP_MAPPINGS[csv_app_name]
        
        # Build paths
        limits_path = f"{yaml_path}.resources.limits.memory"
        requests_path = f"{yaml_path}.resources.requests.memory"
        
        # Get current values
        current_limit = get_nested_value(values, limits_path)
        current_request = get_nested_value(values, requests_path)
        
        # Check if requests are supported (either already exist or template supports them)
        # Templates that explicitly support requests: frigate, pinchflat, immich*, kosmos* (use toYaml)
        supports_requests = (
            current_request is not None or  # Already has requests
            csv_app_name in ('frigate', 'pinchflat') or  # Explicitly supports requests
            csv_app_name.startswith('immich-') or  # Uses toYaml
            csv_app_name.startswith('kosmos-')  # Uses toYaml
        )
        
        # Update limit if recommended
        if mem_lim_rec and mem_lim_rec.lower() != 'none':
            if current_limit != mem_lim_rec:
                set_nested_value(values, limits_path, mem_lim_rec)
                updates.append({
                    'app': csv_app_name,
                    'type': 'limit',
                    'old': current_limit,
                    'new': mem_lim_rec,
                    'path': limits_path
                })
        
        # Update request if recommended and supported
        if supports_requests and mem_req_rec and mem_req_rec.lower() != 'none':
            if current_request != mem_req_rec:
                # Ensure resources.requests exists
                resources_path_parts = requests_path.split('.')
                resources_path = '.'.join(resources_path_parts[:-2])  # path to resources
                resources_dict = get_nested_value(values, resources_path)
                if not resources_dict:
                    # Create resources dict if it doesn't exist
                    set_nested_value(values, resources_path, {})
                
                set_nested_value(values, requests_path, mem_req_rec)
                updates.append({
                    'app': csv_app_name,
                    'type': 'request',
                    'old': current_request,
                    'new': mem_req_rec,
                    'path': requests_path
                })
    
    if not updates:
        print("No memory settings need updating.")
        return
    
    # Print changes
    print(f"\nMemory updates ({len(updates)} changes):")
    print(f"{'App':<30} {'Type':<10} {'Old':<15} {'New':<15}")
    print("-" * 70)
    for update in updates:
        old_val = str(update['old']) if update['old'] else 'none'
        print(f"{update['app']:<30} {update['type']:<10} {old_val:<15} {update['new']:<15}")
    
    # Write updated values.yaml
    print(f"\nWriting updated values to {values_path}...")
    with open(values_path, 'w') as f:
        yaml.dump(values, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=1000)
    
    print(f"Updated {len(updates)} memory settings.")


def main():
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    values_path = repo_root / "apps-chart" / "values.yaml"
    csv_path = repo_root / "tmp" / "krr_rkd_ea38f4d4-d4e8-4769-a8ca-ecb926678161_2026-01-03T23_32_42.772Z.csv"
    
    if not values_path.exists():
        print(f"Error: {values_path} not found")
        return 1
    
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        return 1
    
    update_values_yaml(values_path, csv_path)
    return 0


if __name__ == "__main__":
    exit(main())
