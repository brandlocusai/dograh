# Zero-Downtime CI/CD Pipeline

## How it works

Push code to `main` → automatic deploy with **0 seconds downtime**.

```
Push to main
    │
    ▼
API Tests (api-tests.yml)
    │  triggers on: api/, ui/, scripts/ changes
    │
    ▼
Build & Push Docker Images (docker-image.yml)
    │  builds: ghcr.io/brandlocusai/dograh-api:latest
    │           ghcr.io/brandlocusai/dograh-ui:latest
    │
    ▼
Deploy to VM (deploy-to-vm.yml)
    │  SSHs into VM → runs scripts/ci_deploy_docker.sh
    │
    ▼
Zero-Downtime Rolling Update (scripts/rolling_update_docker.sh)
```

## Blue-Green Deployment

Two identical bands alternate on every deploy:

| Band | API container | UI container |
|------|--------------|-------------|
| A | `dograh-api-a` | `dograh-ui-a` |
| B | `dograh-api-b` | `dograh-ui-b` |

**Rolling update steps:**
1. Pull latest images from GHCR
2. Run DB migrations from new image
3. Start inactive band (e.g. B)
4. Health-check new band (up to 2 min)
5. Write new Nginx upstream config → graceful reload (nginx keeps serving old band during reload)
6. Wait 10s for in-flight requests to drain
7. Stop old band (e.g. A)
8. Save new active band to `run/active_docker_band`

If health checks fail → new band is stopped, old band keeps serving, deploy exits non-zero.

## GitHub Secrets Required

Set these in **GitHub → Settings → Secrets → Actions**:

| Secret | Value |
|--------|-------|
| `DEBIAN_VM_SSH_KEY` | Private SSH key for the VM |
| `DEBIAN_VM_HOST` | VM IP or hostname |
| `DEBIAN_VM_USER` | SSH user (e.g. `root`) |
| `DEBIAN_VM_PORT` | SSH port (e.g. `22`) |

## Manual Trigger

To deploy without a code change (e.g. after fixing a workflow file):

```bash
gh workflow run "Build and Push Docker Images" --repo brandlocusai/dograh --ref main
```

Or: GitHub → Actions → "Build and Push Docker Images" → Run workflow.

## Key Files

| File | Purpose |
|------|---------|
| `.github/workflows/docker-image.yml` | Build & push images to GHCR |
| `.github/workflows/deploy-to-vm.yml` | SSH deploy trigger |
| `scripts/rolling_update_docker.sh` | Blue-green swap logic |
| `scripts/ci_deploy_docker.sh` | Entry point on VM (git pull → rolling update) |
| `scripts/healthcheck_docker.sh` | Post-deploy verification |
| `run/active_docker_band` | Current active band (`A` or `B`) |

## Checking Status

```bash
# What's running and which band is active
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
cat /root/dograh-live/dograh/run/active_docker_band

# Latest deployment log
cat /root/dograh-live/dograh/logs/deployment/latest.log
```
