#!/bin/bash
# Script to install Longhorn requirements on all Kubernetes nodes
# This script should be run on each node

set -e

echo "Installing Longhorn requirements..."

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "Cannot detect OS. Please install open-iscsi manually."
    exit 1
fi

# Install open-iscsi based on OS
case $OS in
    ubuntu|debian)
        echo "Detected Ubuntu/Debian. Installing open-iscsi..."
        sudo apt-get update
        sudo apt-get install -y open-iscsi
        ;;
    rhel|centos|fedora|rocky|almalinux)
        echo "Detected RHEL/CentOS/Fedora. Installing iscsi-initiator-utils..."
        if command -v dnf &> /dev/null; then
            sudo dnf install -y iscsi-initiator-utils
        else
            sudo yum install -y iscsi-initiator-utils
        fi
        # Generate initiator name if not exists
        if [ ! -f /etc/iscsi/initiatorname.iscsi ]; then
            echo "InitiatorName=$(sudo /sbin/iscsi-iname)" | sudo tee /etc/iscsi/initiatorname.iscsi
        fi
        ;;
    opensuse*|sles)
        echo "Detected openSUSE/SLES. Installing open-iscsi..."
        sudo zypper install -y open-iscsi
        ;;
    arch|manjaro|endeavouros)
        echo "Detected Arch Linux/EndeavourOS. Installing open-iscsi..."
        sudo pacman -S --noconfirm open-iscsi
        ;;
    *)
        echo "Unsupported OS: $OS"
        echo "Please install open-iscsi manually for your distribution."
        exit 1
        ;;
esac

# Check and load iscsi_tcp module
echo "Checking for iscsi_tcp kernel module..."
KERNEL_VERSION=$(uname -r)
MODULE_PATH="/lib/modules/${KERNEL_VERSION}/kernel/drivers/scsi/iscsi_tcp.ko"

if [ -f "$MODULE_PATH" ]; then
    echo "Found iscsi_tcp module, attempting to load..."
    sudo modprobe iscsi_tcp && echo "✓ iscsi_tcp module loaded" || echo "⚠ Could not load iscsi_tcp (may already be loaded or built-in)"
elif lsmod | grep -q "^iscsi_tcp"; then
    echo "✓ iscsi_tcp module is already loaded"
else
    echo "⚠ iscsi_tcp module not found in /lib/modules/${KERNEL_VERSION}/"
    echo "  This may be OK if the kernel has iSCSI support built-in."
    echo "  Checking if kernel has iSCSI support..."
    if [ -d /sys/module/libiscsi ] || [ -d /sys/module/iscsi_tcp ]; then
        echo "  ✓ Kernel appears to have iSCSI support (built-in or already loaded)"
    else
        echo "  ⚠ Kernel may not have iSCSI support. Longhorn may not work properly."
        echo "  Consider updating the kernel or using a kernel with iSCSI support."
    fi
fi

# Enable and start iscsid service
echo ""
echo "Configuring iscsid service..."
if command -v systemctl &> /dev/null; then
    # Check if iscsid service exists
    if systemctl list-unit-files | grep -q iscsid.service; then
        # Check for initiator name
        if [ ! -f /etc/iscsi/initiatorname.iscsi ] || [ ! -s /etc/iscsi/initiatorname.iscsi ]; then
            echo "Generating initiator name..."
            INITIATOR_NAME=$(sudo /usr/sbin/iscsi-iname 2>/dev/null || echo "iqn.$(date +%Y-%m).$(hostname):$(openssl rand -hex 4)")
            echo "InitiatorName=${INITIATOR_NAME}" | sudo tee /etc/iscsi/initiatorname.iscsi
        fi
        
        echo "Enabling iscsid service..."
        sudo systemctl enable iscsid || echo "⚠ Could not enable iscsid (may already be enabled)"
        
        echo "Starting iscsid service..."
        if sudo systemctl start iscsid; then
            echo "✓ iscsid service started successfully"
            sudo systemctl status iscsid --no-pager -l || true
        else
            echo "✗ Failed to start iscsid service"
            echo "Checking logs..."
            sudo journalctl -u iscsid.service -n 20 --no-pager || true
            echo ""
            echo "NOTE: iscsid may not be strictly required if Longhorn can use alternative methods."
            echo "The iscsiadm command should still work for Longhorn."
        fi
    else
        echo "⚠ iscsid.service not found"
    fi
else
    echo "Warning: systemctl not found. Please enable and start iscsid manually."
fi

# Verify installation
echo ""
echo "Verifying installation..."
if command -v iscsiadm &> /dev/null; then
    echo "✓ iscsiadm is installed: $(which iscsiadm)"
    iscsiadm --version || true
else
    echo "✗ ERROR: iscsiadm not found after installation!"
    exit 1
fi

echo ""
echo "=========================================="
echo "Installation Summary:"
echo "=========================================="
if command -v iscsiadm &> /dev/null; then
    echo "✓ iscsiadm is installed: $(which iscsiadm)"
    iscsiadm --version || true
    echo ""
    echo "✓ Longhorn requirements installed successfully!"
    echo ""
    echo "NOTE: Even if iscsid service failed to start, Longhorn may still work"
    echo "      as long as iscsiadm is available and the kernel has iSCSI support."
else
    echo "✗ ERROR: iscsiadm not found after installation!"
    exit 1
fi

echo ""
echo "Next steps:"
echo "1. Verify iscsiadm works: sudo iscsiadm --version"
echo "2. (Optional) Check iscsid status: sudo systemctl status iscsid"
echo "3. Restart Longhorn manager pods: kubectl delete pods -n longhorn-system -l app=longhorn-manager"
echo ""
echo "If Longhorn manager still fails, check the pod logs:"
echo "  kubectl logs -n longhorn-system -l app=longhorn-manager"
