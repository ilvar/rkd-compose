#!/usr/bin/env python3
"""
Backup Restore TUI for Kubernetes homelab.

Reads apps-chart/values.yaml to discover backup configuration,
lists files in B2 via rclone, and restores selected backups.

Requirements: kubectl, rclone (configured with b2 remote), python3 (3.8+)
No pip dependencies required (uses stdlib curses + yaml parsing).
"""

import argparse
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
class BackupFile:
    name: str
    size: int
    mod_time: str

    @property
    def size_human(self) -> str:
        s = self.size
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(s) < 1024:
                return f"{s:.1f} {unit}"
            s /= 1024
        return f"{s:.1f} PB"


@dataclass
class BackupGroup:
    name: str
    b2_path: str
    restore_type: str  # postgres, mysql, sqlite, tar, etcd, meilisearch, immich-data
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
    # Files discovered from B2
    files: list[BackupFile] = field(default_factory=list)


# ---------------------------------------------------------------------------
# B2 / rclone helpers
# ---------------------------------------------------------------------------

def rclone_lsjson(b2_path: str) -> list[dict]:
    """List files in a B2 path using rclone lsjson."""
    try:
        result = subprocess.run(
            ["rclone", "lsjson", b2_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def rclone_copy(src: str, dst: str) -> bool:
    """Copy a file using rclone."""
    result = subprocess.run(
        ["rclone", "copy", src, dst, "--progress"],
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

    # Postgres databases
    pg = backups.get("postgres", {})
    if pg.get("enabled"):
        for db in pg.get("databases", []):
            groups.append(BackupGroup(
                name=f"postgres/{db['name']}",
                b2_path=f"b2:{bucket}/postgres/{db['name']}/",
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
                b2_path=f"b2:{bucket}/mysql/{db['name']}/",
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
            b2_path=f"b2:{bucket}/etcd/",
            restore_type="etcd",
        ))

    # Meilisearch
    meili = backups.get("meilisearch", {})
    if meili.get("enabled"):
        for inst in meili.get("instances", []):
            groups.append(BackupGroup(
                name=f"meilisearch/{inst['name']}",
                b2_path=f"b2:{bucket}/meilisearch/{inst['name']}/",
                restore_type="meilisearch",
            ))

    # Beszel (tar.gz)
    beszel = backups.get("beszel", {})
    if beszel.get("enabled"):
        groups.append(BackupGroup(
            name="beszel",
            b2_path=f"b2:{bucket}/beszel/",
            restore_type="tar",
            workload_type="deployment",
            workload_name="beszel-hub",
        ))

    # Zigbee2mqtt (tar.gz)
    z2m = backups.get("zigbee2mqtt", {})
    if z2m.get("enabled"):
        groups.append(BackupGroup(
            name="zigbee2mqtt",
            b2_path=f"b2:{bucket}/zigbee2mqtt/",
            restore_type="tar",
            workload_type="deployment",
            workload_name="zigbee2mqtt",
        ))

    # Hoarder (sqlite)
    hoarder = backups.get("hoarder", {})
    if hoarder.get("enabled"):
        groups.append(BackupGroup(
            name="hoarder",
            b2_path=f"b2:{bucket}/hoarder/",
            restore_type="sqlite",
            workload_type="deployment",
            workload_name="hoarder-web",
        ))

    # Bugsink (sqlite)
    bugsink = backups.get("bugsink", {})
    if bugsink.get("enabled"):
        groups.append(BackupGroup(
            name="bugsink",
            b2_path=f"b2:{bucket}/bugsink/",
            restore_type="sqlite",
            workload_type="deployment",
            workload_name="bugsink",
        ))

    # Redis
    redis_cfg = backups.get("redis", {})
    if redis_cfg.get("enabled"):
        for inst in redis_cfg.get("instances", []):
            groups.append(BackupGroup(
                name=f"redis/{inst['name']}",
                b2_path=f"b2:{bucket}/redis/{inst['name']}/",
                restore_type="redis",
            ))

    # Immich data
    immich = backups.get("immichData", {})
    if immich.get("enabled"):
        groups.append(BackupGroup(
            name="immich-data",
            b2_path=f"b2:{bucket}/immich-data/",
            restore_type="immich-data",
        ))

    return groups


def fetch_files(group: BackupGroup):
    """Populate group.files from B2."""
    entries = rclone_lsjson(group.b2_path)
    group.files = []
    for entry in entries:
        if entry.get("IsDir"):
            continue
        group.files.append(BackupFile(
            name=entry.get("Name", ""),
            size=entry.get("Size", 0),
            mod_time=entry.get("ModTime", "")[:19].replace("T", " "),
        ))
    # Sort newest first
    group.files.sort(key=lambda f: f.mod_time, reverse=True)


# ---------------------------------------------------------------------------
# Restore implementations
# ---------------------------------------------------------------------------

def restore_postgres(group: BackupGroup, backup_file: BackupFile):
    """Restore a PostgreSQL backup by piping into the database pod."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Downloading {backup_file.name}...")
        if not rclone_copy(f"{group.b2_path}{backup_file.name}", tmpdir):
            print("  ERROR: Failed to download backup file")
            return

        local_file = os.path.join(tmpdir, backup_file.name)
        print(f"  Restoring to {group.db_host}:{group.db_port}/{group.db_name}...")

        # Get password from secret
        pw_result = kubectl("get", "secret", group.secret_name,
                           "-o", f"jsonpath={{.data.{group.password_key}}}",
                           capture=True, namespace=group.namespace)
        if pw_result.returncode != 0:
            print(f"  ERROR: Could not get password from secret {group.secret_name}")
            return

        import base64
        password = base64.b64decode(pw_result.stdout).decode()

        # Find a postgres pod or use the host directly via a temporary pod
        # Simpler: use kubectl exec on the database pod itself
        pod_name = get_pod_name(f"app={group.db_host.split('-')[0]}", namespace=group.namespace)
        if not pod_name:
            # Try matching the host as a service name, find pod by service
            pod_name = get_pod_name(f"app.kubernetes.io/name={group.db_host}", namespace=group.namespace)

        if pod_name:
            print(f"  Using pod: {pod_name}")
            # Copy file to pod, then restore
            kubectl("cp", local_file, f"{group.namespace}/{pod_name}:/tmp/{backup_file.name}",
                    namespace=group.namespace)

            if backup_file.name.endswith(".gz"):
                restore_cmd = f"gunzip -c /tmp/{backup_file.name} | PGPASSWORD='{password}' psql -h localhost -U {group.db_user} -d {group.db_name}"
            else:
                restore_cmd = f"PGPASSWORD='{password}' psql -h localhost -U {group.db_user} -d {group.db_name} < /tmp/{backup_file.name}"

            kubectl("exec", pod_name, "--", "sh", "-c", restore_cmd, namespace=group.namespace)
            kubectl("exec", pod_name, "--", "rm", "-f", f"/tmp/{backup_file.name}", namespace=group.namespace)
            print("  PostgreSQL restore completed")
        else:
            print(f"  ERROR: Could not find pod for {group.db_host}")


def restore_mysql(group: BackupGroup, backup_file: BackupFile):
    """Restore a MySQL backup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Downloading {backup_file.name}...")
        if not rclone_copy(f"{group.b2_path}{backup_file.name}", tmpdir):
            print("  ERROR: Failed to download backup file")
            return

        local_file = os.path.join(tmpdir, backup_file.name)
        pod_name = get_pod_name(f"app={group.db_host}", namespace=group.namespace)
        if not pod_name:
            print(f"  ERROR: Could not find pod for {group.db_host}")
            return

        # Get password
        import base64
        pw_result = kubectl("get", "secret", group.secret_name,
                           "-o", f"jsonpath={{.data.{group.password_key}}}",
                           capture=True, namespace=group.namespace)
        if pw_result.returncode != 0:
            print(f"  ERROR: Could not get password from secret {group.secret_name}")
            return

        password = base64.b64decode(pw_result.stdout).decode()

        print(f"  Using pod: {pod_name}")
        kubectl("cp", local_file, f"{group.namespace}/{pod_name}:/tmp/{backup_file.name}",
                namespace=group.namespace)

        if backup_file.name.endswith(".gz"):
            restore_cmd = f"gunzip -c /tmp/{backup_file.name} | mysql -h localhost -u {group.db_user} -p'{password}' {group.db_name}"
        else:
            restore_cmd = f"mysql -h localhost -u {group.db_user} -p'{password}' {group.db_name} < /tmp/{backup_file.name}"

        kubectl("exec", pod_name, "--", "sh", "-c", restore_cmd, namespace=group.namespace)
        kubectl("exec", pod_name, "--", "rm", "-f", f"/tmp/{backup_file.name}", namespace=group.namespace)
        print("  MySQL restore completed")


def restore_tar(group: BackupGroup, backup_file: BackupFile):
    """Restore a tar.gz backup by scaling down, kubectl cp, scaling back up."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Downloading {backup_file.name}...")
        if not rclone_copy(f"{group.b2_path}{backup_file.name}", tmpdir):
            print("  ERROR: Failed to download backup file")
            return

        local_file = os.path.join(tmpdir, backup_file.name)

        # Extract locally
        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir)
        subprocess.run(["tar", "-xzf", local_file, "-C", extract_dir], check=True)

        # Scale down
        scale_workload(group.workload_type, group.workload_name, 0, group.namespace)

        # Find the pod with the PVC (we need to use a temporary pod or the existing one)
        # After scaling to 0, there's no pod. We'll use kubectl cp via a temporary debug pod
        # or just scale back up and copy. Better approach: scale up, copy, restart.
        print("  Scaling back up to copy files...")
        scale_workload(group.workload_type, group.workload_name, 1, group.namespace)

        # Wait for pod to be ready
        import time
        time.sleep(5)

        pod_name = get_pod_name(f"app={group.workload_name}", namespace=group.namespace)
        if not pod_name:
            # Try alternative label
            pod_name = get_pod_name(f"app.kubernetes.io/name={group.workload_name}", namespace=group.namespace)

        if not pod_name:
            print(f"  ERROR: Could not find pod for {group.workload_name}")
            return

        print(f"  Copying files to pod {pod_name}...")
        # Copy extracted files into the pod's data directory
        # Determine the mount path based on the workload
        mount_path = "/data"
        if group.workload_name == "beszel-hub":
            mount_path = "/beszel_data"
        elif group.workload_name == "zigbee2mqtt":
            mount_path = "/app/data"

        for item in os.listdir(extract_dir):
            src = os.path.join(extract_dir, item)
            kubectl("cp", src, f"{group.namespace}/{pod_name}:{mount_path}/{item}",
                    namespace=group.namespace)

        # Restart the pod to pick up new files
        kubectl("delete", "pod", pod_name, namespace=group.namespace)
        print("  Tar restore completed, pod restarting")


def restore_sqlite(group: BackupGroup, backup_file: BackupFile):
    """Restore SQLite databases by scaling down, copying .db files, scaling up."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Downloading {backup_file.name}...")
        if not rclone_copy(f"{group.b2_path}{backup_file.name}", tmpdir):
            print("  ERROR: Failed to download backup file")
            return

        local_file = os.path.join(tmpdir, backup_file.name)

        # Extract locally
        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir)
        subprocess.run(["tar", "-xzf", local_file, "-C", extract_dir], check=True)

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

        mount_path = "/data"
        if group.workload_name == "hoarder-web":
            mount_path = "/data"
        elif group.workload_name == "bugsink":
            mount_path = "/data"

        print(f"  Copying .db files to pod {pod_name}:{mount_path}/...")
        for item in os.listdir(extract_dir):
            if item.endswith(".db"):
                src = os.path.join(extract_dir, item)
                kubectl("cp", src, f"{group.namespace}/{pod_name}:{mount_path}/{item}",
                        namespace=group.namespace)
                print(f"    Copied {item}")

        # Restart pod
        kubectl("delete", "pod", pod_name, namespace=group.namespace)
        print("  SQLite restore completed, pod restarting")


def restore_etcd(group: BackupGroup, backup_file: BackupFile):
    """Download etcd snapshot and print manual restore instructions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Downloading {backup_file.name}...")
        if not rclone_copy(f"{group.b2_path}{backup_file.name}", tmpdir):
            print("  ERROR: Failed to download backup file")
            return

        local_file = os.path.join(tmpdir, backup_file.name)
        dest = os.path.expanduser(f"~/etcd-restore-{backup_file.name}")
        subprocess.run(["cp", local_file, dest])

        print(f"\n  Snapshot saved to: {dest}")
        print("\n  MANUAL RESTORE INSTRUCTIONS:")
        print("  1. Stop k3s:  sudo systemctl stop k3s")
        print(f"  2. Restore:   sudo etcdctl snapshot restore {dest} \\")
        print("                  --data-dir=/var/lib/rancher/k3s/server/db/etcd-new")
        print("  3. Replace:   sudo mv /var/lib/rancher/k3s/server/db/etcd /var/lib/rancher/k3s/server/db/etcd-old")
        print("                sudo mv /var/lib/rancher/k3s/server/db/etcd-new /var/lib/rancher/k3s/server/db/etcd")
        print("  4. Start k3s: sudo systemctl start k3s")
        print("\n  WARNING: This will replace ALL cluster state!")


def restore_meilisearch(group: BackupGroup, backup_file: BackupFile):
    """Download meilisearch backup and print instructions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"  Downloading {backup_file.name}...")
        if not rclone_copy(f"{group.b2_path}{backup_file.name}", tmpdir):
            print("  ERROR: Failed to download backup file")
            return

        local_file = os.path.join(tmpdir, backup_file.name)
        dest = os.path.expanduser(f"~/meilisearch-restore-{backup_file.name}")
        subprocess.run(["cp", local_file, dest])

        print(f"\n  Backup saved to: {dest}")
        print("\n  MANUAL RESTORE INSTRUCTIONS:")
        print("  Meilisearch restore requires importing dumps/snapshots via the API.")
        print("  See: https://www.meilisearch.com/docs/learn/advanced/snapshots")


def do_restore(group: BackupGroup, backup_file: BackupFile):
    """Dispatch restore based on type."""
    print(f"\nRestoring {group.name}: {backup_file.name}")
    print(f"  Type: {group.restore_type}")
    print(f"  Size: {backup_file.size_human}")
    print()

    if group.restore_type == "immich-data":
        print("  SKIPPED: immich-data is too large for automated restore.")
        print("  Use rclone sync manually:")
        print(f"    rclone sync {group.b2_path} /path/to/immich/upload/")
        return

    handlers = {
        "postgres": restore_postgres,
        "mysql": restore_mysql,
        "tar": restore_tar,
        "sqlite": restore_sqlite,
        "etcd": restore_etcd,
        "meilisearch": restore_meilisearch,
    }

    handler = handlers.get(group.restore_type)
    if handler:
        handler(group, backup_file)
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
        self.items: list[tuple[int, Optional[int]]] = []  # (group_idx, file_idx or None)
        self._rebuild_items()

    def _rebuild_items(self):
        self.items = []
        for gi, group in enumerate(self.groups):
            self.items.append((gi, None))
            if gi in self.expanded:
                for fi in range(len(group.files)):
                    self.items.append((gi, fi))
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
            header = " Backup Restore TUI - Press Enter to expand/restore, q to quit "
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

                gi, fi = self.items[item_idx]
                y = row_idx + 1

                is_selected = item_idx == self.cursor
                attr = curses.A_REVERSE if is_selected else 0

                if fi is None:
                    # Group header
                    group = self.groups[gi]
                    arrow = "v" if gi in self.expanded else ">"
                    type_tag = f"[{group.restore_type}]"
                    file_count = f"({len(group.files)} files)" if group.files else "(loading...)" if gi in self.expanded else ""
                    line = f" {arrow} {group.name} {type_tag} {file_count}"

                    color = curses.color_pair(1) if curses.has_colors() else 0
                    try:
                        stdscr.addstr(y, 0, line[:w].ljust(w), attr | color | curses.A_BOLD)
                    except curses.error:
                        pass
                else:
                    # File entry
                    group = self.groups[gi]
                    bf = group.files[fi]
                    line = f"     {bf.name}  ({bf.size_human})  {bf.mod_time}"
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
                gi, fi = self.items[self.cursor]

                if fi is None:
                    # Toggle expand
                    if gi in self.expanded:
                        self.expanded.discard(gi)
                    else:
                        self.expanded.add(gi)
                        if not self.groups[gi].files:
                            # Fetch files
                            stdscr.addstr(0, 0, " Fetching file list...".ljust(w), curses.A_REVERSE)
                            stdscr.refresh()
                            fetch_files(self.groups[gi])
                    self._rebuild_items()
                else:
                    # Selected a file - confirm restore
                    group = self.groups[gi]
                    bf = group.files[fi]

                    stdscr.clear()
                    stdscr.addstr(0, 0, " CONFIRM RESTORE ".center(w), curses.A_REVERSE)
                    stdscr.addstr(2, 2, f"Group:  {group.name}")
                    stdscr.addstr(3, 2, f"File:   {bf.name}")
                    stdscr.addstr(4, 2, f"Size:   {bf.size_human}")
                    stdscr.addstr(5, 2, f"Date:   {bf.mod_time}")
                    stdscr.addstr(6, 2, f"Type:   {group.restore_type}")
                    stdscr.addstr(8, 2, "Press 'y' to confirm, any other key to cancel")
                    stdscr.refresh()

                    confirm = stdscr.getch()
                    if confirm in (ord("y"), ord("Y")):
                        return (group, bf)


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
    groups = build_groups(values)

    if not groups:
        print("No backup groups found in values.yaml")
        return

    print(f"Fetching file lists from B2...")
    for group in groups:
        fetch_files(group)
        print(f"\n{group.name} [{group.restore_type}]")
        if group.files:
            for bf in group.files:
                print(f"  {bf.name}  ({bf.size_human})  {bf.mod_time}")
        else:
            print("  (no files found)")


def cmd_tui(args):
    """Launch the interactive TUI."""
    values = load_values(args.chart_dir)
    groups = build_groups(values)

    if not groups:
        print("No backup groups found in values.yaml")
        return

    tui = TUI(groups)
    result = curses.wrapper(tui.run)

    if result is None:
        print("Cancelled.")
        return

    group, backup_file = result
    print()  # clear line after curses
    do_restore(group, backup_file)


def main():
    parser = argparse.ArgumentParser(
        description="Restore backups from B2 for Kubernetes homelab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
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
    for tool in ("kubectl", "rclone"):
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
