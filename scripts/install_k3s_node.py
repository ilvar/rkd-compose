#!/usr/bin/env python3
"""
Script to install k3s on a target node.
- Asks for IP suffix
- SSH to target node
- Checks for Docker and optionally cleans it up
- Gets k3s token from primary node (defaults to 126)
- Installs k3s as worker or control plane node
"""

import subprocess
import sys
import getpass


def run_ssh_command(host, command, username="root", check=True, sudo_password=None):
    """Run a command via SSH on the target host.
    
    If sudo_password is provided, it will be used with sudo -S for commands that need sudo.
    """
    ssh_cmd = ["ssh", f"{username}@{host}", command]
    try:
        result = subprocess.run(
            ssh_cmd,
            check=check,
            capture_output=True,
            text=True
        )
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""
        
        # Print output
        if stdout:
            print(f"STDOUT: {stdout}")
        if stderr:
            print(f"STDERR: {stderr}")
        
        return stdout, stderr, result.returncode
    except subprocess.CalledProcessError as e:
        stdout = e.stdout.strip() if e.stdout else ""
        stderr = e.stderr.strip() if e.stderr else ""
        
        # Print output
        if stdout:
            print(f"STDOUT: {stdout}")
        if stderr:
            print(f"STDERR: {stderr}")
        
        return stdout, stderr, e.returncode


def run_sudo_command(host, command, username="root", sudo_password=None):
    """Run a sudo command via SSH.
    
    If sudo_password is provided, uses 'printf to pipe password to sudo -S'.
    Otherwise, assumes passwordless sudo.
    """
    if sudo_password:
        # Use printf to safely pass password to sudo -S
        # Escape single quotes in password by replacing them with '\''
        escaped_password = sudo_password.replace("'", "'\\''")
        sudo_cmd = f"printf '%s\\n' '{escaped_password}' | sudo -S {command}"
    else:
        sudo_cmd = f"sudo {command}"
    
    return run_ssh_command(host, sudo_cmd, username=username, check=False)


def check_passwordless_sudo(host, username="root"):
    """Check if passwordless sudo works on the target host."""
    stdout, stderr, returncode = run_ssh_command(
        host, 
        "sudo -n true 2>&1", 
        username=username, 
        check=False
    )
    return returncode == 0


def check_docker(host, username="root"):
    """Check if Docker is installed and running."""
    stdout, stderr, returncode = run_ssh_command(host, "which docker", username=username, check=False)
    if returncode != 0:
        return False
    
    # Check if docker daemon is running
    stdout, stderr, returncode = run_ssh_command(host, "docker ps", username=username, check=False)
    return returncode == 0


def get_docker_containers(host, username="root"):
    """Get list of running Docker containers."""
    stdout, stderr, returncode = run_ssh_command(host, "docker ps", username=username, check=False)
    if returncode == 0:
        return stdout
    return ""


def cleanup_docker(host, username="root", sudo_password=None):
    """Stop all containers, prune volumes, and uninstall Docker."""
    print("Stopping all Docker containers...")
    run_ssh_command(host, "docker stop $(docker ps -aq)", username=username, check=False)
    
    print("Removing all Docker containers...")
    run_ssh_command(host, "docker rm $(docker ps -aq)", username=username, check=False)
    
    print("Pruning Docker volumes...")
    run_ssh_command(host, "docker volume prune -af", username=username, check=False)
    
    print("Uninstalling Docker...")
    # Detect package manager and uninstall Docker
    if sudo_password:
        # Escape password for shell
        escaped_password = sudo_password.replace("'", "'\\''")
        uninstall_cmd = (
            "if command -v apt-get > /dev/null 2>&1; then "
            f"printf '%s\\n' '{escaped_password}' | sudo -S apt-get remove -y docker docker-engine docker.io containerd runc docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>/dev/null || true; "
            "elif command -v yum > /dev/null 2>&1; then "
            f"printf '%s\\n' '{escaped_password}' | sudo -S yum remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>/dev/null || true; "
            "elif command -v dnf > /dev/null 2>&1; then "
            f"printf '%s\\n' '{escaped_password}' | sudo -S dnf remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>/dev/null || true; "
            "fi"
        )
    else:
        uninstall_cmd = (
            "if command -v apt-get > /dev/null 2>&1; then "
            "sudo apt-get remove -y docker docker-engine docker.io containerd runc docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>/dev/null || true; "
            "elif command -v yum > /dev/null 2>&1; then "
            "sudo yum remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>/dev/null || true; "
            "elif command -v dnf > /dev/null 2>&1; then "
            "sudo dnf remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>/dev/null || true; "
            "fi"
        )
    run_ssh_command(host, uninstall_cmd, username=username, check=False)
    
    # Remove Docker data directories
    print("Removing Docker data directories...")
    run_sudo_command(host, "rm -rf /var/lib/docker /var/lib/containerd /etc/docker", username=username, sudo_password=sudo_password)
    
    print("Docker cleanup and uninstallation completed.")


def get_k3s_token(server_host="192.168.1.126", username="rkd", sudo_password=None):
    """Get the k3s node token from the server node."""
    print(f"Getting k3s token from {server_host}...")
    
    # Check if k3s is installed
    check_cmd = "systemctl is-active k3s 2>/dev/null || systemctl is-active k3s-agent 2>/dev/null || echo 'not-found'"
    stdout, stderr, returncode = run_ssh_command(server_host, check_cmd, username=username, check=False)
    
    if "not-found" in stdout and "active" not in stdout.lower():
        print(f"Warning: k3s does not appear to be running on {server_host}")
        print("Checking if k3s is installed...")
        check_installed = "which k3s 2>/dev/null || test -f /usr/local/bin/k3s || echo 'not-installed'"
        stdout2, stderr2, rc2 = run_ssh_command(server_host, check_installed, username=username, check=False)
        if "not-installed" in stdout2:
            print(f"Error: k3s is not installed on {server_host}")
            return None
    
    # Try to get token from the standard location (try without sudo first)
    token_cmd = "cat /var/lib/rancher/k3s/server/node-token 2>/dev/null || echo ''"
    token, stderr, returncode = run_ssh_command(server_host, token_cmd, username=username, check=False)
    
    # If that failed, try with sudo
    if not token or returncode != 0 or len(token.strip()) == 0:
        print("Token file not readable without sudo, trying with sudo...")
        # Check if passwordless sudo works
        has_sudo = check_passwordless_sudo(server_host, username=username)
        
        if has_sudo:
            token_cmd = "sudo cat /var/lib/rancher/k3s/server/node-token 2>/dev/null || echo ''"
            token, stderr, returncode = run_ssh_command(server_host, token_cmd, username=username, check=False)
        elif sudo_password:
            # Try with provided password
            token_cmd = "cat /var/lib/rancher/k3s/server/node-token"
            token, stderr, returncode = run_sudo_command(server_host, token_cmd, username=username, sudo_password=sudo_password)
        else:
            print("Cannot read token file - requires sudo but no password provided.")
            print("Trying alternative method: checking if token is in k3s config...")
            # Try alternative: get token from k3s kubectl if available
            token_cmd = "sudo cat /var/lib/rancher/k3s/server/node-token 2>/dev/null || sudo cat /var/lib/rancher/k3s/server/token 2>/dev/null || echo ''"
            token, stderr, returncode = run_ssh_command(server_host, token_cmd, username=username, check=False)
    
    # Validate token (k3s tokens are typically long alphanumeric strings)
    token = token.strip() if token else ""
    if not token or len(token) < 20:
        print(f"Warning: Could not get valid token from {server_host}")
        print(f"STDERR: {stderr}")
        print("\nTroubleshooting:")
        print(f"1. SSH to {server_host} and run: sudo cat /var/lib/rancher/k3s/server/node-token")
        print("2. Make sure k3s is installed and running on the server node")
        print("3. Check if the token file exists and is readable")
        return None
    
    print("Successfully retrieved k3s token.")
    return token


def install_k3s_worker(host, server_host, token, username="root", sudo_password=None):
    """Install k3s as a worker node."""
    print(f"Installing k3s as worker node on {host}...")
    
    install_cmd = (
        f"curl -sfL https://get.k3s.io | "
        f"K3S_URL=https://{server_host}:6443 "
        f"K3S_TOKEN={token} sh -"
    )
    
    # Print the command that will be executed
    print(f"\nInstallation command:")
    print(f"  {install_cmd}\n")
    
    # Run with sudo - wrap in bash -c to handle pipes and env vars properly
    if sudo_password:
        escaped_password = sudo_password.replace("'", "'\\''")
        # Escape the install_cmd for bash -c
        escaped_cmd = install_cmd.replace("'", "'\\''")
        sudo_cmd = f"printf '%s\\n' '{escaped_password}' | sudo -S bash -c '{escaped_cmd}'"
    else:
        # Use bash -c to properly handle pipes and environment variables
        escaped_cmd = install_cmd.replace("'", "'\\''")
        sudo_cmd = f"sudo bash -c '{escaped_cmd}'"
    
    stdout, stderr, returncode = run_ssh_command(host, sudo_cmd, username=username, check=False)
    
    if returncode != 0:
        print(f"Error installing k3s worker")
        return False
    
    print("k3s worker installation completed.")
    return True


def install_k3s_control_plane(host, server_host, token, username="root", sudo_password=None):
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
    
    # Print the command that will be executed
    print(f"\nInstallation command:")
    print(f"  {install_cmd}\n")
    
    # Run with sudo - wrap in bash -c to handle pipes and env vars properly
    if sudo_password:
        escaped_password = sudo_password.replace("'", "'\\''")
        # Escape the install_cmd for bash -c
        escaped_cmd = install_cmd.replace("'", "'\\''")
        sudo_cmd = f"printf '%s\\n' '{escaped_password}' | sudo -S bash -c '{escaped_cmd}'"
    else:
        # Use bash -c to properly handle pipes and environment variables
        escaped_cmd = install_cmd.replace("'", "'\\''")
        sudo_cmd = f"sudo bash -c '{escaped_cmd}'"
    
    stdout, stderr, returncode = run_ssh_command(host, sudo_cmd, username=username, check=False)
    
    if returncode != 0:
        print(f"Error installing k3s control plane")
        return False
    
    print("k3s control plane installation completed.")
    return True


def main():
    # Ask for IP suffix
    suffix = input("Enter IP suffix (e.g., 122, 123): ").strip()
    if not suffix:
        print("Error: IP suffix is required.")
        sys.exit(1)
    
    # Ask for SSH username for target (default to rkd)
    target_username = input("Enter SSH username for target node [rkd]: ").strip()
    if not target_username:
        target_username = "rkd"
    
    # Ask for primary node suffix (default to 126)
    primary_suffix = input("Enter primary node IP suffix [126]: ").strip()
    if not primary_suffix:
        primary_suffix = "126"
    
    # Construct full IPs
    target_ip = f"192.168.1.{suffix}"
    server_ip = f"192.168.1.{primary_suffix}"
    server_username = "rkd"  # Always use rkd for primary node
    
    print(f"\nTarget node: {target_username}@{target_ip}")
    print(f"Server node: {server_username}@{server_ip}\n")
    
    # Test SSH connection
    print(f"Testing SSH connection to {target_ip}...")
    stdout, stderr, returncode = run_ssh_command(target_ip, "echo 'SSH connection successful'", username=target_username, check=False)
    if returncode != 0:
        print(f"Error: Cannot connect to {target_ip} via SSH")
        print("Make sure SSH keys are set up and the host is reachable.")
        sys.exit(1)
    
    print("SSH connection successful!\n")
    
    # Check if passwordless sudo works
    print("Checking if passwordless sudo is available...")
    has_passwordless_sudo = check_passwordless_sudo(target_ip, username=target_username)
    sudo_password = None
    
    if not has_passwordless_sudo:
        print("Passwordless sudo is not available.")
        response = input("Do you want to provide a sudo password? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            sudo_password = getpass.getpass(f"Enter sudo password for {target_username}@{target_ip}: ")
            # Test the password
            print("Testing sudo password...")
            test_stdout, test_stderr, test_rc = run_sudo_command(
                target_ip, 
                "echo 'Sudo password works'", 
                username=target_username, 
                sudo_password=sudo_password
            )
            if test_rc != 0:
                print("Error: Sudo password test failed. Please check your password.")
                sys.exit(1)
            print("Sudo password verified.\n")
        else:
            print("Warning: Sudo commands may fail if password is required.\n")
    else:
        print("Passwordless sudo is available.\n")
    
    # Check for Docker
    if check_docker(target_ip, username=target_username):
        print("Docker is installed and running.")
        containers = get_docker_containers(target_ip, username=target_username)
        if containers:
            print("\nRunning Docker containers:")
            print(containers)
            print()
        
        response = input("Do you want to terminate and clean up all Docker containers and volumes? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            cleanup_docker(target_ip, username=target_username, sudo_password=sudo_password)
        else:
            print("Skipping Docker cleanup.")
        print()
    else:
        print("Docker is not installed or not running.\n")
    
    # Check sudo for server node (needed for token retrieval)
    print(f"Checking sudo access for server node {server_ip}...")
    server_has_sudo = check_passwordless_sudo(server_ip, username=server_username)
    server_sudo_password = None
    
    if not server_has_sudo:
        print("Passwordless sudo is not available on server node.")
        response = input("Do you want to provide a sudo password for the server node? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            server_sudo_password = getpass.getpass(f"Enter sudo password for {server_username}@{server_ip}: ")
            # Test the password
            print("Testing sudo password for server node...")
            test_stdout, test_stderr, test_rc = run_sudo_command(
                server_ip, 
                "echo 'Sudo password works'", 
                username=server_username, 
                sudo_password=server_sudo_password
            )
            if test_rc != 0:
                print("Error: Sudo password test failed for server node. Please check your password.")
                sys.exit(1)
            print("Server sudo password verified.\n")
        else:
            print("Warning: May not be able to retrieve token if sudo is required.\n")
    else:
        print("Passwordless sudo is available on server node.\n")
    
    # Get k3s token from server
    token = get_k3s_token(server_ip, username=server_username, sudo_password=server_sudo_password)
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
        success = install_k3s_worker(target_ip, server_ip, token, username=target_username, sudo_password=sudo_password)
    elif node_type == "2":
        success = install_k3s_control_plane(target_ip, server_ip, token, username=target_username, sudo_password=sudo_password)
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

