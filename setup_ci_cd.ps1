# CI/CD Setup Script - Windows PowerShell Version
# Customized for your VM configuration
# VM: 95.217.56.35:2202

$ErrorActionPreference = "Stop"

$VM_HOST = "95.217.56.35"
$VM_PORT = "2202"
$VM_USER = "root"
$SSH_KEY = "$HOME\.ssh\dograh-deploy"

Write-Host "=================================" -ForegroundColor Blue
Write-Host "CI/CD Pipeline Setup" -ForegroundColor Blue
Write-Host "=================================" -ForegroundColor Blue
Write-Host ""
Write-Host "VM Host: $VM_HOST"
Write-Host "VM Port: $VM_PORT"
Write-Host "VM User: $VM_USER"
Write-Host ""

# Step 1: Check if SSH key exists
Write-Host "[Step 1/4] Checking SSH key..." -ForegroundColor Blue
if (Test-Path $SSH_KEY) {
    Write-Host "✓ SSH key already exists at $SSH_KEY" -ForegroundColor Green
} else {
    Write-Host "⚠ SSH key not found. Generating new key..." -ForegroundColor Yellow
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f $SSH_KEY -N '""'
    Write-Host "✓ SSH key generated" -ForegroundColor Green
}
Write-Host ""

# Step 2: Copy public key to VM
Write-Host "[Step 2/4] Adding public key to VM..." -ForegroundColor Blue
Write-Host "This will prompt for your VM password..."
try {
    $publicKey = Get-Content "$SSH_KEY.pub"
    Write-Host "Attempting to copy SSH key to VM..."

    # Try ssh-copy-id if available (Git Bash on Windows)
    $result = ssh-copy-id -i "$SSH_KEY.pub" -p $VM_PORT "${VM_USER}@${VM_HOST}" 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Public key added to VM" -ForegroundColor Green
    } else {
        throw "ssh-copy-id failed"
    }
} catch {
    Write-Host "✗ Automatic key copy not available" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please add the key manually:" -ForegroundColor Yellow
    Write-Host "1. Copy this public key:" -ForegroundColor Yellow
    Write-Host ""
    Get-Content "$SSH_KEY.pub"
    Write-Host ""
    Write-Host "2. SSH to VM: ssh -p $VM_PORT $VM_USER@$VM_HOST"
    Write-Host "3. Run: mkdir -p ~/.ssh && chmod 700 ~/.ssh"
    Write-Host "4. Run: nano ~/.ssh/authorized_keys"
    Write-Host "5. Paste the public key, save and exit (Ctrl+X, Y, Enter)"
    Write-Host "6. Run: chmod 600 ~/.ssh/authorized_keys"
    Write-Host "7. Exit and re-run this script"
    Write-Host ""
    Write-Host "Then test connection with:"
    Write-Host "ssh -i $SSH_KEY -p $VM_PORT ${VM_USER}@${VM_HOST}"
    exit 1
}
Write-Host ""

# Step 3: Test SSH connection
Write-Host "[Step 3/4] Testing SSH connection..." -ForegroundColor Blue
try {
    $testResult = ssh -i $SSH_KEY -p $VM_PORT -o BatchMode=yes -o ConnectTimeout=5 "${VM_USER}@${VM_HOST}" "echo 'SSH key works!'" 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ SSH connection successful (no password needed)" -ForegroundColor Green
    } else {
        throw "SSH test failed"
    }
} catch {
    Write-Host "✗ SSH connection failed" -ForegroundColor Red
    Write-Host "Please check:"
    Write-Host "  - Public key was added correctly to VM"
    Write-Host "  - SSH service is running on VM"
    Write-Host "  - Firewall allows connections on port $VM_PORT"
    exit 1
}
Write-Host ""

# Step 4: Display GitHub Secrets
Write-Host "[Step 4/4] GitHub Secrets Configuration" -ForegroundColor Blue
Write-Host ""
Write-Host "Add these secrets to GitHub:"
Write-Host "Settings → Secrets and variables → Actions → New repository secret"
Write-Host ""
Write-Host "Secret 1: DEBIAN_VM_SSH_KEY" -ForegroundColor Yellow
Write-Host "Copy the ENTIRE private key below (including BEGIN/END lines):"
Write-Host ""
Write-Host "------- START OF PRIVATE KEY -------"
Get-Content $SSH_KEY
Write-Host "------- END OF PRIVATE KEY -------"
Write-Host ""
Write-Host "Secret 2: DEBIAN_VM_HOST" -ForegroundColor Yellow
Write-Host "Value: $VM_HOST"
Write-Host ""
Write-Host "Secret 3: DEBIAN_VM_USER" -ForegroundColor Yellow
Write-Host "Value: $VM_USER"
Write-Host ""
Write-Host "Secret 4: DEBIAN_VM_PORT" -ForegroundColor Yellow
Write-Host "Value: $VM_PORT"
Write-Host ""
Write-Host "=================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Add the 4 secrets to GitHub (shown above)"
Write-Host "2. Go to Actions → Deploy to Debian VM → Run workflow"
Write-Host "3. Watch your first deployment!"
Write-Host ""
Write-Host "Repository URL:"
Write-Host "https://github.com/YOUR_USERNAME/dograh/settings/secrets/actions"
Write-Host ""
