#!/usr/bin/env python3
"""
Pre-commit hook to automatically bump Compote version
Bumps the patch version when any files in compote3/ are changed
"""

import re
import sys
from pathlib import Path

VERSION_FILE = Path("compote3/VERSION")


def get_current_version():
    """Extract current version from VERSION file"""
    if not VERSION_FILE.exists():
        print(f"Warning: {VERSION_FILE} not found")
        return None
    
    content = VERSION_FILE.read_text().strip()
    if not content:
        print(f"Warning: {VERSION_FILE} is empty")
        return None
    
    # Remove 'v' prefix if present
    version = content.lstrip('v')
    return version


def bump_version(version):
    """Bump patch version (e.g., 0.2.1 -> 0.2.2)"""
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


def update_version_file(new_version):
    """Update version in VERSION file (with 'v' prefix)"""
    VERSION_FILE.write_text(f"v{new_version}\n")


def main():
    """Main function"""
    # Check if any files in compote3 are staged (excluding VERSION itself)
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            capture_output=True,
            text=True,
            check=True
        )
        staged_files = [f for f in result.stdout.strip().split('\n') if f]
        
        # Check if any compote3 files are staged (excluding VERSION itself)
        compote_files_staged = any(
            f.startswith('compote3/') and not f.endswith('VERSION')
            for f in staged_files
        )
        
        if not compote_files_staged:
            # No compote files changed (other than VERSION), skip version bump
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
    
    update_version_file(new_version)
    
    # Stage the updated VERSION file
    import subprocess
    try:
        subprocess.run(
            ['git', 'add', str(VERSION_FILE)],
            check=True,
            capture_output=True
        )
        print(f"Bumped compote version from v{current_version} to v{new_version}")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not stage {VERSION_FILE}: {e}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

