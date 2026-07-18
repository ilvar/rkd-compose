#!/usr/bin/env python3
"""
Add CPU requests to values.yaml based on best practices.
Only adds CPU requests, not limits.
"""

import yaml
from pathlib import Path
from typing import Dict, Optional

# CPU request recommendations based on service type and workload
# Values in millicores (m)
CPU_REQUESTS = {
    # Very light services (50-100m)
    "blog": "100m",
    "compote3": "50m",
    "itTools": "100m",
    "miniflux": "100m",
    "portainer": "100m",
    "kuma": "100m",
    "irishSchools": "50m",
    "rkdPw": "100m",
    "blocky": "100m",
    
    # Light web services (100-200m)
    "changes": "150m",
    "nodered": "150m",
    "hoarder.web": "200m",
    "hoarder.chrome": "150m",
    "hoarder.meilisearch": "100m",
    "termix": "100m",
    
    # Medium services (200-500m)
    "jackett": "250m",
    "radarr": "300m",
    "nextcloud.app": "300m",
    "paperless.webserver": "400m",
    "bugsink": "300m",
    
    # Database services (200-500m)
    "nextcloud.db": "300m",
    "minifluxDb": "200m",
    "paperless.redis": "100m",
    "immich.database": "300m",
    "immich.redis": "100m",
    
    # CPU-intensive services (500-1000m)
    "jellyfin": "500m",
    "frigate": "800m",  # Video processing
    "pinchflat": "500m",  # Video processing
    "homeassistant": "300m",
    "deluge": "200m",
    "immich.server": "400m",
    "immich.machineLearning": "500m",  # ML processing
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


def add_cpu_requests(values_path: Path):
    """Add CPU requests to values.yaml."""
    print(f"Loading {values_path}...")
    with open(values_path, 'r') as f:
        values = yaml.safe_load(f)
    
    if not values:
        print("Failed to load values.yaml")
        return
    
    updates = []
    
    # Add CPU requests
    for service_path, cpu_request in CPU_REQUESTS.items():
        requests_path = f"{service_path}.resources.requests.cpu"
        
        # Check if requests section exists
        resources_path_parts = requests_path.split('.')
        resources_path = '.'.join(resources_path_parts[:-2])  # path to resources
        requests_section_path = '.'.join(resources_path_parts[:-1])  # path to requests
        
        # Get current CPU request
        current_cpu = get_nested_value(values, requests_path)
        
        # Only add if not already set
        if current_cpu is None:
            # Ensure resources.requests exists
            resources_dict = get_nested_value(values, resources_path)
            if resources_dict is None:
                # Create resources dict if it doesn't exist
                set_nested_value(values, resources_path, {})
            
            requests_dict = get_nested_value(values, requests_section_path)
            if requests_dict is None:
                # Create requests dict if it doesn't exist
                set_nested_value(values, requests_section_path, {})
            
            set_nested_value(values, requests_path, cpu_request)
            updates.append({
                'service': service_path,
                'cpu_request': cpu_request,
                'path': requests_path
            })
        else:
            print(f"Skipping {service_path} - CPU request already set to {current_cpu}")
    
    if not updates:
        print("No CPU requests to add.")
        return
    
    # Print changes
    print(f"\nAdding CPU requests ({len(updates)} services):")
    print(f"{'Service':<40} {'CPU Request':<15}")
    print("-" * 55)
    for update in updates:
        print(f"{update['service']:<40} {update['cpu_request']:<15}")
    
    # Write updated values.yaml
    print(f"\nWriting updated values to {values_path}...")
    with open(values_path, 'w') as f:
        yaml.dump(values, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=1000)
    
    print(f"Added {len(updates)} CPU requests.")


def main():
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    values_path = repo_root / "apps-chart" / "values.yaml"
    
    if not values_path.exists():
        print(f"Error: {values_path} not found")
        return 1
    
    add_cpu_requests(values_path)
    return 0


if __name__ == "__main__":
    exit(main())
