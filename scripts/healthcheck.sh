#!/bin/bash
#
# Post-Deployment Health Check Script
#
# Validates that deployment succeeded by:
# 1. Polling health endpoint: https://localhost/api/v1/health
# 2. Verifying response code is 200
# 3. Checking that worker processes are running
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

    # Wait a moment for nginx reload to complete
    log "Waiting for nginx reload to complete..."
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

# Check worker processes
check_worker_processes() {
    log "Checking uvicorn worker processes..."

    cd "$DEPLOY_DIR" || {
        log_error "Failed to change to deployment directory"
        return 1
    }

    # Check if run directory exists
    if [ ! -d "run" ]; then
        log_error "run/ directory not found"
        return 1
    fi

    # Get active band
    if [ -f "run/active_band" ]; then
        ACTIVE_BAND=$(cat run/active_band)
        log "Active band: $ACTIVE_BAND"
    else
        log_warning "active_band file not found - assuming band A"
        ACTIVE_BAND="A"
    fi

    # Check PID files based on active band
    local pid_files_found=0
    local expected_workers=4  # Adjust based on your configuration

    if [ "$ACTIVE_BAND" = "A" ]; then
        log "Checking Band A worker PIDs..."
        for i in $(seq 0 3); do
            PID_FILE="run/worker_a_$i.pid"
            if [ -f "$PID_FILE" ]; then
                PID=$(cat "$PID_FILE")
                if ps -p "$PID" > /dev/null 2>&1; then
                    log_success "Worker A-$i is running (PID: $PID)"
                    pid_files_found=$((pid_files_found + 1))
                else
                    log_warning "Worker A-$i PID file exists but process not running (PID: $PID)"
                fi
            else
                log_warning "Worker A-$i PID file not found: $PID_FILE"
            fi
        done
    else
        log "Checking Band B worker PIDs..."
        for i in $(seq 0 3); do
            PID_FILE="run/worker_b_$i.pid"
            if [ -f "$PID_FILE" ]; then
                PID=$(cat "$PID_FILE")
                if ps -p "$PID" > /dev/null 2>&1; then
                    log_success "Worker B-$i is running (PID: $PID)"
                    pid_files_found=$((pid_files_found + 1))
                else
                    log_warning "Worker B-$i PID file exists but process not running (PID: $PID)"
                fi
            else
                log_warning "Worker B-$i PID file not found: $PID_FILE"
            fi
        done
    fi

    if [ $pid_files_found -ge $expected_workers ]; then
        log_success "All expected workers are running ($pid_files_found/$expected_workers)"
        return 0
    else
        log_error "Not all workers are running ($pid_files_found/$expected_workers)"
        return 1
    fi
}

# Check Docker containers
check_docker_containers() {
    log "Checking Docker container status..."

    cd "$DEPLOY_DIR" || {
        log_error "Failed to change to deployment directory"
        return 1
    }

    # Check if containers are running
    CONTAINERS=$(docker compose ps --services --filter "status=running" 2>/dev/null)

    if [ -z "$CONTAINERS" ]; then
        log_error "No running Docker containers found"
        return 1
    fi

    log "Running containers:"
    echo "$CONTAINERS" | while read -r container; do
        log_success "  - $container"
    done

    # Check for unhealthy containers
    UNHEALTHY=$(docker compose ps --filter "health=unhealthy" -q 2>/dev/null)

    if [ -n "$UNHEALTHY" ]; then
        log_error "Found unhealthy containers"
        docker compose ps --filter "health=unhealthy"
        return 1
    fi

    log_success "All Docker containers are healthy"
    return 0
}

# Check for immediate errors in logs
check_recent_logs() {
    log "Checking recent logs for errors..."

    cd "$DEPLOY_DIR" || {
        log_error "Failed to change to deployment directory"
        return 1
    }

    if [ -d "logs/latest" ]; then
        # Check for errors in the last 50 lines of each log file
        ERROR_COUNT=0
        for log_file in logs/latest/*.log; do
            if [ -f "$log_file" ]; then
                ERRORS=$(tail -n 50 "$log_file" | grep -i "error\|exception\|traceback" | grep -v "DEBUG" | wc -l)
                if [ "$ERRORS" -gt 0 ]; then
                    log_warning "Found $ERRORS error lines in $(basename "$log_file")"
                    ERROR_COUNT=$((ERROR_COUNT + ERRORS))
                fi
            fi
        done

        if [ "$ERROR_COUNT" -gt 5 ]; then
            log_error "Found significant errors in recent logs ($ERROR_COUNT lines)"
            log "Review logs at: $DEPLOY_DIR/logs/latest/"
            return 1
        elif [ "$ERROR_COUNT" -gt 0 ]; then
            log_warning "Found minor errors in logs ($ERROR_COUNT lines) - may be transient"
        else
            log_success "No significant errors found in recent logs"
        fi
    else
        log_warning "logs/latest/ directory not found - skipping log check"
    fi

    return 0
}

# Main health check process
main() {
    log "==================================="
    log "Starting post-deployment health checks"
    log "==================================="

    local failed_checks=0

    # Run all health checks
    if ! check_health_endpoint; then
        failed_checks=$((failed_checks + 1))
    fi

    if ! check_worker_processes; then
        failed_checks=$((failed_checks + 1))
    fi

    if ! check_docker_containers; then
        failed_checks=$((failed_checks + 1))
    fi

    # Log check is informational only - don't fail on it
    check_recent_logs

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
