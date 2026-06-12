#!/bin/bash
#
# CI/CD Deployment Script - Executed on VM via SSH
#
# This script handles the actual deployment steps on the Debian VM:
# 1. Navigates to deployment directory
# 2. Pulls latest code from main branch
# 3. Updates git submodules (pipecat)
# 4. Executes rolling_update.sh for zero-downtime deployment
# 5. Captures deployment logs and returns appropriate exit codes
#

set -e  # Exit on any error
set -u  # Exit on undefined variable

# Configuration
DEPLOY_DIR="/root/dograh-live/dograh"
LOG_DIR="$DEPLOY_DIR/logs/deployment"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/deploy_${TIMESTAMP}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✅ $1${NC}" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ❌ $1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  $1${NC}" | tee -a "$LOG_FILE"
}

# Error handler
error_exit() {
    log_error "$1"
    exit 1
}

# Main deployment process
main() {
    # Check if deployment directory exists FIRST
    if [ ! -d "$DEPLOY_DIR" ]; then
        echo "[ERROR] Deployment directory not found: $DEPLOY_DIR" >&2
        exit 1
    fi

    # Navigate to deployment directory
    cd "$DEPLOY_DIR" || {
        echo "[ERROR] Failed to change to deployment directory: $DEPLOY_DIR" >&2
        exit 1
    }

    # Create log directory (now that we're in the right place)
    if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
        echo "[ERROR] Failed to create log directory: $LOG_DIR" >&2
        echo "[ERROR] Current directory: $(pwd)" >&2
        echo "[ERROR] Permissions: $(ls -ld "$DEPLOY_DIR" 2>&1)" >&2
        exit 1
    fi

    log "Starting CI/CD deployment process..."
    log "Navigating to deployment directory: $DEPLOY_DIR"

    # Check current branch
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    log "Current branch: $CURRENT_BRANCH"

    # Fetch latest changes
    log "Fetching latest changes from origin..."
    if ! git fetch origin main 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "Failed to fetch from origin"
    fi

    # Show what we're deploying
    CURRENT_COMMIT=$(git rev-parse HEAD)
    TARGET_COMMIT=$(git rev-parse origin/main)
    log "Current commit: $CURRENT_COMMIT"
    log "Target commit: $TARGET_COMMIT"

    if [ "$CURRENT_COMMIT" = "$TARGET_COMMIT" ]; then
        log_warning "Already at target commit - no changes to deploy"
        log "Proceeding anyway to ensure services are up-to-date..."
    fi

    # Check for local changes
    if ! git diff-index --quiet HEAD --; then
        log_warning "Local changes detected - will be overwritten"
        git status --short | tee -a "$LOG_FILE"
    fi

    # Reset to origin/main (hard reset)
    log "Resetting to origin/main..."
    if ! git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "Failed to reset to origin/main"
    fi

    log_success "Code updated to latest commit"

    # Update git submodules (pipecat)
    log "Updating git submodules..."
    if ! git submodule update --init --recursive 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "Failed to update git submodules"
    fi

    log_success "Submodules updated successfully"

    # Check if rolling_update.sh exists
    if [ ! -f "scripts/rolling_update.sh" ]; then
        error_exit "rolling_update.sh script not found"
    fi

    # Make rolling_update.sh executable
    chmod +x scripts/rolling_update.sh

    # Execute rolling update for zero-downtime deployment
    log "==================================="
    log "Starting rolling update..."
    log "==================================="

    if ./scripts/rolling_update.sh 2>&1 | tee -a "$LOG_FILE"; then
        log_success "Rolling update completed successfully"
    else
        EXIT_CODE=$?
        error_exit "Rolling update failed with exit code: $EXIT_CODE"
    fi

    # Show final commit info
    DEPLOYED_COMMIT=$(git rev-parse HEAD)
    DEPLOYED_MESSAGE=$(git log -1 --pretty=format:"%s")
    log ""
    log "==================================="
    log_success "Deployment completed successfully"
    log "==================================="
    log "Deployed commit: $DEPLOYED_COMMIT"
    log "Commit message: $DEPLOYED_MESSAGE"
    log "Deployment log: $LOG_FILE"

    # Symlink latest log
    ln -sf "$LOG_FILE" "$LOG_DIR/latest.log"

    return 0
}

# Execute main function
main "$@"
