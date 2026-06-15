#!/bin/bash
#
# CI/CD Deployment Script - Docker-Based Zero-Downtime Deployment
#
# Called by GitHub Actions via SSH. Performs:
#   1. git fetch + reset --hard origin/main
#   2. git submodule update (keep pipecat in sync)
#   3. scripts/rolling_update_docker.sh  (Blue-Green swap — 0 downtime)
#

set -e
set -u
set -o pipefail

DEPLOY_DIR="/root/dograh-live/dograh"
LOG_DIR="$DEPLOY_DIR/logs/deployment"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/deploy_${TIMESTAMP}.log"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()         { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"; }
log_success() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✅ $1${NC}" | tee -a "$LOG_FILE"; }
log_error()   { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ❌ $1${NC}" | tee -a "$LOG_FILE"; }
log_warning() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  $1${NC}" | tee -a "$LOG_FILE"; }

error_exit() { log_error "$1"; exit 1; }

main() {
    [[ -d "$DEPLOY_DIR" ]] || { echo "[ERROR] $DEPLOY_DIR not found" >&2; exit 1; }
    cd "$DEPLOY_DIR"
    mkdir -p "$LOG_DIR"

    log "======================================="
    log "Dograh CI/CD deployment starting"
    log "======================================="
    log "Directory : $DEPLOY_DIR"
    log "Branch    : $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    log "Old SHA   : $(git rev-parse HEAD 2>/dev/null || echo unknown)"

    # ── Step 1: Sync code ─────────────────────────────────────────────────────
    log "Fetching latest code from origin/main..."
    if ! git fetch origin main 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "git fetch failed"
    fi

    CURRENT_COMMIT=$(git rev-parse HEAD)
    TARGET_COMMIT=$(git rev-parse origin/main)
    if [[ "$CURRENT_COMMIT" == "$TARGET_COMMIT" ]]; then
        log_warning "Already at target commit — re-deploying to ensure images are up-to-date"
    fi

    log "Resetting to origin/main..."
    if ! git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "git reset failed"
    fi
    log_success "Code updated — new SHA: $(git rev-parse HEAD)"

    # ── Step 2: Submodules ────────────────────────────────────────────────────
    log "Updating git submodules (pipecat)..."
    if ! git submodule update --init --recursive 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "git submodule update failed"
    fi
    log_success "Submodules updated"

    # ── Step 3: First-run cleanup — remove legacy local-build containers ─────
    # Old deployments used container names like dograh-api-1 / dograh-ui-1
    # (docker-compose.override.yaml local build). Those containers aren't part of
    # the blue-green bands so they must be stopped before the first rolling update.
    for old_container in dograh-api-1 dograh-ui-1; do
        if docker ps -q -f "name=^${old_container}$" | grep -q .; then
            log_warning "Stopping legacy container $old_container (pre-blue-green deployment)"
            docker stop "$old_container" || true
            docker rm "$old_container" || true
        fi
    done

    # ── Step 4: Blue-Green rolling update ─────────────────────────────────────
    log "======================================="
    log "Starting zero-downtime rolling update..."
    log "======================================="

    chmod +x "$DEPLOY_DIR/scripts/rolling_update_docker.sh"
    if ! "$DEPLOY_DIR/scripts/rolling_update_docker.sh" 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "rolling_update_docker.sh failed — see log: $LOG_FILE"
    fi

    log_success "Deployment complete!"
    ln -sf "$LOG_FILE" "$LOG_DIR/latest.log"
    return 0
}

main "$@"
