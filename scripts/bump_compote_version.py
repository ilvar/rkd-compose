#!/usr/bin/env python3
"""
Pre-commit hook to automatically bump Compote version
Bumps the patch version when any files in compote3/ are changed
Usage: ./scripts/bump_compote_version.py [--force]
"""

import argparse
import re
import sys
from pathlib import Path

VERSION_FILE = Path("compote3/VERSION")
VALUES_FILE = Path("apps-chart/values.yaml")
CARGO_FILE = Path("compote3/Cargo.toml")
CARGO_LOCK = Path("compote3/Cargo.lock")


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
    print(f"Updated {VERSION_FILE} to v{new_version}")


def update_cargo_files(new_version):
    """Update the crate version in Cargo.toml and Cargo.lock

    The three version records — VERSION, the chart tag and the crate — have to
    agree, otherwise `compote3 --version`-shaped questions get a different
    answer from the image tag.
    """
    if not CARGO_FILE.exists():
        print(f"Warning: {CARGO_FILE} not found")
        return False

    content = CARGO_FILE.read_text()
    # Only the [package] version, which is the first `version =` in the file.
    new_content, count = re.subn(
        r'^version = "\d+\.\d+\.\d+"$',
        f'version = "{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        print(f"Warning: Could not find a package version in {CARGO_FILE}")
        return False

    CARGO_FILE.write_text(new_content)
    print(f"Updated {CARGO_FILE} to {new_version}")

    if CARGO_LOCK.exists():
        lock = CARGO_LOCK.read_text()
        new_lock, count = re.subn(
            r'(name = "compote3"\nversion = )"\d+\.\d+\.\d+"',
            rf'\g<1>"{new_version}"',
            lock,
            count=1,
        )
        if count == 1:
            CARGO_LOCK.write_text(new_lock)
            print(f"Updated {CARGO_LOCK} to {new_version}")
        else:
            print(f"Warning: Could not find compote3 in {CARGO_LOCK}")

    return True


def update_values_file(new_version):
    """Update version tag in values.yaml file"""
    if not VALUES_FILE.exists():
        print(f"Warning: {VALUES_FILE} not found")
        return False
    
    content = VALUES_FILE.read_text()
    
    # Pattern to match the tag line after "repository: ilvar/compote3"
    # Matches the tag line in compote3 section specifically
    pattern = r'(repository: ilvar/compote3\n\s+tag:\s+)(v?\d+\.\d+\.\d+)'
    match = re.search(pattern, content)
    
    if not match:
        print(f"Warning: Could not find compote3 tag line to update in {VALUES_FILE}")
        return False
    
    old_tag = match.group(2)
    replacement = rf'\1v{new_version}'
    new_content = re.sub(pattern, replacement, content)
    
    if new_content == content:
        print(f"Warning: Could not update compote3 tag line in {VALUES_FILE}")
        return False
    
    VALUES_FILE.write_text(new_content)
    print(f"Updated {VALUES_FILE} tag from {old_tag} to v{new_version}")
    return True


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Bump Compote version')
    parser.add_argument('--force', action='store_true', 
                       help='Force version bump even if no compote3 files are staged')
    args = parser.parse_args()
    
    # Check if any files in compote3 are staged (excluding VERSION itself)
    import subprocess
    compote_files_staged = False
    if not args.force:
        try:
            result = subprocess.run(
                ['git', 'diff', '--cached', '--name-only'],
                capture_output=True,
                text=True,
                check=True
            )
            staged_files = [f for f in result.stdout.strip().split('\n') if f]
            
            if staged_files:
                print(f"Checking staged files: {', '.join(staged_files)}")
            
            # Check if any compote3 files are staged (excluding VERSION itself)
            compote_files_staged = any(
                f.startswith('compote3/') and not f.endswith('VERSION')
                for f in staged_files
            )
            
            if not compote_files_staged:
                # No compote files changed (other than VERSION), skip version bump
                print("No compote3 files staged (excluding VERSION). Skipping version bump.")
                print("Use --force to bump version anyway.")
                return 0
        except subprocess.CalledProcessError:
            # If git command fails, continue anyway (might be run outside git context)
            print("Note: Could not check git staged files. Continuing anyway...")
            pass
    else:
        print("Force flag enabled. Bumping version regardless of staged files.")
    
    if compote_files_staged:
        print("Compote3 files detected. Bumping version...")
    else:
        print("Bumping version...")
    current_version = get_current_version()
    if not current_version:
        print("Error: Could not read current version from VERSION file")
        return 1
    
    print(f"Current version: v{current_version}")
    new_version = bump_version(current_version)
    if not new_version:
        print("Error: Could not bump version")
        return 1
    
    print(f"New version: v{new_version}")
    update_version_file(new_version)
    update_values_file(new_version)
    update_cargo_files(new_version)
    
    # Stage the updated files
    try:
        subprocess.run(
            ['git', 'add', str(VERSION_FILE), str(VALUES_FILE),
             str(CARGO_FILE), str(CARGO_LOCK)],
            check=True,
            capture_output=True
        )
        print(f"✓ Staged {VERSION_FILE}, {VALUES_FILE} and the Cargo manifests")
        print(f"✓ Successfully bumped compote version from v{current_version} to v{new_version}")
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not stage files: {e}")
        print(f"Note: Files were updated but not staged. You may need to stage them manually.")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

