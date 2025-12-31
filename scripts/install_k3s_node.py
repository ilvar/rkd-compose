#!/usr/bin/env python3
"""
Script to install k3s on a target node.
- Asks for IP suffix
- SSH to target node
- Checks for Docker and optionally cleans it up
- Gets k3s token from primary node (defaults to 124)
- Installs k3s as worker or control plane node
"""

import subprocess
import sys


def run_ssh_command(host, command, check=True):
    """Run a command via SSH on the target host."""
    ssh_cmd = ["ssh", f"root@{host}", command]
    try:
        result = subprocess.run(
            ssh_cmd,
            check=check,
            capture_output=True,
            text=True
        )
        return result.stdout.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout.strip() if e.stdout else "", e.returncode


def check_docker(host):
    """Check if Docker is installed and running."""
    stdout, returncode = run_ssh_command(host, "which docker", check=False)
    if returncode != 0:
        return False
    
    # Check if docker daemon is running
    stdout, returncode = run_ssh_command(host, "docker ps", check=False)
    return returncode == 0


def get_docker_containers(host):
    """Get list of running Docker containers."""
    stdout, returncode = run_ssh_command(host, "docker ps", check=False)
    if returncode == 0:
        return stdout
    return ""


def cleanup_docker(host):
    """Stop all containers and prune volumes."""
    print("Stopping all Docker containers...")
    run_ssh_command(host, "docker stop $(docker ps -aq)", check=False)
    
    print("Removing all Docker containers...")
    run_ssh_command(host, "docker rm $(docker ps -aq)", check=False)
    
    print("Pruning Docker volumes...")
    run_ssh_command(host, "docker volume prune -af", check=False)
    
    print("Docker cleanup completed.")


def get_k3s_token(server_host="192.168.1.124"):
    """Get the k3s node token from the server node."""
    print(f"Getting k3s token from {server_host}...")
    
    # Try to get token from the standard location
    token_cmd = "cat /var/lib/rancher/k3s/server/node-token 2>/dev/null || echo ''"
    token, returncode = run_ssh_command(server_host, token_cmd, check=False)
    
    if not token or returncode != 0:
        print(f"Warning: Could not get token from {server_host}")
        print("You may need to manually retrieve the token.")
        return None
    
    return token.strip()


def install_k3s_worker(host, server_host, token):
    """Install k3s as a worker node."""
    print(f"Installing k3s as worker node on {host}...")
    
    install_cmd = (
        f"curl -sfL https://get.k3s.io | "
        f"K3S_URL=https://{server_host}:6443 "
        f"K3S_TOKEN={token} sh -"
    )
    
    stdout, returncode = run_ssh_command(host, install_cmd, check=False)
    
    if returncode != 0:
        print(f"Error installing k3s worker: {stdout}")
        return False
    
    print("k3s worker installation completed.")
    return True


def install_k3s_control_plane(host, server_host, token):
    """Install k3s as a control plane node."""
    print(f"Installing k3s as control plane node on {host}...")
    
    if token:
        # Join existing cluster as additional control plane node
        install_cmd = (
            f"curl -sfL https://get.k3s.io | "
            f"K3S_TOKEN={token} sh -s - server --server https://{server_host}:6443"
        )
    else:
        # First control plane node
        install_cmd = "curl -sfL https://get.k3s.io | sh -"
    
    stdout, returncode = run_ssh_command(host, install_cmd, check=False)
    
    if returncode != 0:
        print(f"Error installing k3s control plane: {stdout}")
        return False
    
    print("k3s control plane installation completed.")
    return True


def main():
    # Ask for IP suffix
    suffix = input("Enter IP suffix (e.g., 122, 123): ").strip()
    if not suffix:
        print("Error: IP suffix is required.")
        sys.exit(1)
    
    # Ask for primary node suffix (default to 124)
    primary_suffix = input("Enter primary node IP suffix [124]: ").strip()
    if not primary_suffix:
        primary_suffix = "124"
    
    # Construct full IPs
    target_ip = f"192.168.1.{suffix}"
    server_ip = f"192.168.1.{primary_suffix}"
    
    print(f"\nTarget node: {target_ip}")
    print(f"Server node: {server_ip}\n")
    
    # Test SSH connection
    print(f"Testing SSH connection to {target_ip}...")
    stdout, returncode = run_ssh_command(target_ip, "echo 'SSH connection successful'", check=False)
    if returncode != 0:
        print(f"Error: Cannot connect to {target_ip} via SSH")
        print("Make sure SSH keys are set up and the host is reachable.")
        sys.exit(1)
    
    print("SSH connection successful!\n")
    
    # Check for Docker
    if check_docker(target_ip):
        print("Docker is installed and running.")
        containers = get_docker_containers(target_ip)
        if containers:
            print("\nRunning Docker containers:")
            print(containers)
            print()
        
        response = input("Do you want to terminate and clean up all Docker containers and volumes? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            cleanup_docker(target_ip)
        else:
            print("Skipping Docker cleanup.")
        print()
    else:
        print("Docker is not installed or not running.\n")
    
    # Get k3s token from server
    token = get_k3s_token(server_ip)
    if not token:
        print("Warning: Could not retrieve k3s token automatically.")
        manual_token = input("Enter k3s token manually (or press Enter to skip): ").strip()
        token = manual_token if manual_token else None
    
    # Ask for node type
    print("\nNode type:")
    print("1. Worker node")
    print("2. Control plane node")
    node_type = input("Enter choice (1 or 2): ").strip()
    
    # Install k3s
    success = False
    if node_type == "1":
        if not token:
            print("Error: Token is required for worker node installation.")
            sys.exit(1)
        success = install_k3s_worker(target_ip, server_ip, token)
    elif node_type == "2":
        success = install_k3s_control_plane(target_ip, server_ip, token)
    else:
        print("Invalid choice. Exiting.")
        sys.exit(1)
    
    if success:
        print("\n🎉 k3s installation completed successfully!")
    else:
        print("\n❌ k3s installation failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()

