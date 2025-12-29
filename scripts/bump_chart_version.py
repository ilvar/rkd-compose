#!/usr/bin/env python3
"""
Pre-commit hook to automatically bump Helm chart version
Bumps the patch version when any files in apps-chart/ are changed
"""

import re
import sys
from pathlib import Path

CHART_FILE = Path("apps-chart/Chart.yaml")


def get_current_version():
    """Extract current version from Chart.yaml"""
    if not CHART_FILE.exists():
        print(f"Warning: {CHART_FILE} not found")
        return None
    
    content = CHART_FILE.read_text()
    match = re.search(r'^version:\s*(.+)$', content, re.MULTILINE)
    if not match:
        print(f"Warning: Could not find version in {CHART_FILE}")
        return None
    
    version = match.group(1).strip().strip('"').strip("'")
    return version


def bump_version(version):
    """Bump patch version (e.g., 0.1.0 -> 0.1.1)"""
    parts = version.split('.')
    if len(parts) != 3:
        print(f"Warning: Invalid version format: {version}")
        return None
    
    try:
        major, minor, patch = map(int, parts)
        patch += 1
        return f"{major}.{minor}.{patch}"
    except ValueError:
        print(f"Warning: Invalid version format: {version}")
        return None


def update_chart_version(new_version):
    """Update version in Chart.yaml"""
    content = CHART_FILE.read_text()
    updated = re.sub(
        r'^version:\s*.+$',
        f'version: {new_version}',
        content,
        flags=re.MULTILINE
    )
    CHART_FILE.write_text(updated)


def main():
    """Main function"""
    # Check if any files in apps-chart are staged
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            capture_output=True,
            text=True,
            check=True
        )
        staged_files = [f for f in result.stdout.strip().split('\n') if f]
        
        # Check if any apps-chart files are staged (excluding Chart.yaml itself)
        chart_files_staged = any(
            f.startswith('apps-chart/') and not f.endswith('Chart.yaml')
            for f in staged_files
        )
        
        if not chart_files_staged:
            # No chart files changed (other than Chart.yaml), skip version bump
            return 0
    except subprocess.CalledProcessError:
        # If git command fails, continue anyway
        pass
    
    current_version = get_current_version()
    if not current_version:
        return 0
    
    new_version = bump_version(current_version)
    if not new_version:
        return 0
    
    update_chart_version(new_version)
    
    # Stage the updated Chart.yaml
    import subprocess
    try:
        subprocess.run(
            ['git', 'add', str(CHART_FILE)],
            check=True,
            capture_output=True
        )
        print(f"Bumped chart version from {current_version} to {new_version}")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not stage {CHART_FILE}: {e}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

