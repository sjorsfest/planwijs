#!/bin/sh

set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$APP_DIR"

# --- Configuration Defaults ---
REMOTE="${DEPLOY_REMOTE:-origin}"
BRANCH="${DEPLOY_BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-leslab}"
CLOUDFLARED_SERVICE="${CLOUDFLARED_SERVICE:-cloudflared}"
RESTART_CLOUDFLARED="${RESTART_CLOUDFLARED:-0}"

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8030}"  # Incremented port for the new service
HEALTH_PATH="${HEALTH_PATH:-/health}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://$APP_HOST:$APP_PORT$HEALTH_PATH}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://api.leslab.net/health}"

SYNC_FROZEN="${SYNC_FROZEN:-1}"
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-0}"
SKIP_TY_CHECK="${SKIP_TY_CHECK:-0}"

log() {
    printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

run_systemctl() {
    if [ "$(id -u)" -eq 0 ]; then
        systemctl "$@"
    else
        sudo systemctl "$@"
    fi
}

show_service_logs() {
    service_name="$1"
    if ! command -v journalctl >/dev/null 2>&1; then
        return 0
    fi

    if [ "$(id -u)" -eq 0 ]; then
        journalctl -u "$service_name" -n 80 --no-pager || true
    else
        sudo journalctl -u "$service_name" -n 80 --no-pager || true
    fi
}

wait_for_health() {
    url="$1"
    attempts="$2"
    delay_seconds="$3"

    i=1
    while [ "$i" -le "$attempts" ]; do
        if curl --fail --silent --show-error --max-time 10 "$url" >/dev/null; then
            return 0
        fi
        sleep "$delay_seconds"
        i=$((i + 1))
    done
    return 1
}

# --- Prerequisites ---
need_cmd git
need_cmd uv
need_cmd curl

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    fail "Current directory is not a git repository: $APP_DIR"
fi

if ! git diff --quiet --ignore-submodules -- || ! git diff --cached --quiet --ignore-submodules --; then
    fail "Working tree has local changes. Commit or stash before deploying."
fi

# --- Git Operations ---
current_branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$current_branch" != "$BRANCH" ]; then
    log "Switching branch from $current_branch to $BRANCH"
    git checkout "$BRANCH"
fi

log "Fetching latest code from $REMOTE/$BRANCH"
git fetch --prune "$REMOTE"
if ! git show-ref --verify --quiet "refs/remotes/$REMOTE/$BRANCH"; then
    fail "Remote branch not found: $REMOTE/$BRANCH"
fi

log "Fast-forwarding local branch"
git merge --ff-only "$REMOTE/$BRANCH"

# --- Dependency Sync ---
if [ "$SYNC_FROZEN" = "1" ]; then
    log "Syncing dependencies with uv (frozen lockfile)"
    uv sync --frozen
else
    log "Syncing dependencies with uv"
    uv sync
fi

# --- Database & Checks ---
if [ "$SKIP_MIGRATIONS" != "1" ]; then
    log "Running database migrations"
    uv run alembic upgrade head
else
    log "Skipping migrations (SKIP_MIGRATIONS=1)"
fi

if [ "$SKIP_TY_CHECK" != "1" ]; then
    log "Running type checks"
    uv run ty check
else
    log "Skipping type checks (SKIP_TY_CHECK=1)"
fi

# --- Service Restart ---
log "Restarting service: $SERVICE_NAME"
run_systemctl restart "$SERVICE_NAME"

if ! run_systemctl is-active --quiet "$SERVICE_NAME"; then
    log "Service failed to become active: $SERVICE_NAME"
    show_service_logs "$SERVICE_NAME"
    fail "Deployment failed during service restart"
fi

# --- Tunnel Sync ---
if [ "$RESTART_CLOUDFLARED" = "1" ]; then
    log "Restarting tunnel service: $CLOUDFLARED_SERVICE"
    run_systemctl restart "$CLOUDFLARED_SERVICE"
    if ! run_systemctl is-active --quiet "$CLOUDFLARED_SERVICE"; then
        log "Tunnel service failed to become active: $CLOUDFLARED_SERVICE"
        show_service_logs "$CLOUDFLARED_SERVICE"
        fail "Deployment failed during cloudflared restart"
    fi
fi

# --- Health Checks ---
log "Checking local health endpoint: $LOCAL_HEALTH_URL"
if ! wait_for_health "$LOCAL_HEALTH_URL" 30 2; then
    show_service_logs "$SERVICE_NAME"
    fail "Local health check failed: $LOCAL_HEALTH_URL"
fi

if [ -n "$PUBLIC_HEALTH_URL" ]; then
    log "Checking public health endpoint: $PUBLIC_HEALTH_URL"
    if ! wait_for_health "$PUBLIC_HEALTH_URL" 30 2; then
        fail "Public health check failed: $PUBLIC_HEALTH_URL"
    fi
fi

deployed_commit=$(git rev-parse --short HEAD)
log "Deployment of $SERVICE_NAME succeeded on commit $deployed_commit"
