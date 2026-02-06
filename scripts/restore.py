#!/usr/bin/env python3
"""
Backup Restore TUI for Kubernetes homelab.

Reads apps-chart/values.yaml to discover backup configuration,
lists snapshots in restic repositories on B2, and restores selected backups.

Requirements: kubectl, restic, python3 (3.8+)
Environment: B2_ACCOUNT_ID, B2_ACCOUNT_KEY, RESTIC_PASSWORD
  (or access to kubectl to read from backblaze-credentials secret)
No pip dependencies required (uses stdlib curses + yaml parsing).
"""

import argparse
import base64
import curses
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Minimal YAML parser (enough for values.yaml, avoids PyYAML dependency)
# ---------------------------------------------------------------------------

def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML subset parser. Handles nested dicts, lists, and scalars."""
    import re

    lines = text.splitlines()
    root: dict = {}
    stack: list[tuple[int, dict | list]] = [(-1, root)]

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.rstrip()
        i += 1

        if not stripped or stripped.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip())

        # pop stack to find parent
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        parent_indent, parent = stack[-1]

        # list item
        if stripped.lstrip().startswith("- "):
            content = stripped.lstrip()[2:].strip()
            if isinstance(parent, list):
                lst = parent
            elif isinstance(parent, dict):
                # find last key added
                last_key = list(parent.keys())[-1] if parent else None
                if last_key and isinstance(parent[last_key], list):
                    lst = parent[last_key]
                else:
                    lst = []
                    if last_key:
                        parent[last_key] = lst
            else:
                lst = []

            if ":" in content and not content.startswith("{"):
                item: dict = {}
                # inline key: value on the dash line
                k, v = content.split(":", 1)
                k = k.strip()
                v = v.strip()
                item[k] = _yaml_scalar(v)
                lst.append(item)
                stack.append((indent + 2, item))
            else:
                lst.append(_yaml_scalar(content))
            continue

        # key: value
        m = re.match(r'^(\s*)([\w.\-/]+)\s*:\s*(.*)', stripped)
        if m and isinstance(parent, dict):
            key = m.group(2)
            val = m.group(3).strip()
            if val == "" or val == "|":
                # could be a nested dict, list, or block scalar
                # peek ahead
                if i < len(lines):
                    next_stripped = lines[i].rstrip()
                    next_indent = len(lines[i]) - len(lines[i].lstrip()) if next_stripped.strip() else 0
                    if next_stripped.strip().startswith("- "):
                        parent[key] = []
                        stack.append((indent, parent))
                        continue
                    elif next_indent > indent and val == "|":
                        # block scalar - collect lines
                        block_lines = []
                        while i < len(lines):
                            bl = lines[i]
                            bl_stripped = bl.rstrip()
                            if bl_stripped == "" or (len(bl) - len(bl.lstrip()) > indent):
                                block_lines.append(bl_stripped)
                                i += 1
                            else:
                                break
                        parent[key] = "\n".join(block_lines)
                        continue
                    elif next_indent > indent:
                        child: dict = {}
                        parent[key] = child
                        stack.append((indent, parent))
                        stack.append((indent, child))
                        continue
                parent[key] = None
            else:
                parent[key] = _yaml_scalar(val)
            continue

    return root


def _yaml_scalar(val: str):
    """Convert a YAML scalar string to Python type."""
    if val in ("true", "True", "yes"):
        return True
    if val in ("false", "False", "no"):
        return False
    if val in ("null", "~", ""):
        return None

    # remove surrounding quotes
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]

    # try int/float
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass

    # strip inline comments
    for sep in ("  #", "\t#"):
        if sep in val:
            val = val[:val.index(sep)].rstrip()
            break

    return val


def load_values(chart_dir: str) -> dict:
    """Load and parse values.yaml, trying PyYAML first, falling back to simple parser."""
    values_path = os.path.join(chart_dir, "values.yaml")
    with open(values_path) as f:
        text = f.read()

    try:
        import yaml  # noqa: F811
        return yaml.safe_load(text)
    except ImportError:
        return _parse_yaml_simple(text)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class BackupSnapshot:
    id: str
    short_id: str
    time: str
    hostname: str
    paths: list[str] = field(default_factory=list)

    @property
    def display_time(self) -> str:
        return self.time[:19].replace("T", " ")


@dataclass
class BackupGroup:
    name: str
    restic_repo: str
    restore_type: str  # postgres, mysql, sqlite, tar, etcd, meilisearch, immich-data, dir
    # Restore target info
    workload_type: str = ""  # deployment, statefulset
    workload_name: str = ""
    namespace: str = "default"
    container_name: str = ""
    # For postgres/mysql
    db_host: str = ""
    db_port: str = ""
    db_user: str = ""
    db_name: str = ""
    secret_name: str = ""
    password_key: str = ""
    # Mount path for dir-based restores
    mount_path: str = "/data"
    # Snapshots discovered from restic
    snapshots: list[BackupSnapshot] = field(default_factory=list)


# ---------------------------------------------------------------------------
# restic helpers
# ---------------------------------------------------------------------------

def restic_snapshots(repo: str) -> list[dict]:
    """List snapshots in a restic repository."""
    try:
        result = subprocess.run(
            ["restic", "-r", repo, "snapshots", "--json"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ},
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def restic_restore(repo: str, snapshot_id: str, target: str) -> bool:
    """Restore a restic snapshot to a target directory."""
    result = subprocess.run(
        ["restic", "-r", repo, "restore", snapshot_id, "--target", target],
        env={**os.environ},
        timeout=600,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# kubectl helpers
# ---------------------------------------------------------------------------

def kubectl(*args: str, capture: bool = False, namespace: str = "default") -> subprocess.CompletedProcess:
    cmd = ["kubectl", "-n", namespace] + list(args)
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return subprocess.run(cmd, timeout=120)


def scale_workload(kind: str, name: str, replicas: int, namespace: str = "default"):
    print(f"  Scaling {kind}/{name} to {replicas}...")
    kubectl("scale", f"{kind}/{name}", f"--replicas={replicas}", namespace=namespace)
    if replicas == 0:
        print(f"  Waiting for {kind}/{name} to scale down...")
        kubectl("rollout", "status", f"{kind}/{name}", "--timeout=120s", namespace=namespace)


def get_pod_name(label_selector: str, namespace: str = "default") -> Optional[str]:
    result = kubectl("get", "pods", "-l", label_selector, "-o", "jsonpath={.items[0].metadata.name}",
                     capture=True, namespace=namespace)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

def ensure_restic_env(values: dict) -> bool:
    """Ensure restic environment variables are set, reading from k8s secret if needed."""
    bb = values.get("backups", {}).get("backblaze", {})
    secret_name = bb.get("secretName", "backblaze-credentials")

    key_mapping = {
        "B2_ACCOUNT_ID": bb.get("accountIdKey", "account-id"),
        "B2_ACCOUNT_KEY": bb.get("applicationKeyKey", "application-key"),
        "RESTIC_PASSWORD": bb.get("resticPasswordKey", "restic-password"),
    }

    missing = [v for v in key_mapping if not os.environ.get(v)]
    if not missing:
        return True

    # Try to get from k8s secret
    print(f"Reading credentials from k8s secret '{secret_name}'...")
    for env_var in missing:
        secret_key = key_mapping[env_var]
        result = kubectl("get", "secret", secret_name,
                        "-o", f'jsonpath={{.data["{secret_key}"]}}',
                        capture=True)
        if result.returncode == 0 and result.stdout.strip():
            os.environ[env_var] = base64.b64decode(result.stdout.strip()).decode()
        else:
            print(f"ERROR: {env_var} not set and could not read key '{secret_key}' from secret '{secret_name}'")
            print(f"Set environment variables manually:")
            print(f"  export B2_ACCOUNT_ID=...")
            print(f"  export B2_ACCOUNT_KEY=...")
            print(f"  export RESTIC_PASSWORD=...")
            return False

    return True


# ---------------------------------------------------------------------------
# Build backup groups from values.yaml
# ---------------------------------------------------------------------------

def build_groups(values: dict) -> list[BackupGroup]:
    groups: list[BackupGroup] = []
    backups = values.get("backups", {})
    if not backups:
        return groups

    bb = backups.get("backblaze", {})
    bucket = bb.get("bucket", "")
    if not bucket:
        return groups

    def repo(path: str) -> str:
        return f"b2:{bucket}:{path}"

    # Postgres databases
    pg = backups.get("postgres", {})
    if pg.get("enabled"):
        for db in pg.get("databases", []):
            groups.append(BackupGroup(
                name=f"postgres/{db['name']}",
                restic_repo=repo(f"postgres/{db['name']}"),
                restore_type="postgres",
                db_host=db.get("host", ""),
                db_port=str(db.get("port", "5432")),
                db_user=db.get("user", "postgres"),
                db_name=db.get("database", db["name"]),
                secret_name=db.get("secretName", ""),
                password_key=db.get("passwordKey", "postgres-password"),
            ))

    # MySQL databases
    mysql = backups.get("mysql", {})
    if mysql.get("enabled"):
        for db in mysql.get("databases", []):
            groups.append(BackupGroup(
                name=f"mysql/{db['name']}",
                restic_repo=repo(f"mysql/{db['name']}"),
                restore_type="mysql",
                db_host=db.get("host", ""),
                db_port=str(db.get("port", "3306")),
                db_user=db.get("user", "root"),
                db_name=db.get("database", db["name"]),
                secret_name=db.get("secretName", ""),
                password_key=db.get("passwordKey", "mysql-password"),
            ))

    # etcd
    etcd = backups.get("etcd", {})
    if etcd.get("enabled"):
        groups.append(BackupGroup(
            name="etcd",
            restic_repo=repo("etcd"),
            restore_type="etcd",
        ))

    # Meilisearch
    meili = backups.get("meilisearch", {})
    if meili.get("enabled"):
        for inst in meili.get("instances", []):
            groups.append(BackupGroup(
                name=f"meilisearch/{inst['name']}",
                restic_repo=repo(f"meilisearch/{inst['name']}"),
                restore_type="meilisearch",
            ))

    # Beszel (directory backup)
    beszel = backups.get("beszel", {})
    if beszel.get("enabled"):
        groups.append(BackupGroup(
            name="beszel",
            restic_repo=repo("beszel"),
            restore_type="dir",
            workload_type="deployment",
            workload_name="beszel-hub",
            mount_path="/beszel_data",
        ))

    # Zigbee2mqtt (directory backup)
    z2m = backups.get("zigbee2mqtt", {})
    if z2m.get("enabled"):
        groups.append(BackupGroup(
            name="zigbee2mqtt",
            restic_repo=repo("zigbee2mqtt"),
            restore_type="dir",
            workload_type="deployment",
            workload_name="zigbee2mqtt",
            mount_path="/app/data",
        ))

    # Hoarder (sqlite)
    hoarder = backups.get("hoarder", {})
    if hoarder.get("enabled"):
        groups.append(BackupGroup(
            name="hoarder",
            restic_repo=repo("hoarder"),
            restore_type="sqlite",
            workload_type="deployment",
            workload_name="hoarder-web",
            mount_path="/data",
        ))

    # Bugsink (sqlite)
    bugsink = backups.get("bugsink", {})
    if bugsink.get("enabled"):
        groups.append(BackupGroup(
            name="bugsink",
            restic_repo=repo("bugsink"),
            restore_type="sqlite",
            workload_type="deployment",
            workload_name="bugsink",
            mount_path="/data",
        ))

    # Redis
    redis_cfg = backups.get("redis", {})
    if redis_cfg.get("enabled"):
        for inst in redis_cfg.get("instances", []):
            groups.append(BackupGroup(
                name=f"redis/{inst['name']}",
                restic_repo=repo(f"redis/{inst['name']}"),
                restore_type="redis",
            ))

    # Immich data
    immich = backups.get("immichData", {})
    if immich.get("enabled"):
        groups.append(BackupGroup(
            name="immich-data",
            restic_repo=repo("immich-data"),
            restore_type="immich-data",
        ))

    return groups


def fetch_snapshots(group: BackupGroup):
    """Populate group.snapshots from restic repository."""
    entries = restic_snapshots(group.restic_repo)
    group.snapshots = []
    for entry in entries:
        group.snapshots.append(BackupSnapshot(
            id=entry.get("id", ""),
            short_id=entry.get("short_id", entry.get("id", "")[:8]),
            time=entry.get("time", ""),
            hostname=entry.get("hostname", ""),
            paths=entry.get("paths", []),
        ))
    # Sort newest first
    group.snapshots.sort(key=lambda s: s.time, reverse=True)


# ---------------------------------------------------------------------------
# Restore implementations
# ---------------------------------------------------------------------------

def restore_postgres(group: BackupGroup, snapshot: BackupSnapshot):
    """Restore a PostgreSQL backup from restic snapshot."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Restoring snapshot {snapshot.short_id}...")
        if not restic_restore(group.restic_repo, snapshot.id, tmpdir):
            print("  ERROR: Failed to restore snapshot")
            return

        # Find the backup file (e.g., immich.sql.gz)
        sql_files = []
        for f in os.listdir(tmpdir):
            if f.endswith(".sql") or f.endswith(".sql.gz"):
                sql_files.append(f)
        if not sql_files:
            print(f"  ERROR: No .sql or .sql.gz files found in restored snapshot")
            return

        local_file = os.path.join(tmpdir, sql_files[0])
        backup_filename = sql_files[0]
        print(f"  Restoring {backup_filename} to {group.db_host}:{group.db_port}/{group.db_name}...")

        # Get password from secret
        pw_result = kubectl("get", "secret", group.secret_name,
                           "-o", f'jsonpath={{.data["{group.password_key}"]}}',
                           capture=True, namespace=group.namespace)
        if pw_result.returncode != 0:
            print(f"  ERROR: Could not get password from secret {group.secret_name}")
            return

        password = base64.b64decode(pw_result.stdout).decode()

        pod_name = get_pod_name(f"app={group.db_host.split('-')[0]}", namespace=group.namespace)
        if not pod_name:
            pod_name = get_pod_name(f"app.kubernetes.io/name={group.db_host}", namespace=group.namespace)

        if pod_name:
            print(f"  Using pod: {pod_name}")
            kubectl("cp", local_file, f"{group.namespace}/{pod_name}:/tmp/{backup_filename}",
                    namespace=group.namespace)

            if backup_filename.endswith(".gz"):
                restore_cmd = f"gunzip -c /tmp/{backup_filename} | PGPASSWORD='{password}' psql -h localhost -U {group.db_user} -d {group.db_name}"
            else:
                restore_cmd = f"PGPASSWORD='{password}' psql -h localhost -U {group.db_user} -d {group.db_name} < /tmp/{backup_filename}"

            kubectl("exec", pod_name, "--", "sh", "-c", restore_cmd, namespace=group.namespace)
            kubectl("exec", pod_name, "--", "rm", "-f", f"/tmp/{backup_filename}", namespace=group.namespace)
            print("  PostgreSQL restore completed")
        else:
            print(f"  ERROR: Could not find pod for {group.db_host}")


def restore_mysql(group: BackupGroup, snapshot: BackupSnapshot):
    """Restore a MySQL backup from restic snapshot."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Restoring snapshot {snapshot.short_id}...")
        if not restic_restore(group.restic_repo, snapshot.id, tmpdir):
            print("  ERROR: Failed to restore snapshot")
            return

        sql_files = [f for f in os.listdir(tmpdir)
                     if f.endswith(".sql") or f.endswith(".sql.gz")]
        if not sql_files:
            print("  ERROR: No .sql or .sql.gz files found in restored snapshot")
            return

        local_file = os.path.join(tmpdir, sql_files[0])
        backup_filename = sql_files[0]

        pod_name = get_pod_name(f"app={group.db_host}", namespace=group.namespace)
        if not pod_name:
            print(f"  ERROR: Could not find pod for {group.db_host}")
            return

        # Get password
        pw_result = kubectl("get", "secret", group.secret_name,
                           "-o", f'jsonpath={{.data["{group.password_key}"]}}',
                           capture=True, namespace=group.namespace)
        if pw_result.returncode != 0:
            print(f"  ERROR: Could not get password from secret {group.secret_name}")
            return

        password = base64.b64decode(pw_result.stdout).decode()

        print(f"  Using pod: {pod_name}")
        kubectl("cp", local_file, f"{group.namespace}/{pod_name}:/tmp/{backup_filename}",
                namespace=group.namespace)

        if backup_filename.endswith(".gz"):
            restore_cmd = f"gunzip -c /tmp/{backup_filename} | mysql -h localhost -u {group.db_user} -p'{password}' {group.db_name}"
        else:
            restore_cmd = f"mysql -h localhost -u {group.db_user} -p'{password}' {group.db_name} < /tmp/{backup_filename}"

        kubectl("exec", pod_name, "--", "sh", "-c", restore_cmd, namespace=group.namespace)
        kubectl("exec", pod_name, "--", "rm", "-f", f"/tmp/{backup_filename}", namespace=group.namespace)
        print("  MySQL restore completed")


def restore_dir(group: BackupGroup, snapshot: BackupSnapshot):
    """Restore a directory backup by restoring snapshot, scaling down, kubectl cp, scaling back up."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Restoring snapshot {snapshot.short_id}...")
        if not restic_restore(group.restic_repo, snapshot.id, tmpdir):
            print("  ERROR: Failed to restore snapshot")
            return

        # Scale down
        scale_workload(group.workload_type, group.workload_name, 0, group.namespace)

        # Scale back up to copy files
        print("  Scaling back up to copy files...")
        scale_workload(group.workload_type, group.workload_name, 1, group.namespace)

        import time
        time.sleep(5)

        pod_name = get_pod_name(f"app={group.workload_name}", namespace=group.namespace)
        if not pod_name:
            pod_name = get_pod_name(f"app.kubernetes.io/name={group.workload_name}", namespace=group.namespace)

        if not pod_name:
            print(f"  ERROR: Could not find pod for {group.workload_name}")
            return

        print(f"  Copying files to pod {pod_name}:{group.mount_path}/...")
        for item in os.listdir(tmpdir):
            src = os.path.join(tmpdir, item)
            kubectl("cp", src, f"{group.namespace}/{pod_name}:{group.mount_path}/{item}",
                    namespace=group.namespace)

        # Restart the pod to pick up new files
        kubectl("delete", "pod", pod_name, namespace=group.namespace)
        print("  Directory restore completed, pod restarting")


def restore_sqlite(group: BackupGroup, snapshot: BackupSnapshot):
    """Restore SQLite databases from restic snapshot."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Restoring snapshot {snapshot.short_id}...")
        if not restic_restore(group.restic_repo, snapshot.id, tmpdir):
            print("  ERROR: Failed to restore snapshot")
            return

        # Scale down
        scale_workload(group.workload_type, group.workload_name, 0, group.namespace)

        # Scale back up to copy
        print("  Scaling back up to copy files...")
        scale_workload(group.workload_type, group.workload_name, 1, group.namespace)

        import time
        time.sleep(5)

        pod_name = get_pod_name(f"app={group.workload_name}", namespace=group.namespace)
        if not pod_name:
            pod_name = get_pod_name(f"app.kubernetes.io/name={group.workload_name}", namespace=group.namespace)

        if not pod_name:
            print(f"  ERROR: Could not find pod for {group.workload_name}")
            return

        print(f"  Copying .db files to pod {pod_name}:{group.mount_path}/...")
        for item in os.listdir(tmpdir):
            if item.endswith(".db"):
                src = os.path.join(tmpdir, item)
                kubectl("cp", src, f"{group.namespace}/{pod_name}:{group.mount_path}/{item}",
                        namespace=group.namespace)
                print(f"    Copied {item}")

        # Restart pod
        kubectl("delete", "pod", pod_name, namespace=group.namespace)
        print("  SQLite restore completed, pod restarting")


def restore_etcd(group: BackupGroup, snapshot: BackupSnapshot):
    """Restore etcd snapshot and print manual restore instructions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Restoring snapshot {snapshot.short_id}...")
        if not restic_restore(group.restic_repo, snapshot.id, tmpdir):
            print("  ERROR: Failed to restore snapshot")
            return

        # Find the .db file
        db_files = [f for f in os.listdir(tmpdir) if f.endswith(".db")]
        if not db_files:
            print("  ERROR: No .db files found in restored snapshot")
            return

        src = os.path.join(tmpdir, db_files[0])
        dest = os.path.expanduser(f"~/etcd-restore-{db_files[0]}")
        subprocess.run(["cp", src, dest])

        print(f"\n  Snapshot saved to: {dest}")
        print("\n  MANUAL RESTORE INSTRUCTIONS:")
        print("  1. Stop k3s:  sudo systemctl stop k3s")
        print(f"  2. Restore:   sudo etcdctl snapshot restore {dest} \\")
        print("                  --data-dir=/var/lib/rancher/k3s/server/db/etcd-new")
        print("  3. Replace:   sudo mv /var/lib/rancher/k3s/server/db/etcd /var/lib/rancher/k3s/server/db/etcd-old")
        print("                sudo mv /var/lib/rancher/k3s/server/db/etcd-new /var/lib/rancher/k3s/server/db/etcd")
        print("  4. Start k3s: sudo systemctl start k3s")
        print("\n  WARNING: This will replace ALL cluster state!")


def restore_meilisearch(group: BackupGroup, snapshot: BackupSnapshot):
    """Restore meilisearch backup and print instructions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Restoring snapshot {snapshot.short_id}...")
        if not restic_restore(group.restic_repo, snapshot.id, tmpdir):
            print("  ERROR: Failed to restore snapshot")
            return

        dest_dir = os.path.expanduser(f"~/meilisearch-restore-{snapshot.short_id}")
        subprocess.run(["cp", "-r", tmpdir, dest_dir])

        print(f"\n  Backup saved to: {dest_dir}")
        print("\n  MANUAL RESTORE INSTRUCTIONS:")
        print("  Meilisearch restore requires importing dumps/snapshots via the API.")
        print("  See: https://www.meilisearch.com/docs/learn/advanced/snapshots")


def do_restore(group: BackupGroup, snapshot: BackupSnapshot):
    """Dispatch restore based on type."""
    print(f"\nRestoring {group.name}: snapshot {snapshot.short_id}")
    print(f"  Type: {group.restore_type}")
    print(f"  Time: {snapshot.display_time}")
    print(f"  Host: {snapshot.hostname}")
    print()

    if group.restore_type == "immich-data":
        print("  SKIPPED: immich-data is too large for automated restore.")
        print("  Use restic restore manually:")
        print(f"    restic -r {group.restic_repo} restore latest --target /path/to/immich/upload/")
        return

    handlers = {
        "postgres": restore_postgres,
        "mysql": restore_mysql,
        "dir": restore_dir,
        "sqlite": restore_sqlite,
        "etcd": restore_etcd,
        "meilisearch": restore_meilisearch,
    }

    handler = handlers.get(group.restore_type)
    if handler:
        handler(group, snapshot)
    else:
        print(f"  ERROR: Unknown restore type: {group.restore_type}")


# ---------------------------------------------------------------------------
# TUI with curses
# ---------------------------------------------------------------------------

class TUI:
    def __init__(self, groups: list[BackupGroup]):
        self.groups = groups
        self.expanded: set[int] = set()
        self.cursor = 0
        self.scroll_offset = 0
        self.items: list[tuple[int, Optional[int]]] = []  # (group_idx, snapshot_idx or None)
        self._rebuild_items()

    def _rebuild_items(self):
        self.items = []
        for gi, group in enumerate(self.groups):
            self.items.append((gi, None))
            if gi in self.expanded:
                for si in range(len(group.snapshots)):
                    self.items.append((gi, si))
        if self.cursor >= len(self.items):
            self.cursor = max(0, len(self.items) - 1)

    def run(self, stdscr):
        curses.curs_set(0)
        curses.use_default_colors()

        if curses.has_colors():
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()

            # Header
            header = " Backup Restore TUI (restic) - Press Enter to expand/restore, q to quit "
            stdscr.addstr(0, 0, header[:w].ljust(w), curses.A_REVERSE)

            # Visible area
            visible_h = h - 3
            if self.cursor < self.scroll_offset:
                self.scroll_offset = self.cursor
            elif self.cursor >= self.scroll_offset + visible_h:
                self.scroll_offset = self.cursor - visible_h + 1

            for row_idx in range(visible_h):
                item_idx = self.scroll_offset + row_idx
                if item_idx >= len(self.items):
                    break

                gi, si = self.items[item_idx]
                y = row_idx + 1

                is_selected = item_idx == self.cursor
                attr = curses.A_REVERSE if is_selected else 0

                if si is None:
                    # Group header
                    group = self.groups[gi]
                    arrow = "v" if gi in self.expanded else ">"
                    type_tag = f"[{group.restore_type}]"
                    snap_count = f"({len(group.snapshots)} snapshots)" if group.snapshots else "(loading...)" if gi in self.expanded else ""
                    line = f" {arrow} {group.name} {type_tag} {snap_count}"

                    color = curses.color_pair(1) if curses.has_colors() else 0
                    try:
                        stdscr.addstr(y, 0, line[:w].ljust(w), attr | color | curses.A_BOLD)
                    except curses.error:
                        pass
                else:
                    # Snapshot entry
                    group = self.groups[gi]
                    snap = group.snapshots[si]
                    line = f"     {snap.short_id}  {snap.display_time}  ({snap.hostname})"
                    color = curses.color_pair(2) if curses.has_colors() else 0
                    try:
                        stdscr.addstr(y, 0, line[:w].ljust(w), attr | color)
                    except curses.error:
                        pass

            # Footer
            footer = " [Enter] Expand/Restore  [q] Quit  [j/k or arrows] Navigate "
            try:
                stdscr.addstr(h - 1, 0, footer[:w].ljust(w), curses.A_REVERSE)
            except curses.error:
                pass

            stdscr.refresh()

            key = stdscr.getch()

            if key in (ord("q"), ord("Q"), 27):
                return None

            elif key in (curses.KEY_UP, ord("k")):
                if self.cursor > 0:
                    self.cursor -= 1

            elif key in (curses.KEY_DOWN, ord("j")):
                if self.cursor < len(self.items) - 1:
                    self.cursor += 1

            elif key in (curses.KEY_PPAGE,):
                self.cursor = max(0, self.cursor - visible_h)

            elif key in (curses.KEY_NPAGE,):
                self.cursor = min(len(self.items) - 1, self.cursor + visible_h)

            elif key in (ord("\n"), curses.KEY_ENTER, 10, 13):
                if not self.items:
                    continue
                gi, si = self.items[self.cursor]

                if si is None:
                    # Toggle expand
                    if gi in self.expanded:
                        self.expanded.discard(gi)
                    else:
                        self.expanded.add(gi)
                        if not self.groups[gi].snapshots:
                            # Fetch snapshots
                            stdscr.addstr(0, 0, " Fetching snapshots...".ljust(w), curses.A_REVERSE)
                            stdscr.refresh()
                            fetch_snapshots(self.groups[gi])
                    self._rebuild_items()
                else:
                    # Selected a snapshot - confirm restore
                    group = self.groups[gi]
                    snap = group.snapshots[si]

                    stdscr.clear()
                    stdscr.addstr(0, 0, " CONFIRM RESTORE ".center(w), curses.A_REVERSE)
                    stdscr.addstr(2, 2, f"Group:    {group.name}")
                    stdscr.addstr(3, 2, f"Snapshot: {snap.short_id}")
                    stdscr.addstr(4, 2, f"Time:     {snap.display_time}")
                    stdscr.addstr(5, 2, f"Host:     {snap.hostname}")
                    stdscr.addstr(6, 2, f"Type:     {group.restore_type}")
                    stdscr.addstr(8, 2, "Press 'y' to confirm, any other key to cancel")
                    stdscr.refresh()

                    confirm = stdscr.getch()
                    if confirm in (ord("y"), ord("Y")):
                        return (group, snap)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_chart_dir() -> str:
    """Find the apps-chart directory relative to this script."""
    script_dir = Path(__file__).resolve().parent
    # Try ../apps-chart (typical layout: scripts/restore.py -> apps-chart/)
    candidate = script_dir.parent / "apps-chart"
    if candidate.exists():
        return str(candidate)
    # Try current dir
    if Path("apps-chart").exists():
        return "apps-chart"
    return str(candidate)  # fallback


def cmd_list(args):
    """List all available backups."""
    values = load_values(args.chart_dir)

    if not ensure_restic_env(values):
        sys.exit(1)

    groups = build_groups(values)

    if not groups:
        print("No backup groups found in values.yaml")
        return

    print(f"Fetching snapshots from restic repositories...")
    for group in groups:
        fetch_snapshots(group)
        print(f"\n{group.name} [{group.restore_type}] repo={group.restic_repo}")
        if group.snapshots:
            for snap in group.snapshots:
                print(f"  {snap.short_id}  {snap.display_time}  ({snap.hostname})")
        else:
            print("  (no snapshots found)")


def cmd_tui(args):
    """Launch the interactive TUI."""
    values = load_values(args.chart_dir)

    if not ensure_restic_env(values):
        sys.exit(1)

    groups = build_groups(values)

    if not groups:
        print("No backup groups found in values.yaml")
        return

    tui = TUI(groups)
    result = curses.wrapper(tui.run)

    if result is None:
        print("Cancelled.")
        return

    group, snapshot = result
    print()  # clear line after curses
    do_restore(group, snapshot)


def main():
    parser = argparse.ArgumentParser(
        description="Restore encrypted restic backups from B2 for Kubernetes homelab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables (read from k8s secret if not set):
  B2_ACCOUNT_ID      Backblaze B2 account ID
  B2_ACCOUNT_KEY     Backblaze B2 application key
  RESTIC_PASSWORD    Restic repository encryption password

Examples:
  %(prog)s                   Launch interactive TUI
  %(prog)s --list            List all available backups
  %(prog)s --chart-dir ./apps-chart  Specify chart directory
        """,
    )
    parser.add_argument("--list", action="store_true",
                       help="List all available backups (non-interactive)")
    parser.add_argument("--chart-dir", default=find_chart_dir(),
                       help="Path to apps-chart directory (default: auto-detect)")

    args = parser.parse_args()

    # Verify prerequisites
    for tool in ("kubectl", "restic"):
        if not subprocess.run(["which", tool], capture_output=True).returncode == 0:
            print(f"ERROR: {tool} not found in PATH. Please install it first.")
            sys.exit(1)

    if not os.path.exists(os.path.join(args.chart_dir, "values.yaml")):
        print(f"ERROR: values.yaml not found in {args.chart_dir}")
        print(f"Use --chart-dir to specify the correct path")
        sys.exit(1)

    if args.list:
        cmd_list(args)
    else:
        cmd_tui(args)


if __name__ == "__main__":
    main()
