#!/bin/bash
#
# Post-Deployment Health Check Script - Docker Version
#
# Validates that deployment succeeded by:
# 1. Polling health endpoint: https://localhost/api/v1/health
# 2. Verifying response code is 200
# 3. Checking that Docker containers are running
# 4. Returns exit code 0 on success, 1 on failure
#

set -u  # Exit on undefined variable

# Configuration
HEALTH_URL="https://localhost/api/v1/health"
MAX_ATTEMPTS=30
RETRY_INTERVAL=2
DEPLOY_DIR="/root/dograh-live/dograh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✅ $1${NC}"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ❌ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  $1${NC}"
}

# Check health endpoint
check_health_endpoint() {
    log "Checking health endpoint: $HEALTH_URL"

    # Wait a moment for containers to fully start
    log "Waiting for services to stabilize..."
    sleep 5

    local attempt=1
    while [ $attempt -le $MAX_ATTEMPTS ]; do
        log "Health check attempt $attempt/$MAX_ATTEMPTS..."

        # Make health check request (ignore SSL cert validation for localhost)
        HTTP_CODE=$(curl -s -k -o /tmp/health_response.json -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

        if [ "$HTTP_CODE" = "200" ]; then
            log_success "Health endpoint returned 200 OK"

            # Show response
            if [ -f /tmp/health_response.json ]; then
                RESPONSE=$(cat /tmp/health_response.json)
                log "Response: $RESPONSE"
                rm -f /tmp/health_response.json
            fi

            return 0
        else
            log_warning "Health check failed - HTTP $HTTP_CODE (attempt $attempt/$MAX_ATTEMPTS)"

            if [ $attempt -eq $MAX_ATTEMPTS ]; then
                log_error "Health endpoint check failed after $MAX_ATTEMPTS attempts"
                return 1
            fi

            sleep $RETRY_INTERVAL
            attempt=$((attempt + 1))
        fi
    done

    return 1
}

# Check Docker containers
check_docker_containers() {
    log "Checking Docker container status..."

    cd "$DEPLOY_DIR" || {
        log_error "Failed to change to deployment directory"
        return 1
    }

    # Detect docker compose command
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "Docker Compose not found"
        return 1
    fi

    # Check if containers are running
    CONTAINERS=$($COMPOSE_CMD ps --services --filter "status=running" 2>/dev/null)

    if [ -z "$CONTAINERS" ]; then
        log_error "No running Docker containers found"
        return 1
    fi

    log "Running containers:"
    echo "$CONTAINERS" | while read -r container; do
        log_success "  - $container"
    done

    # Check for unhealthy containers
    UNHEALTHY=$($COMPOSE_CMD ps --filter "health=unhealthy" -q 2>/dev/null)

    if [ -n "$UNHEALTHY" ]; then
        log_error "Found unhealthy containers"
        $COMPOSE_CMD ps --filter "health=unhealthy"
        return 1
    fi

    # Determine active band (A or B) from rolling update state file
    local band_file="$DEPLOY_DIR/run/active_docker_band"
    local active_band="a"
    if [[ -f "$band_file" ]]; then
        active_band=$(tr '[:upper:]' '[:lower:]' < "$band_file")
    fi

    # Check critical containers are running (api/ui use active band suffix)
    CRITICAL_CONTAINERS=("api-${active_band}" "ui-${active_band}" "postgres" "redis" "nginx")
    local missing=0

    for container in "${CRITICAL_CONTAINERS[@]}"; do
        if echo "$CONTAINERS" | grep -q "^${container}$"; then
            log_success "  ✓ $container is running"
        else
            log_error "  ✗ $container is NOT running"
            missing=$((missing + 1))
        fi
    done

    if [ $missing -gt 0 ]; then
        log_error "Missing $missing critical container(s)"
        return 1
    fi

    log_success "All critical Docker containers are running"
    return 0
}

# Check API container logs for errors
check_api_logs() {
    log "Checking API container logs for errors..."

    cd "$DEPLOY_DIR" || {
        log_error "Failed to change to deployment directory"
        return 1
    }

    # Detect docker compose command
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_warning "Docker Compose not found - skipping log check"
        return 0
    fi

    # Determine active band
    local band_file="$DEPLOY_DIR/run/active_docker_band"
    local active_band="a"
    if [[ -f "$band_file" ]]; then
        active_band=$(tr '[:upper:]' '[:lower:]' < "$band_file")
    fi
    local active_api="api-${active_band}"

    # Check last 50 lines of API logs for errors
    ERROR_COUNT=$($COMPOSE_CMD logs --tail=50 "$active_api" 2>/dev/null | grep -i "error\|exception\|traceback" | grep -v "DEBUG" | wc -l)

    if [ "$ERROR_COUNT" -gt 5 ]; then
        log_error "Found significant errors in API logs ($ERROR_COUNT lines)"
        log "Recent API logs:"
        $COMPOSE_CMD logs --tail=20 "$active_api" 2>&1 | tail -n 20
        return 1
    elif [ "$ERROR_COUNT" -gt 0 ]; then
        log_warning "Found minor errors in API logs ($ERROR_COUNT lines) - may be transient"
    else
        log_success "No significant errors found in API logs"
    fi

    return 0
}

# Check if containers are restarting
check_container_restarts() {
    log "Checking for container restart loops..."

    cd "$DEPLOY_DIR" || {
        log_error "Failed to change to deployment directory"
        return 1
    }

    # Detect docker compose command
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_warning "Docker Compose not found - skipping restart check"
        return 0
    fi

    # Get container status with restart counts
    local restarting=0
    while IFS= read -r line; do
        # Check if any container is restarting
        if echo "$line" | grep -q "Restarting"; then
            log_warning "Container is restarting: $line"
            restarting=$((restarting + 1))
        fi
    done < <($COMPOSE_CMD ps 2>/dev/null)

    if [ $restarting -gt 0 ]; then
        log_error "Found $restarting container(s) in restart loop"
        return 1
    fi

    log_success "No containers in restart loops"
    return 0
}

# Main health check process
main() {
    log "==================================="
    log "Starting post-deployment health checks (Docker mode)"
    log "==================================="

    local failed_checks=0

    # Run all health checks
    if ! check_health_endpoint; then
        failed_checks=$((failed_checks + 1))
    fi

    if ! check_docker_containers; then
        failed_checks=$((failed_checks + 1))
    fi

    if ! check_container_restarts; then
        failed_checks=$((failed_checks + 1))
    fi

    # Log check is informational only - don't fail on it
    check_api_logs

    # Final verdict
    log ""
    log "==================================="
    if [ $failed_checks -eq 0 ]; then
        log_success "All health checks passed ✅"
        log "==================================="
        return 0
    else
        log_error "Health checks failed: $failed_checks check(s) did not pass ❌"
        log "==================================="
        return 1
    fi
}

# Execute main function
main "$@"
