# CI/CD Pipeline Setup Guide

This guide walks you through setting up automatic deployments to your Debian VM using GitHub Actions.

## Quick Overview

The CI/CD pipeline automatically deploys your Dograh application to the production VM whenever:
1. Code is pushed to the `main` branch
2. API tests pass successfully
3. API or Docker-related files have changed

**Deployment method**: Zero-downtime rolling updates using the existing `rolling_update.sh` script.

## Files Created

- `.github/workflows/deploy-to-vm.yml` - Main GitHub Actions workflow
- `scripts/ci_deploy.sh` - Deployment execution script (runs on VM)
- `scripts/healthcheck.sh` - Post-deployment health verification

## Files Modified

- `.github/workflows/api-tests.yml` - Updated to run on push to main (enables automatic deployment)

## Prerequisites

Before setting up the CI/CD pipeline, ensure:

1. ✅ You have SSH access to your Debian VM
2. ✅ The application is already deployed at `/root/dograh-live/dograh`
3. ✅ The `rolling_update.sh` script works when run manually
4. ✅ You have admin access to your GitHub repository

## Step 1: Generate SSH Key for GitHub Actions

On your **local machine**, create a dedicated SSH key for GitHub Actions:

```bash
# Generate SSH key (no passphrase)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/dograh-deploy -N ""

# This creates two files:
# - ~/.ssh/dograh-deploy (private key - for GitHub Secrets)
# - ~/.ssh/dograh-deploy.pub (public key - for VM)
```

## Step 2: Add Public Key to VM

Copy the public key to your Debian VM to allow GitHub Actions to connect:

### Option A: Using ssh-copy-id (Recommended)

```bash
ssh-copy-id -i ~/.ssh/dograh-deploy.pub root@YOUR_VM_IP
```

Replace `YOUR_VM_IP` with your actual VM IP address or hostname.

### Option B: Manual Method

If `ssh-copy-id` doesn't work:

```bash
# Display the public key
cat ~/.ssh/dograh-deploy.pub

# SSH to your VM
ssh root@YOUR_VM_IP

# Add the public key to authorized_keys
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "YOUR_PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

### Test SSH Connection

Verify the key works:

```bash
ssh -i ~/.ssh/dograh-deploy root@YOUR_VM_IP "echo 'SSH key works!'"
```

You should see "SSH key works!" without being prompted for a password.

## Step 3: Add Secrets to GitHub

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:

### DEBIAN_VM_SSH_KEY

```bash
# Copy the ENTIRE contents of the private key
cat ~/.ssh/dograh-deploy
```

- Click **New repository secret**
- Name: `DEBIAN_VM_SSH_KEY`
- Value: Paste the entire private key (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)
- Click **Add secret**

### DEBIAN_VM_HOST

- Name: `DEBIAN_VM_HOST`
- Value: Your VM's IP address or hostname (e.g., `203.0.113.42` or `vm.example.com`)
- Click **Add secret**

### DEBIAN_VM_USER

- Name: `DEBIAN_VM_USER`
- Value: `root` (or your SSH username if different)
- Click **Add secret**

### DEBIAN_VM_PORT

- Name: `DEBIAN_VM_PORT`
- Value: `2202` (⚠️ **Your VM uses port 2202, not the default 22**)
- Click **Add secret**

## Step 4: Verify GitHub Secrets

After adding all secrets, you should see:

- ✅ DEBIAN_VM_HOST
- ✅ DEBIAN_VM_PORT
- ✅ DEBIAN_VM_SSH_KEY
- ✅ DEBIAN_VM_USER

## Step 5: Test Manual Deployment

Before automatic deployments, test the workflow manually:

1. Go to your GitHub repository
2. Click **Actions** tab
3. Select **Deploy to Debian VM** workflow
4. Click **Run workflow** dropdown
5. Leave "Commit SHA" empty (deploys latest)
6. Click **Run workflow**

Watch the deployment logs to ensure everything works correctly.

## Step 6: Enable Automatic Deployments

Once manual deployment works, automatic deployments are already enabled! They will trigger when:

1. You push code to `main` branch
2. The push includes changes to:
   - `api/` directory
   - `docker-compose.yaml` or `Dockerfile`
   - `scripts/rolling_update.sh`
   - `.github/workflows/` directory
3. API tests pass successfully

## How It Works

### Deployment Flow

```
1. Push to main branch
   ↓
2. API tests run (api-tests.yml)
   ↓ (only if tests pass)
3. Deploy workflow triggers (deploy-to-vm.yml)
   ↓
4. Check if deployment needed (did API files change?)
   ↓ (if yes)
5. SSH to VM and run ci_deploy.sh
   ├─ git pull origin main
   ├─ git submodule update
   └─ ./scripts/rolling_update.sh
       ├─ Run database migrations
       ├─ Start new workers (alternate band)
       ├─ Health check new workers
       ├─ Switch nginx to new workers
       ├─ Drain old workers (300s timeout)
       └─ Restart supporting services
   ↓
6. Run healthcheck.sh
   ├─ Check /api/v1/health endpoint
   ├─ Verify worker processes
   └─ Check Docker containers
   ↓
7. Report success/failure
```

### Zero-Downtime Strategy

The deployment uses a **dual-band** approach:

- **Band A**: Workers on ports 8100-8103
- **Band B**: Workers on ports 8104-8107

When deploying:
1. New workers start on the **inactive band**
2. Health checks ensure they're working
3. Nginx switches to the new band
4. Old workers drain gracefully (WebSockets complete)
5. Old workers are shut down

If health checks fail, the deployment **automatically rolls back**.

## Monitoring Deployments

### View Deployment Status

1. Go to **Actions** tab in GitHub
2. Look for **Deploy to Debian VM** workflow runs
3. Green checkmark ✅ = successful deployment
4. Red X ❌ = failed deployment (automatic rollback)

### View Deployment Logs on VM

```bash
# SSH to your VM
ssh root@YOUR_VM_IP

# View latest deployment log
cd /root/dograh-live/dograh
tail -f logs/deployment/latest.log

# View all deployment logs
ls -lt logs/deployment/
```

### Check Application Health

```bash
# Health endpoint
curl -k https://YOUR_VM_IP/api/v1/health

# Worker status
cd /root/dograh-live/dograh
cat run/active_band
ls -la run/*.pid

# Container status
docker compose ps
```

## Troubleshooting

### Issue: "SSH Connection Failed"

**Symptoms**: Workflow fails with "Permission denied" or "Connection refused"

**Solutions**:
1. Verify SSH key is correct:
   ```bash
   ssh -i ~/.ssh/dograh-deploy root@YOUR_VM_IP
   ```
2. Check public key is in VM's authorized_keys:
   ```bash
   ssh root@YOUR_VM_IP "cat ~/.ssh/authorized_keys | grep github-actions"
   ```
3. Verify `DEBIAN_VM_SSH_KEY` secret contains the **private** key (not public)
4. Check `DEBIAN_VM_HOST` and `DEBIAN_VM_PORT` are correct

### Issue: "Health Check Timeout"

**Symptoms**: Deployment succeeds but verification fails

**Solutions**:
1. SSH to VM and check logs:
   ```bash
   tail -f /root/dograh-live/dograh/logs/latest/*.log
   ```
2. Check if workers are running:
   ```bash
   cd /root/dograh-live/dograh
   ls -la run/*.pid
   cat run/active_band
   ```
3. Test health endpoint manually:
   ```bash
   curl -k https://localhost/api/v1/health
   ```
4. Check nginx configuration:
   ```bash
   sudo nginx -t
   sudo systemctl status nginx
   ```

### Issue: "Rolling Update Failed"

**Symptoms**: New workers fail to start or pass health checks

**Solutions**:
1. Check worker logs on VM:
   ```bash
   cd /root/dograh-live/dograh
   tail -f logs/latest/worker_*.log
   ```
2. Verify database migrations succeeded:
   ```bash
   docker exec -it dograh-api-1 alembic current
   ```
3. Check if ports are already in use:
   ```bash
   ss -tln | grep "810[0-7]"
   ```
4. Review environment variables:
   ```bash
   cat /root/dograh-live/dograh/.env
   ```

### Issue: "Tests Pass But Deployment Skipped"

**Symptoms**: Tests succeed but "No deployment needed" message appears

**Explanation**: Deployment only triggers when API or Docker files change. UI-only changes don't require redeployment.

**If you need to deploy anyway**:
1. Go to **Actions** tab
2. Select **Deploy to Debian VM**
3. Click **Run workflow**
4. Deploy manually

### Issue: "Deployment Stuck"

**Symptoms**: Deployment runs for a long time without completing

**Solutions**:
1. Check if old workers are still draining (5 minute timeout):
   ```bash
   ps aux | grep uvicorn
   ```
2. View active connections:
   ```bash
   ss -an | grep ":810[0-7]" | wc -l
   ```
3. If truly stuck, manually kill old workers:
   ```bash
   cd /root/dograh-live/dograh
   # Read the PID files and kill processes
   for pid_file in run/worker_*.pid; do
     if [ -f "$pid_file" ]; then
       kill $(cat "$pid_file") || true
     fi
   done
   ```

## Manual Rollback

If you need to rollback to a previous version:

### Option 1: Deploy Previous Commit via GitHub

1. Go to **Actions** tab
2. Select **Deploy to Debian VM**
3. Click **Run workflow**
4. Enter the commit SHA you want to deploy
5. Click **Run workflow**

### Option 2: Manual Rollback on VM

```bash
# SSH to VM
ssh root@YOUR_VM_IP

# Navigate to deployment directory
cd /root/dograh-live/dograh

# Find previous commit
git log --oneline -10

# Checkout previous commit
git checkout <PREVIOUS_COMMIT_SHA>

# Update submodules
git submodule update --init --recursive

# Run rolling update
./scripts/rolling_update.sh

# Verify deployment
./scripts/healthcheck.sh
```

### Option 3: Revert Commit and Deploy

```bash
# On your local machine
cd dograh

# Revert the problematic commit
git revert <BAD_COMMIT_SHA>

# Push to main (triggers automatic deployment)
git push origin main
```

## Security Best Practices

### SSH Key Management

1. ✅ Use a **dedicated SSH key** for GitHub Actions (don't reuse personal keys)
2. ✅ Store private key **only** in GitHub Secrets (never commit to repo)
3. ✅ Add public key **only** to deployment VM (not to personal machines)
4. ✅ Consider **rotating keys** every 90 days
5. ✅ If key is compromised:
   ```bash
   # Remove from VM
   ssh root@YOUR_VM_IP
   nano ~/.ssh/authorized_keys  # Delete the github-actions key

   # Generate new key and update GitHub Secret
   ssh-keygen -t ed25519 -C "github-actions-deploy-new" -f ~/.ssh/dograh-deploy-new -N ""
   ssh-copy-id -i ~/.ssh/dograh-deploy-new.pub root@YOUR_VM_IP
   # Update DEBIAN_VM_SSH_KEY secret in GitHub
   ```

### VM Firewall

Ensure your VM firewall allows SSH from GitHub Actions:

```bash
# GitHub Actions uses dynamic IPs from GitHub's IP ranges
# You can restrict to GitHub's published IP ranges, but they change frequently
# Recommended: Use fail2ban for SSH brute force protection

# Install fail2ban (if not already installed)
sudo apt install fail2ban -y

# Enable fail2ban for SSH
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Secret Protection

- Secrets are **encrypted** in GitHub
- Secrets are **masked** in workflow logs
- Secrets are **never** displayed in the UI
- Only repository admins can view/edit secrets

## Advanced Configuration

### Adjust Health Check Timeout

Edit `scripts/healthcheck.sh`:

```bash
# Increase max attempts (default: 30 attempts × 2s = 60s total)
MAX_ATTEMPTS=60  # Change from 30 to 60 for 2 minute timeout
```

### Adjust Worker Drain Timeout

Edit `scripts/rolling_update.sh`:

```bash
# Find the drain timeout section (around line 200-250)
DRAIN_TIMEOUT=600  # Change from 300 to 600 for 10 minute drain
```

### Deploy Only Specific File Changes

Edit `.github/workflows/deploy-to-vm.yml`:

```yaml
# Adjust the file pattern check (around line 26)
if echo "$CHANGED_FILES" | grep -qE '^(api/|docker-compose|Dockerfile|YOUR_NEW_PATTERN)'; then
```

### Add Deployment Notifications

To receive Slack notifications on deployment status, add to `.github/workflows/deploy-to-vm.yml`:

```yaml
- name: Send Slack notification - Success
  if: success()
  uses: slackapi/slack-github-action@v1.26.0
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
  with:
    payload: |
      {
        "text": "✅ Dograh deployed successfully to production - <${{ github.server_url }}/${{ github.repository }}/commit/${{ github.sha }}|View Commit>"
      }

- name: Send Slack notification - Failure
  if: failure()
  uses: slackapi/slack-github-action@v1.26.0
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
  with:
    payload: |
      {
        "text": "❌ Dograh deployment failed - <${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}|View Logs>"
      }
```

Then add `SLACK_WEBHOOK_URL` to GitHub Secrets.

## Testing the Pipeline

### Test Checklist

Before relying on automatic deployments, verify:

- [ ] Manual workflow dispatch works
- [ ] Health checks pass after deployment
- [ ] Application is accessible after deployment
- [ ] Database migrations run correctly
- [ ] No errors in deployment logs
- [ ] Rollback works (test by deploying a previous commit)
- [ ] Automatic deployment triggers on push to main

### Perform a Test Deployment

1. Make a trivial change to the API (e.g., add a comment)
2. Commit and push to main:
   ```bash
   git add api/app.py
   git commit -m "test: trigger deployment"
   git push origin main
   ```
3. Watch the deployment in GitHub Actions
4. Verify the application works after deployment
5. Check logs on the VM for any issues

## Maintenance

### Regular Tasks

- **Monthly**: Review deployment logs for patterns/issues
- **Quarterly**: Rotate SSH keys (generate new key, update secret)
- **As needed**: Adjust health check timeouts if deployments timeout
- **After major changes**: Test manual rollback procedure

### Monitoring Recommendations

Consider setting up:
1. **Uptime monitoring**: External service to ping `/api/v1/health`
2. **Log aggregation**: Send logs to centralized logging (e.g., Loki, CloudWatch)
3. **Metrics**: Track deployment frequency, duration, success rate
4. **Alerts**: Notify on repeated deployment failures

## Success Metrics

Your CI/CD pipeline is working well when:

- ✅ Deployments complete in < 10 minutes
- ✅ Success rate > 95%
- ✅ Zero downtime during deployments
- ✅ Automatic rollback works when needed
- ✅ No manual intervention required for normal deployments

## Getting Help

If you encounter issues not covered in this guide:

1. Check deployment logs on VM: `/root/dograh-live/dograh/logs/deployment/`
2. Review GitHub Actions logs for the failed workflow
3. Test rolling_update.sh manually on the VM
4. Verify all GitHub Secrets are correct
5. Check VM system resources (disk space, memory)

## Next Steps

After successful setup:

1. ✅ Document your deployment schedule (if any)
2. ✅ Share this guide with team members
3. ✅ Set up monitoring/alerting (optional)
4. ✅ Test rollback procedure
5. ✅ Consider staging environment (optional)

---

**Congratulations!** Your CI/CD pipeline is now set up for automatic, zero-downtime deployments. 🎉
