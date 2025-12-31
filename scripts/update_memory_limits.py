#!/usr/bin/env python3
"""
Update memory limits in values.yaml based on actual usage from k3s.
Calculates 1.5x current usage and rounds up to reasonable values.
"""

import subprocess
import re
import yaml
from pathlib import Path
from typing import Dict, Tuple

# Mapping of container names to values.yaml keys
# Format: {container_name: (yaml_path, subkey)}
CONTAINER_MAPPINGS = {
    "portainer": ("portainer", "resources.limits.memory"),
    "jackett": ("jackett", "resources.limits.memory"),
    "radarr": ("radarr", "resources.limits.memory"),
    "jellyfin": ("jellyfin", "resources.limits.memory"),
    "deluge": ("deluge", "resources.limits.memory"),
    "homeassistant": ("homeassistant", "resources.limits.memory"),
    # frigate handled separately (has requests too)
    "nodered": ("nodered", "resources.limits.memory"),
    "hoarder-web": ("hoarder.web", "resources.limits.memory"),
    "hoarder-chrome": ("hoarder.chrome", "resources.limits.memory"),
    "hoarder-meilisearch": ("hoarder.meilisearch", "resources.limits.memory"),
    "paperless-webserver": ("paperless.webserver", "resources.limits.memory"),
    "nextcloud-app": ("nextcloud.app", "resources.limits.memory"),
    "nextcloud-db": ("nextcloud.db", "resources.limits.memory"),
    "kuma": ("kuma", "resources.limits.memory"),
    "immich-server": ("immich.server", "resources.limits.memory"),
    "immich-machine-learning": ("immich.machineLearning", "resources.limits.memory"),
    "immich-database": ("immich.database", "resources.limits.memory"),
    "immich-redis": ("immich.redis", "resources.limits.memory"),
    "bugsink": ("bugsink", "resources.limits.memory"),
    "it-tools": ("itTools", "resources.limits.memory"),
    "miniflux": ("miniflux", "resources.limits.memory"),
    "miniflux-db": ("minifluxDb", "resources.limits.memory"),
    "irish-schools": ("irishSchools", "resources.limits.memory"),
    "changes": ("changes", "resources.limits.memory"),
    "termix": ("termix", "resources.limits.memory"),
}


def parse_memory(memory_str: str) -> int:
    """Convert memory string (e.g., '338Mi', '1.5Gi') to bytes."""
    memory_str = memory_str.strip()
    match = re.match(r'^(\d+(?:\.\d+)?)\s*(Mi|Gi|Ki|MiB|GiB|KiB)$', memory_str, re.IGNORECASE)
    if not match:
        return 0
    
    value = float(match.group(1))
    unit = match.group(2).upper()
    
    if unit.startswith('KI'):
        return int(value * 1024)
    elif unit.startswith('MI'):
        return int(value * 1024 * 1024)
    elif unit.startswith('GI'):
        return int(value * 1024 * 1024 * 1024)
    return 0


def format_memory(bytes_val: int) -> str:
    """Convert bytes to Mi or Gi format, rounding appropriately."""
    if bytes_val >= 1024 * 1024 * 1024:  # >= 1Gi
        # Round to nearest 128Mi for Gi values
        gi = bytes_val / (1024 * 1024 * 1024)
        if gi < 1.5:
            return "1536Mi"  # 1.5Gi
        elif gi < 2:
            return "2Gi"
        elif gi < 3:
            return "3Gi"
        else:
            # Round to nearest Gi
            return f"{int(round(gi))}Gi"
    else:
        # Round to nearest power-of-2 or common value for Mi
        mi = bytes_val / (1024 * 1024)
        if mi < 16:
            return "16Mi"
        elif mi < 32:
            return "32Mi"
        elif mi < 64:
            return "64Mi"
        elif mi < 128:
            return "128Mi"
        elif mi < 256:
            return "256Mi"
        elif mi < 512:
            return "512Mi"
        elif mi < 768:
            return "768Mi"
        elif mi < 1024:
            return "1024Mi"
        else:
            # Round to nearest 128Mi
            return f"{int(round(mi / 128) * 128)}Mi"


def get_memory_usage(kubeconfig: str) -> Dict[str, int]:
    """Get memory usage from k3s using kubectl."""
    try:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "top", "pods", "--containers"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running kubectl: {e}")
        print(f"stderr: {e.stderr}")
        return {}
    
    usage = {}
    lines = result.stdout.strip().split('\n')
    
    # Skip header lines
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 4:
            container_name = parts[1]
            memory_str = parts[3]
            memory_bytes = parse_memory(memory_str)
            
            # Handle multiple instances of the same container (take max)
            if container_name in usage:
                usage[container_name] = max(usage[container_name], memory_bytes)
            else:
                usage[container_name] = memory_bytes
    
    return usage


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
        current = current[key]
    current[keys[-1]] = value


def update_values_yaml(values_path: Path, kubeconfig: str):
    """Update values.yaml with new memory limits based on usage."""
    # Get memory usage
    print("Fetching memory usage from k3s...")
    usage = get_memory_usage(kubeconfig)
    
    if not usage:
        print("No memory usage data found. Exiting.")
        return
    
    # Load values.yaml
    print(f"Loading {values_path}...")
    with open(values_path, 'r') as f:
        values = yaml.safe_load(f)
    
    if not values:
        print("Failed to load values.yaml")
        return
    
    updates = []
    
    # Calculate and update memory limits
    for container_name, (yaml_path, memory_path) in CONTAINER_MAPPINGS.items():
        if container_name not in usage:
            continue
        
        current_usage = usage[container_name]
        # Limits: 2x usage
        new_limit_bytes = int(current_usage * 2)
        new_limit_str = format_memory(new_limit_bytes)
        # Requests: 1x usage (rounded up)
        new_request_bytes = int(current_usage * 1)
        new_request_str = format_memory(new_request_bytes)
        
        # Get current limit and request
        full_path = f"{yaml_path}.{memory_path}"
        requests_path = full_path.replace(".limits.memory", ".requests.memory")
        current_limit = get_nested_value(values, full_path)
        current_request = get_nested_value(values, requests_path)
        
        limit_changed = current_limit != new_limit_str
        request_changed = current_request != new_request_str
        
        if limit_changed or request_changed:
            if limit_changed:
                set_nested_value(values, full_path, new_limit_str)
            if request_changed:
                set_nested_value(values, requests_path, new_request_str)
            updates.append((container_name, current_limit, new_limit_str, current_request, new_request_str, current_usage))
    
    if not updates:
        print("No memory limits need updating.")
        return
    
    # Print changes
    print("\nMemory updates (Limits: 2x usage, Requests: 1x usage):")
    print(f"{'Container':<30} {'Limit':<15} {'Request':<15} {'Usage':<15}")
    print(f"{'':<30} {'Old -> New':<15} {'Old -> New':<15} {'':<15}")
    print("-" * 75)
    for container, old_limit, new_limit, old_request, new_request, usage_bytes in updates:
        usage_str = format_memory(usage_bytes)
        limit_str = f"{str(old_limit):<6} -> {new_limit}"
        request_str = f"{str(old_request) if old_request else 'none':<6} -> {new_request}"
        print(f"{container:<30} {limit_str:<15} {request_str:<15} {usage_str:<15}")
    
    # Handle special case: frigate (already has requests, just update both)
    if "frigate" in usage:
        frigate_usage = usage["frigate"]
        frigate_limit_bytes = int(frigate_usage * 2)
        frigate_limit_str = format_memory(frigate_limit_bytes)
        frigate_request_bytes = int(frigate_usage * 1)
        frigate_request_str = format_memory(frigate_request_bytes)
        current_frigate_limit = get_nested_value(values, "frigate.resources.limits.memory")
        current_frigate_request = get_nested_value(values, "frigate.resources.requests.memory")
        limit_changed = current_frigate_limit != frigate_limit_str
        request_changed = current_frigate_request != frigate_request_str
        if limit_changed or request_changed:
            if limit_changed:
                set_nested_value(values, "frigate.resources.limits.memory", frigate_limit_str)
            if request_changed:
                set_nested_value(values, "frigate.resources.requests.memory", frigate_request_str)
            # Check if already in updates list
            already_updated = any(container == "frigate" for container, _, _, _, _, _ in updates)
            if not already_updated:
                updates.append(("frigate", current_frigate_limit, frigate_limit_str, current_frigate_request, frigate_request_str, frigate_usage))
    
    if not updates:
        print("No memory limits need updating.")
        return
    
    # Print changes
    print("\nMemory updates (Limits: 2x usage, Requests: 1x usage):")
    print(f"{'Container':<30} {'Limit':<15} {'Request':<15} {'Usage':<15}")
    print(f"{'':<30} {'Old -> New':<15} {'Old -> New':<15} {'':<15}")
    print("-" * 75)
    for container, old_limit, new_limit, old_request, new_request, usage_bytes in updates:
        usage_str = format_memory(usage_bytes)
        limit_str = f"{str(old_limit):<6} -> {new_limit}"
        request_str = f"{str(old_request) if old_request else 'none':<6} -> {new_request}"
        print(f"{container:<30} {limit_str:<15} {request_str:<15} {usage_str:<15}")
    
    # Write updated values.yaml
    print(f"\nWriting updated values to {values_path}...")
    with open(values_path, 'w') as f:
        yaml.dump(values, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=1000)
    
    print(f"Updated {len(updates)} memory limits.")


def main():
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    values_path = repo_root / "apps-chart" / "values.yaml"
    kubeconfig = repo_root / "local.yaml"
    
    if not values_path.exists():
        print(f"Error: {values_path} not found")
        return 1
    
    if not kubeconfig.exists():
        print(f"Error: {kubeconfig} not found")
        return 1
    
    update_values_yaml(values_path, str(kubeconfig))
    return 0


if __name__ == "__main__":
    exit(main())

