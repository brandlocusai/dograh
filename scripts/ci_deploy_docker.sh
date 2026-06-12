#!/bin/bash
#
# CI/CD Deployment Script - Docker-Based Deployment
#
# This script handles deployment for Docker Compose environments:
# 1. Pulls latest code
# 2. Updates git submodules
# 3. Runs database migrations
# 4. Restarts Docker containers with zero-downtime strategy
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
        exit 1
    fi

    log "Starting CI/CD deployment process (Docker mode)..."
    log "Deployment directory: $DEPLOY_DIR"

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

    # Check if docker-compose is available
    if ! command -v docker &> /dev/null; then
        error_exit "Docker is not installed or not in PATH"
    fi

    log "Checking Docker Compose..."
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        error_exit "Docker Compose is not installed"
    fi
    log "Using: $COMPOSE_CMD"

    # Enable Docker BuildKit for faster builds (if available)
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1
    log "Docker BuildKit enabled for faster builds"

    # Run database migrations in the API container
    log "==================================="
    log "Running database migrations..."
    log "==================================="

    if ! $COMPOSE_CMD exec -T api alembic upgrade head 2>&1 | tee -a "$LOG_FILE"; then
        log_warning "Migration failed or container not running, trying alternative method..."

        # Try running migrations with docker-compose run
        if ! $COMPOSE_CMD run --rm api alembic upgrade head 2>&1 | tee -a "$LOG_FILE"; then
            error_exit "Database migrations failed"
        fi
    fi

    log_success "Database migrations completed"

    # Rebuild and recreate containers with new code
    log "==================================="
    log "Rebuilding and deploying containers..."
    log "==================================="

    # Build new images for API and UI with latest code
    log "Building new Docker images (this may take 2-5 minutes)..."
    BUILD_START=$(date +%s)

    if ! $COMPOSE_CMD build api ui 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "Failed to build Docker images"
    fi

    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    log_success "Docker images built successfully (took ${BUILD_TIME}s)"

    # Recreate containers with new images
    # --no-deps: Don't recreate linked services (postgres, redis, etc.)
    # --force-recreate: Force recreation even if config hasn't changed
    # -d: Detached mode
    log "Recreating API container with new image..."
    if ! $COMPOSE_CMD up -d --no-deps --force-recreate api 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "Failed to recreate API container"
    fi
    log_success "API container recreated"

    # Wait for API to be healthy
    log "Waiting for API to be ready..."
    sleep 10

    log "Recreating UI container with new image..."
    if ! $COMPOSE_CMD up -d --no-deps --force-recreate ui 2>&1 | tee -a "$LOG_FILE"; then
        error_exit "Failed to recreate UI container"
    fi
    log_success "UI container recreated"

    # Wait for UI to be ready
    log "Waiting for UI to be ready..."
    sleep 5

    # Reload nginx to pick up any config changes
    log "Reloading nginx..."
    if $COMPOSE_CMD exec -T nginx nginx -t 2>&1 | tee -a "$LOG_FILE"; then
        if $COMPOSE_CMD exec -T nginx nginx -s reload 2>&1 | tee -a "$LOG_FILE"; then
            log_success "Nginx reloaded"
        else
            log_warning "Nginx reload failed, but continuing..."
        fi
    else
        log_warning "Nginx config test failed, skipping reload"
    fi

    # Show container status
    log "Container status:"
    $COMPOSE_CMD ps 2>&1 | tee -a "$LOG_FILE"

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
