# CI/CD Pipeline Implementation Summary

## ✅ Implementation Complete

The CI/CD pipeline for automatic deployment to your Debian VM has been successfully implemented.

## Files Created

### 1. `.github/workflows/deploy-to-vm.yml`
**Purpose**: Main GitHub Actions workflow for automatic deployment

**Key Features**:
- ✅ Triggers after API tests pass on main branch
- ✅ Concurrency control (prevents overlapping deployments)
- ✅ Conditional execution (only when API/Docker files change)
- ✅ Manual workflow dispatch for emergency deploys
- ✅ SSH connection to VM with key-based authentication
- ✅ Post-deployment health verification
- ✅ Automatic rollback on failure

**Location**: `.github/workflows/deploy-to-vm.yml`

### 2. `scripts/ci_deploy.sh`
**Purpose**: Deployment execution script that runs on the VM

**Key Features**:
- ✅ Navigates to `/root/dograh-live/dograh`
- ✅ Fetches and resets to latest main branch
- ✅ Updates git submodules (pipecat)
- ✅ Executes `rolling_update.sh` for zero-downtime deployment
- ✅ Comprehensive logging with timestamps
- ✅ Error handling and exit codes
- ✅ Deployment log archival

**Location**: `scripts/ci_deploy.sh` (executable)

### 3. `scripts/healthcheck.sh`
**Purpose**: Post-deployment health verification

**Key Features**:
- ✅ Polls `/api/v1/health` endpoint (30 attempts, 2s interval)
- ✅ Verifies HTTP 200 response
- ✅ Checks worker process PIDs
- ✅ Validates Docker container status
- ✅ Scans logs for immediate errors
- ✅ Returns exit code 0 on success, 1 on failure

**Location**: `scripts/healthcheck.sh` (executable)

### 4. `CI_CD_SETUP_GUIDE.md`
**Purpose**: Comprehensive setup guide for operators

**Contents**:
- Step-by-step setup instructions
- SSH key generation and configuration
- GitHub Secrets setup
- Troubleshooting guide
- Manual rollback procedures
- Security best practices
- Monitoring recommendations

**Location**: `CI_CD_SETUP_GUIDE.md`

### 5. `IMPLEMENTATION_SUMMARY.md`
**Purpose**: This summary document

**Location**: `IMPLEMENTATION_SUMMARY.md`

## Files Modified

### `.github/workflows/api-tests.yml`
**Changes**: Added push trigger for main branch

**Before**:
```yaml
on:
  pull_request:
    branches: [main]
    paths:
      - "api/**"
      - "pipecat/**"
      - "scripts/**"
      - ".github/workflows/api-tests.yml"
```

**After**:
```yaml
on:
  pull_request:
    branches: [main]
    paths:
      - "api/**"
      - "pipecat/**"
      - "scripts/**"
      - ".github/workflows/api-tests.yml"
  push:
    branches: [main]
    paths:
      - "api/**"
      - "pipecat/**"
      - "scripts/**"
      - ".github/workflows/api-tests.yml"
```

**Why**: Enables automatic deployment by running tests on push to main

## Deployment Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Developer pushes code to main branch                         │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. api-tests.yml workflow runs                                  │
│    - Runs pytest on all API tests                               │
│    - Uses PostgreSQL + Redis services                           │
│    - Must pass for deployment to proceed                        │
└────────────────────────┬────────────────────────────────────────┘
                         ↓ (only if tests pass)
┌─────────────────────────────────────────────────────────────────┐
│ 3. deploy-to-vm.yml workflow triggers                           │
│    - Checks if API/Docker files changed                         │
│    - Sets up SSH connection with key from secrets               │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Copies scripts to VM and executes ci_deploy.sh              │
│    - cd /root/dograh-live/dograh                                │
│    - git fetch origin main                                      │
│    - git reset --hard origin/main                               │
│    - git submodule update --init --recursive                    │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. rolling_update.sh executes (zero-downtime deployment)       │
│    a. Run Alembic database migrations                           │
│    b. Start new workers on alternate band (A→B or B→A)          │
│    c. Health check each new worker                              │
│    d. Switch nginx upstream to new workers                      │
│    e. Drain old workers gracefully (300s timeout)               │
│    f. Kill old workers after drain                              │
│    g. Restart supporting services (ARQ workers)                 │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. healthcheck.sh verifies deployment                           │
│    - Check /api/v1/health endpoint returns 200                  │
│    - Verify worker processes are running                        │
│    - Check Docker containers are healthy                        │
│    - Scan logs for immediate errors                             │
└────────────────────────┬────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. Report success/failure to GitHub Actions                     │
│    ✅ Success: Deployment complete, services healthy            │
│    ❌ Failure: Automatic rollback, old workers still running    │
└─────────────────────────────────────────────────────────────────┘
```

## Zero-Downtime Strategy

The deployment uses the existing **dual-band port strategy** from `rolling_update.sh`:

### Band System
- **Band A**: Workers on ports 8000-8003 (default)
- **Band B**: Workers on ports 8100-8103 (alternate)

### Deployment Process
1. **Detect active band** (read from `run/active_band`)
2. **Start new workers** on the inactive band
3. **Health check** each new worker individually
4. **Switch nginx** to point to new workers
5. **Drain old workers** (allow WebSocket/WebRTC calls to complete)
6. **Kill old workers** after drain timeout (300s default)
7. **Update active_band** file for next deployment

### Rollback on Failure
If health checks fail at any point:
- New workers are immediately killed
- Old workers continue serving traffic
- Nginx configuration stays unchanged
- Deployment workflow exits with error code
- No manual intervention required

## Required GitHub Secrets

Before the pipeline can work, you must add these secrets to your GitHub repository:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `DEBIAN_VM_SSH_KEY` | Private SSH key for deployment | Contents of `~/.ssh/dograh-deploy` |
| `DEBIAN_VM_HOST` | VM IP address or hostname | `203.0.113.42` or `vm.example.com` |
| `DEBIAN_VM_USER` | SSH username | `root` |
| `DEBIAN_VM_PORT` | SSH port | `22` |

## Setup Steps

Follow these steps to complete the setup:

### 1. Generate SSH Key
```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/dograh-deploy -N ""
```

### 2. Add Public Key to VM
```bash
ssh-copy-id -i ~/.ssh/dograh-deploy.pub root@YOUR_VM_IP
```

### 3. Add Secrets to GitHub
1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add each of the 4 secrets listed above

### 4. Test Manual Deployment
1. Go to **Actions** tab
2. Select **Deploy to Debian VM**
3. Click **Run workflow**
4. Leave commit SHA empty
5. Click **Run workflow**
6. Watch logs to verify successful deployment

### 5. Enable Automatic Deployment
Once manual deployment works, automatic deployments are **already enabled**!

They will trigger when you push to main and API/Docker files have changed.

## Detailed Setup Guide

For complete setup instructions, troubleshooting, and advanced configuration, see:

📖 **[CI_CD_SETUP_GUIDE.md](CI_CD_SETUP_GUIDE.md)**

## Security Features

### SSH Key Security
- ✅ Dedicated SSH key (not personal key)
- ✅ Private key stored only in GitHub Secrets
- ✅ Public key only on deployment VM
- ✅ Key rotation recommended every 90 days

### Deployment Safety
- ✅ Concurrency control (one deployment at a time)
- ✅ Test gate (blocked if tests fail)
- ✅ Automatic rollback on failure
- ✅ Health verification before declaring success
- ✅ Comprehensive logging

### Secret Protection
- ✅ Secrets encrypted in GitHub
- ✅ Secrets masked in workflow logs
- ✅ Never exposed in UI or output

## Monitoring

### GitHub Actions
- View deployment status in **Actions** tab
- Green ✅ = successful deployment
- Red ❌ = failed (automatic rollback)

### On the VM
```bash
# Deployment logs
tail -f /root/dograh-live/dograh/logs/deployment/latest.log

# Health status
curl -k https://localhost/api/v1/health

# Worker status
cd /root/dograh-live/dograh
cat run/active_band
ls -la run/*.pid

# Container status
docker compose ps
```

## Performance Metrics

### Typical Deployment Timeline
- **Git pull**: ~10 seconds
- **Database migrations**: ~5-30 seconds
- **New workers start**: ~30 seconds
- **Health checks**: ~60 seconds
- **Nginx switch**: ~1 second
- **Old worker drain**: ~300 seconds (5 minutes)
- **Verification**: ~30 seconds

**Total**: ~7-10 minutes per deployment

### Expected Success Rate
- **Target**: > 95% success rate
- **Rollback**: Automatic on failure
- **Downtime**: Zero during successful deployment

## Rollback Options

### 1. Automatic Rollback
If health checks fail, rollback is **automatic**:
- New workers killed immediately
- Old workers continue serving
- No manual intervention needed

### 2. Manual Rollback via GitHub
1. Go to **Actions** → **Deploy to Debian VM**
2. Click **Run workflow**
3. Enter previous commit SHA
4. Click **Run workflow**

### 3. Manual Rollback on VM
```bash
ssh root@YOUR_VM_IP
cd /root/dograh-live/dograh
git log --oneline -10  # Find previous commit
git checkout <PREVIOUS_COMMIT_SHA>
git submodule update --init --recursive
./scripts/rolling_update.sh
./scripts/healthcheck.sh
```

## Troubleshooting

### Common Issues

1. **SSH Connection Failed**
   - Verify SSH key in secrets
   - Check public key on VM
   - Test SSH manually

2. **Health Check Timeout**
   - Check worker logs on VM
   - Verify services are starting
   - Test health endpoint manually

3. **Rolling Update Failed**
   - Check database migrations
   - Verify ports not in use
   - Review worker startup logs

4. **Tests Pass But No Deployment**
   - Only UI files changed (no deployment needed)
   - Use manual workflow dispatch if needed

For detailed troubleshooting, see **[CI_CD_SETUP_GUIDE.md](CI_CD_SETUP_GUIDE.md)**.

## Next Steps

1. ✅ **Review** this implementation summary
2. ✅ **Read** [CI_CD_SETUP_GUIDE.md](CI_CD_SETUP_GUIDE.md) for detailed setup instructions
3. ✅ **Generate** SSH key for GitHub Actions
4. ✅ **Add** the 4 required secrets to GitHub
5. ✅ **Test** manual deployment workflow
6. ✅ **Verify** automatic deployment works on next push
7. ✅ **Test** rollback procedure
8. ✅ **Monitor** first few deployments closely

## Advanced Features

Consider adding later:
- 📊 Deployment metrics and tracking
- 📢 Slack/Discord notifications
- 🧪 Staging environment
- 📦 Database backup before migrations
- 🔄 Canary deployments
- 🔍 Integration tests post-deployment

## Success Criteria

Your CI/CD pipeline is successful when:
- ✅ Tests pass before every deployment
- ✅ Deployments complete without errors
- ✅ Health checks pass consistently
- ✅ Zero downtime during deployments
- ✅ Automatic rollback works when needed
- ✅ No manual intervention required
- ✅ Deployment time < 10 minutes
- ✅ Success rate > 95%

## Support

For issues or questions:
1. Check **[CI_CD_SETUP_GUIDE.md](CI_CD_SETUP_GUIDE.md)** troubleshooting section
2. Review deployment logs on VM
3. Check GitHub Actions workflow logs
4. Verify all secrets are configured correctly

---

**Status**: ✅ Implementation Complete - Ready for Setup

**Next Action**: Follow the setup steps above to configure GitHub Secrets and test deployment.
