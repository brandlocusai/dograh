#!/usr/bin/env bash
# rolling_update_docker.sh — Zero-downtime Blue-Green update for Docker deployments
#
# Strategy:
#   Band A: api-a / ui-a  (ports inside the network: api=8000, ui=3010)
#   Band B: api-b / ui-b  (same internal ports, different container names)
#
# Flow:
#   1. Read active band from run/active_docker_band (defaults to A on first run)
#   2. Pull latest images
#   3. Start new (inactive) band containers
#   4. Health-check each new container
#   5. Regenerate Nginx config to point upstreams at new band
#   6. Reload Nginx gracefully (in-flight requests finish on old band)
#   7. Stop old band containers
#   8. Save new active band
#
# On ANY failure after step 3: stop new band containers and exit non-zero.
# The old band + nginx remain untouched — users are never impacted.
#
# Usage:
#   ./scripts/rolling_update_docker.sh
#   DRY_RUN=1 ./scripts/rolling_update_docker.sh    # skip actual docker/nginx commands

set -euo pipefail

###############################################################################
### CONFIGURATION
###############################################################################

DEPLOY_DIR="$(cd "$(dirname "$(dirname "${BASH_SOURCE[0]}")")" && pwd)"
RUN_DIR="$DEPLOY_DIR/run"
BAND_FILE="$RUN_DIR/active_docker_band"
LOG_DIR="$DEPLOY_DIR/logs/deployment"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/rolling_docker_${TIMESTAMP}.log"

HEALTH_MAX_ATTEMPTS=${HEALTH_MAX_ATTEMPTS:-30}   # 30 × 4s = 2 min max wait
HEALTH_INTERVAL=${HEALTH_INTERVAL:-4}
DRAIN_SLEEP=${DRAIN_SLEEP:-10}                   # seconds to wait after nginx reload before stopping old band

COMPOSE_CMD="docker compose"
DRY_RUN=${DRY_RUN:-0}

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

###############################################################################
### HELPERS
###############################################################################

log()         { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*"          | tee -a "$LOG_FILE"; }
log_success() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✅ $*${NC}"      | tee -a "$LOG_FILE"; }
log_error()   { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ❌ $*${NC}" >&2   | tee -a "$LOG_FILE"; }
log_warn()    { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  $*${NC}"    | tee -a "$LOG_FILE"; }

run_cmd() {
    log "  → $*"
    if [[ "$DRY_RUN" == "1" ]]; then
        log_warn "    [DRY RUN — skipped]"
    else
        "$@" 2>&1 | tee -a "$LOG_FILE"
    fi
}

opposite_band() { if [[ "$1" == "A" ]]; then echo "B"; else echo "A"; fi; }
band_lower()    { echo "$1" | tr '[:upper:]' '[:lower:]'; }

###############################################################################
### SETUP
###############################################################################

cd "$DEPLOY_DIR"
mkdir -p "$LOG_DIR" "$RUN_DIR"

# Detect docker compose command
if ! docker compose version &>/dev/null; then
    if command -v docker-compose &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "Docker Compose not found. Install it first."
        exit 1
    fi
fi

###############################################################################
### PHASE 0: DETERMINE BANDS
###############################################################################

log "=== Phase 0: Determining active/inactive bands ==="

if [[ -f "$BAND_FILE" ]]; then
    OLD_BAND=$(< "$BAND_FILE")
    if [[ "$OLD_BAND" != "A" && "$OLD_BAND" != "B" ]]; then
        log_warn "Invalid band '$OLD_BAND' in $BAND_FILE — defaulting to A"
        OLD_BAND="A"
    fi
else
    log "No $BAND_FILE found — assuming Band A is active (first run)"
    OLD_BAND="A"
fi

NEW_BAND=$(opposite_band "$OLD_BAND")
OLD_API="api-$(band_lower "$OLD_BAND")"
OLD_UI="ui-$(band_lower "$OLD_BAND")"
NEW_API="api-$(band_lower "$NEW_BAND")"
NEW_UI="ui-$(band_lower "$NEW_BAND")"

log "Current active band : $OLD_BAND  ($OLD_API / $OLD_UI)"
log "Deploying to band   : $NEW_BAND  ($NEW_API / $NEW_UI)"

###############################################################################
### PHASE 1: PULL LATEST IMAGES
###############################################################################

log ""
log "=== Phase 1: Pulling latest prebuilt images ==="

run_cmd $COMPOSE_CMD pull "$NEW_API" "$NEW_UI"

log_success "Images pulled successfully"

###############################################################################
### PHASE 2: RUN DATABASE MIGRATIONS (using freshly pulled NEW image)
###############################################################################

log ""
log "=== Phase 2: Running database migrations ==="

# Always run migrations from the new image so migration files match the new code.
# docker compose run starts a one-shot container from the service definition
# without starting the service permanently.
run_cmd $COMPOSE_CMD run --rm -e LOG_TO_FILE=false "$NEW_API" \
    sh -c "alembic -c /app/api/alembic.ini upgrade head"

log_success "Database migrations completed"

###############################################################################
### PHASE 3: START NEW BAND
###############################################################################

log ""
log "=== Phase 3: Starting new band $NEW_BAND ($NEW_API / $NEW_UI) ==="

# Docker Compose v2 starts profiled services when named explicitly — no --profile needed.
run_cmd $COMPOSE_CMD up -d --no-deps "$NEW_API" "$NEW_UI"

log_success "New band containers started"

###############################################################################
### PHASE 4: HEALTH-CHECK NEW BAND
###############################################################################

log ""
log "=== Phase 4: Health-checking new band ==="

# Rollback helper — stop new containers if anything fails after this point
rollback() {
    log_error "ROLLING BACK — stopping new band $NEW_BAND containers"
    $COMPOSE_CMD stop "$NEW_API" "$NEW_UI" 2>/dev/null || true
    $COMPOSE_CMD rm -f "$NEW_API" "$NEW_UI" 2>/dev/null || true
    log_error "Rollback done. Old band $OLD_BAND is still serving traffic."
    exit 1
}
trap rollback ERR

check_container_health() {
    local container=$1
    local attempt=1
    log "  Waiting for $container to become healthy..."

    while [[ $attempt -le $HEALTH_MAX_ATTEMPTS ]]; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "missing")
        if [[ "$STATUS" == "healthy" ]]; then
            log_success "  $container is healthy (attempt $attempt)"
            return 0
        fi
        log "    Attempt $attempt/$HEALTH_MAX_ATTEMPTS — status: $STATUS"
        sleep "$HEALTH_INTERVAL"
        attempt=$((attempt + 1))
    done

    log_error "$container did not become healthy in time"
    return 1
}

# Map service name to container name
API_CONTAINER="dograh-api-$(band_lower "$NEW_BAND")"
UI_CONTAINER="dograh-ui-$(band_lower "$NEW_BAND")"

check_container_health "$API_CONTAINER"
check_container_health "$UI_CONTAINER"

log_success "New band $NEW_BAND is healthy"

###############################################################################
### PHASE 5: SWITCH NGINX TO NEW BAND
###############################################################################

log ""
log "=== Phase 5: Switching Nginx to new band $NEW_BAND ==="

NGINX_CONF_DEST="/etc/nginx/conf.d/default.conf"

# Source env vars needed by the render function
set -a; source "$DEPLOY_DIR/.env"; set +a

# Use the library function to regenerate the config with the new band
source "$DEPLOY_DIR/scripts/lib/setup_common.sh"
export DOGRAH_DEPLOY_PROJECT_DIR="$DEPLOY_DIR"

TMP_CONF=$(mktemp)
dograh_render_remote_nginx_conf "$DEPLOY_DIR" "$TMP_CONF" "$NEW_BAND" "$NEW_BAND"

log "Generated Nginx config (bands: api=$NEW_BAND, ui=$NEW_BAND):"
grep "server " "$TMP_CONF" | head -6 | tee -a "$LOG_FILE"

# Resolve the actual Docker volume name from the running nginx container.
# Compose prefixes volume names with the project name (e.g. dograh_nginx-generated),
# so hardcoding the short name would write to the wrong volume.
NGINX_VOLUME=$(docker inspect nginx_https \
    --format '{{range .Mounts}}{{if eq .Destination "/etc/nginx/conf.d"}}{{.Name}}{{end}}{{end}}')

if [[ -z "$NGINX_VOLUME" ]]; then
    log_error "Could not determine nginx config volume name from nginx_https container"
    rm -f "$TMP_CONF"
    rollback
fi
log "Nginx config volume: $NGINX_VOLUME"

# Write new config into the volume via a one-shot container.
# docker cp cannot be used because nginx mounts the volume as :ro.
if [[ "$DRY_RUN" == "1" ]]; then
    log_warn "[DRY RUN] Would write $TMP_CONF → $NGINX_VOLUME/default.conf and reload"
else
    if ! docker run --rm \
            -v "${NGINX_VOLUME}:/nginx-conf" \
            -v "${TMP_CONF}:/tmp/new.conf:ro" \
            alpine sh -c "cp /tmp/new.conf /nginx-conf/default.conf" 2>&1 | tee -a "$LOG_FILE"; then
        log_error "Failed to write Nginx config into volume — rolling back"
        rm -f "$TMP_CONF"
        rollback
    fi
    # Test config first
    if ! docker exec nginx_https nginx -t 2>&1 | tee -a "$LOG_FILE"; then
        log_error "Nginx config test FAILED — rolling back"
        rm -f "$TMP_CONF"
        rollback
    fi
    # Graceful reload: existing connections finish on old band
    docker exec nginx_https nginx -s reload 2>&1 | tee -a "$LOG_FILE"
fi
rm -f "$TMP_CONF"

log_success "Nginx reloaded — traffic now routes to band $NEW_BAND"

###############################################################################
### PHASE 6: DRAIN & STOP OLD BAND
###############################################################################

log ""
log "=== Phase 6: Draining old band $OLD_BAND (waiting ${DRAIN_SLEEP}s for in-flight requests) ==="

# Give long-running WebSocket connections time to finish
sleep "$DRAIN_SLEEP"

run_cmd $COMPOSE_CMD stop "$OLD_API" "$OLD_UI"
run_cmd $COMPOSE_CMD rm -f "$OLD_API" "$OLD_UI"

log_success "Old band $OLD_BAND stopped and removed"

###############################################################################
### PHASE 7: FINALIZE
###############################################################################

# Remove the rollback trap — everything succeeded
trap - ERR

log ""
log "=== Phase 7: Finalizing ==="

echo "$NEW_BAND" > "$BAND_FILE"

DEPLOYED_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
DEPLOYED_MSG=$(git log -1 --pretty=format:"%s" 2>/dev/null || echo "")

# Symlink latest log
ln -sf "$LOG_FILE" "$LOG_DIR/latest.log"

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Rolling update completed — ZERO DOWNTIME     ${NC}"
echo ""
echo -e "  Band:    $OLD_BAND → $NEW_BAND"
echo -e "  API:     $NEW_API"
echo -e "  UI:      $NEW_UI"
echo -e "  Commit:  $DEPLOYED_COMMIT"
echo -e "  Message: $DEPLOYED_MSG"
echo -e "  Log:     $LOG_FILE"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
