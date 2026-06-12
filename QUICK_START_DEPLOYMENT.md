# Quick Start: CI/CD Pipeline Setup

## 🚀 5-Minute Setup Guide

### Prerequisites
- ✅ Debian VM at `/root/dograh-live/dograh`
- ✅ SSH access to VM as root
- ✅ GitHub repository admin access

---

## Step 1: Generate SSH Key (2 minutes)

```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/dograh-deploy -N ""

# Add to VM (using port 2202)
ssh-copy-id -i ~/.ssh/dograh-deploy.pub -p 2202 root@95.217.56.35

# Test connection (should not ask for password)
ssh -i ~/.ssh/dograh-deploy -p 2202 root@95.217.56.35 "echo 'SSH works!'"
```

✅ If you see "SSH works!" without entering a password, proceed to Step 2.

---

## Step 2: Add GitHub Secrets (3 minutes)

1. Go to: `https://github.com/YOUR_USERNAME/dograh/settings/secrets/actions`
2. Click **"New repository secret"** (4 times)

### Secret 1: DEBIAN_VM_SSH_KEY
```bash
# Copy the private key
cat ~/.ssh/dograh-deploy
```
- Paste the **entire** private key (including BEGIN/END lines)

### Secret 2: DEBIAN_VM_HOST
- Value: Your VM's IP or hostname (e.g., `203.0.113.42`)

### Secret 3: DEBIAN_VM_USER
- Value: `root`

### Secret 4: DEBIAN_VM_PORT
- Value: `2202` (⚠️ **Your VM uses port 2202, not 22**)

✅ Verify all 4 secrets appear in the list.

---

## Step 3: Test Deployment (5 minutes)

1. Go to: `https://github.com/YOUR_USERNAME/dograh/actions`
2. Click **"Deploy to Debian VM"** workflow
3. Click **"Run workflow"** button (top right)
4. Leave "Commit SHA" empty
5. Click **"Run workflow"**
6. Watch the logs (deployment takes ~7-10 minutes)

✅ If you see "Deployment successful!" with green checkmarks, you're done!

---

## ✨ That's It!

Your CI/CD pipeline is now active. Future pushes to `main` will automatically deploy after tests pass.

---

## Quick Commands

### Verify Deployment on VM
```bash
ssh -p 2202 root@95.217.56.35

# Check health
curl -k https://localhost/api/v1/health

# View deployment log
tail -f /root/dograh-live/dograh/logs/deployment/latest.log

# Check active band
cat /root/dograh-live/dograh/run/active_band

# Check running workers
ls -la /root/dograh-live/dograh/run/*.pid
```

### Manual Rollback
```bash
# SSH to VM
ssh -p 2202 root@95.217.56.35
cd /root/dograh-live/dograh

# Find previous commit
git log --oneline -10

# Deploy previous version
git checkout <COMMIT_SHA>
git submodule update --init --recursive
./scripts/rolling_update.sh
./scripts/healthcheck.sh
```

### Trigger Manual Deployment
1. Go to **Actions** → **Deploy to Debian VM**
2. Click **Run workflow**
3. Enter commit SHA (or leave empty for latest)
4. Click **Run workflow**

---

## When Deployment Triggers

✅ **Automatic deployment** runs when:
- Code pushed to `main` branch
- API tests pass
- Files changed in: `api/`, `docker-compose.yaml`, `Dockerfile`, `scripts/rolling_update.sh`, `.github/workflows/`

⏭️ **Skipped** when:
- Only UI or docs files changed
- Tests failed
- Another deployment is in progress

---

## Troubleshooting

### ❌ "SSH Connection Failed"
```bash
# Test SSH manually (with port 2202)
ssh -i ~/.ssh/dograh-deploy -p 2202 root@95.217.56.35

# If fails, check public key on VM
ssh -p 2202 root@95.217.56.35 "cat ~/.ssh/authorized_keys | grep github-actions"
```

### ❌ "Health Check Timeout"
```bash
# SSH to VM and check logs
ssh -p 2202 root@95.217.56.35
tail -f /root/dograh-live/dograh/logs/latest/*.log
```

### ❌ "Tests Pass But No Deployment"
This is normal if only UI/docs files changed. To force deployment:
1. Go to **Actions** → **Deploy to Debian VM**
2. Click **Run workflow** → **Run workflow**

---

## 📚 Full Documentation

- **Comprehensive Setup**: [CI_CD_SETUP_GUIDE.md](CI_CD_SETUP_GUIDE.md)
- **Implementation Details**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

---

## Support Checklist

Before asking for help, verify:
- [ ] All 4 GitHub secrets are added correctly
- [ ] SSH key works when tested manually
- [ ] VM is accessible and running
- [ ] `/root/dograh-live/dograh` directory exists on VM
- [ ] `rolling_update.sh` works when run manually on VM

---

## Success Indicators

Your pipeline is working when you see:
- ✅ Green checkmarks in GitHub Actions
- ✅ "Deployment completed successfully" in logs
- ✅ Health checks pass
- ✅ Application accessible at your VM's IP/domain
- ✅ No errors in `/root/dograh-live/dograh/logs/latest/`

---

**Next Push to `main`**: Will automatically deploy! 🎉
