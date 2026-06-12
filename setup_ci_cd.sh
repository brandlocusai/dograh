#!/bin/bash
#
# CI/CD Setup Script - Customized for your VM configuration
# VM: 95.217.56.35:2202
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VM_HOST="95.217.56.35"
VM_PORT="2202"
VM_USER="root"
SSH_KEY="$HOME/.ssh/dograh-deploy"

echo -e "${BLUE}=================================${NC}"
echo -e "${BLUE}CI/CD Pipeline Setup${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""
echo "VM Host: $VM_HOST"
echo "VM Port: $VM_PORT"
echo "VM User: $VM_USER"
echo ""

# Step 1: Check if SSH key exists
echo -e "${BLUE}[Step 1/4] Checking SSH key...${NC}"
if [ -f "$SSH_KEY" ]; then
    echo -e "${GREEN}✓ SSH key already exists at $SSH_KEY${NC}"
else
    echo -e "${YELLOW}⚠ SSH key not found. Generating new key...${NC}"
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f "$SSH_KEY" -N ""
    echo -e "${GREEN}✓ SSH key generated${NC}"
fi
echo ""

# Step 2: Copy public key to VM
echo -e "${BLUE}[Step 2/4] Adding public key to VM...${NC}"
echo "This will prompt for your VM password..."
if ssh-copy-id -i "${SSH_KEY}.pub" -p "$VM_PORT" "${VM_USER}@${VM_HOST}" 2>/dev/null; then
    echo -e "${GREEN}✓ Public key added to VM${NC}"
else
    echo -e "${RED}✗ Failed to add public key automatically${NC}"
    echo ""
    echo "Please add the key manually:"
    echo "1. Copy this public key:"
    echo ""
    cat "${SSH_KEY}.pub"
    echo ""
    echo "2. SSH to VM: ssh -p $VM_PORT $VM_USER@$VM_HOST"
    echo "3. Run: mkdir -p ~/.ssh && chmod 700 ~/.ssh"
    echo "4. Run: nano ~/.ssh/authorized_keys"
    echo "5. Paste the public key, save and exit"
    echo "6. Run: chmod 600 ~/.ssh/authorized_keys"
    echo "7. Exit and re-run this script"
    exit 1
fi
echo ""

# Step 3: Test SSH connection
echo -e "${BLUE}[Step 3/4] Testing SSH connection...${NC}"
if ssh -i "$SSH_KEY" -p "$VM_PORT" -o BatchMode=yes -o ConnectTimeout=5 "${VM_USER}@${VM_HOST}" "echo 'SSH key works!'" 2>/dev/null; then
    echo -e "${GREEN}✓ SSH connection successful (no password needed)${NC}"
else
    echo -e "${RED}✗ SSH connection failed${NC}"
    echo "Please check:"
    echo "  - Public key was added correctly to VM"
    echo "  - SSH service is running on VM"
    echo "  - Firewall allows connections on port $VM_PORT"
    exit 1
fi
echo ""

# Step 4: Display GitHub Secrets
echo -e "${BLUE}[Step 4/4] GitHub Secrets Configuration${NC}"
echo ""
echo "Add these secrets to GitHub:"
echo "Settings → Secrets and variables → Actions → New repository secret"
echo ""
echo -e "${YELLOW}Secret 1: DEBIAN_VM_SSH_KEY${NC}"
echo "Copy the ENTIRE private key below (including BEGIN/END lines):"
echo ""
echo "------- START OF PRIVATE KEY -------"
cat "$SSH_KEY"
echo "------- END OF PRIVATE KEY -------"
echo ""
echo -e "${YELLOW}Secret 2: DEBIAN_VM_HOST${NC}"
echo "Value: $VM_HOST"
echo ""
echo -e "${YELLOW}Secret 3: DEBIAN_VM_USER${NC}"
echo "Value: $VM_USER"
echo ""
echo -e "${YELLOW}Secret 4: DEBIAN_VM_PORT${NC}"
echo "Value: $VM_PORT"
echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
echo "Next steps:"
echo "1. Add the 4 secrets to GitHub (shown above)"
echo "2. Go to Actions → Deploy to Debian VM → Run workflow"
echo "3. Watch your first deployment!"
echo ""
echo "Repository URL:"
echo "https://github.com/YOUR_USERNAME/dograh/settings/secrets/actions"
echo ""
