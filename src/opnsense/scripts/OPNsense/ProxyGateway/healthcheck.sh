#!/bin/sh

# healthcheck.sh — Probe connectivity through a proxy gateway connection
# Called periodically by cron or configd
# Exit code: 0 = healthy, 1 = unhealthy
#
# Tests connectivity by sending traffic THROUGH the proxy server to a target.
# Uses curl --proxy to route through the actual SOCKS5/HTTP proxy, which
# verifies the entire chain: proxy reachable → proxy forwards → target responds.
#
# Default target is http://1.1.1.1/ (Cloudflare anycast, returns HTTP 301).
# IP-based to avoid DNS dependency. Universally reachable regardless of country.

SCRIPT_DIR=$(dirname "$0")
RUNDIR="/var/run/proxygateway"
LOGDIR="/var/log/proxygateway"

# Source structured logging library
. "${SCRIPT_DIR}/lib/logging.sh"

# Default probe target: Cloudflare anycast IP (returns 301, no DNS needed)
DEFAULT_TARGET="http://1.1.1.1/"

NAME="$1"
TARGET="${2:-$DEFAULT_TARGET}"
TIMEOUT="${3:-5}"

if [ -z "$NAME" ]; then
    echo "Usage: $0 <name> [target_url] [timeout_seconds]"
    exit 1
fi

# Validate name (alphanumeric + underscore, max 16 chars — must match MVC model)
echo "$NAME" | grep -qE '^[a-zA-Z0-9_]{1,16}$' || {
    echo "ERROR: Invalid connection name: $NAME"
    exit 1
}

CONFFILE="${RUNDIR}/${NAME}.conf"
STATUSFILE="${RUNDIR}/${NAME}.status"
LOGFILE="${LOGDIR}/${NAME}.log"

# Initialize structured logging
log_init "healthcheck" "$NAME" "info"
log_set_file "$LOGFILE"

# Check if connection config exists
if [ ! -f "$CONFFILE" ]; then
    log_error "Connection config not found"
    echo "status=error" > "$STATUSFILE"
    exit 1
fi

. "$CONFFILE"

# Check if tun2socks process is alive
if [ -f "${RUNDIR}/${NAME}.pid" ]; then
    PID=$(cat "${RUNDIR}/${NAME}.pid")
    if ! kill -0 "$PID" 2>/dev/null; then
        log_error "tun2socks process (PID: $PID) is dead"
        echo "status=down" > "$STATUSFILE"
        echo "reason=process_dead" >> "$STATUSFILE"
        echo "timestamp=$(date +%s)" >> "$STATUSFILE"
        exit 1
    fi
else
    log_error "No PID file found — process not tracked"
    echo "status=down" > "$STATUSFILE"
    echo "reason=no_pidfile" >> "$STATUSFILE"
    echo "timestamp=$(date +%s)" >> "$STATUSFILE"
    exit 1
fi

# Check if interface exists and is up
if ! ifconfig "$IFACE" >/dev/null 2>&1; then
    log_error "Interface $IFACE does not exist"
    echo "status=down" > "$STATUSFILE"
    echo "reason=no_interface" >> "$STATUSFILE"
    echo "timestamp=$(date +%s)" >> "$STATUSFILE"
    exit 1
fi

# --- Connectivity probe through the proxy server ---
# Use PROXY_URL from .conf (includes auth credentials if configured).
# For SOCKS5, switch to socks5h:// so curl asks the proxy to resolve DNS.
case "$PROXY_TYPE" in
    socks5|socks5tls) CURL_PROXY="socks5h${PROXY_URL#socks5}" ;;
    http|https)       CURL_PROXY="$PROXY_URL" ;;
    *)                CURL_PROXY="socks5h${PROXY_URL#socks5}" ;;
esac

# Mask credentials in log output
CURL_PROXY_LOG=$(echo "$CURL_PROXY" | sed 's|://[^@]*@|://***@|')

log_debug "Probing ${TARGET} via proxy ${CURL_PROXY_LOG}..."
START_MS=$(date +%s%N 2>/dev/null || echo "0")

CURL_ERR_FILE="${RUNDIR}/${NAME}.curl_err"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    --proxy "$CURL_PROXY" \
    --connect-timeout "$TIMEOUT" \
    --max-time "$TIMEOUT" \
    "$TARGET" 2>"$CURL_ERR_FILE")
CURL_EXIT=$?

END_MS=$(date +%s%N 2>/dev/null || echo "0")

# Calculate latency
LATENCY_MS="-1"
if [ "$START_MS" != "0" ] && [ "$END_MS" != "0" ]; then
    LATENCY_NS=$((END_MS - START_MS))
    LATENCY_MS=$((LATENCY_NS / 1000000))
fi

PROBE_DETAIL="via=${CURL_PROXY_LOG} target=${TARGET} http=${HTTP_CODE}"

# Any HTTP response (even 4xx/5xx) means the proxy forwarded the request.
# Only 000 means the proxy itself is unreachable or not working.
if [ "$HTTP_CODE" != "000" ] && [ -n "$HTTP_CODE" ]; then
    rm -f "$CURL_ERR_FILE"
    log_info "Healthy — HTTP ${HTTP_CODE}, ${LATENCY_MS}ms (${PROBE_DETAIL})"
    cat > "$STATUSFILE" <<EOF
status=up
probe=${PROBE_DETAIL}
latency_ms=${LATENCY_MS}
timestamp=$(date +%s)
EOF
    exit 0
else
    CURL_ERR=$(head -1 "$CURL_ERR_FILE" 2>/dev/null)
    rm -f "$CURL_ERR_FILE"
    log_warning "Proxy unreachable — ${PROBE_DETAIL} curl_exit=${CURL_EXIT} ${CURL_ERR}"
    cat > "$STATUSFILE" <<EOF
status=down
probe=${PROBE_DETAIL}
reason=proxy_unreachable
curl_exit=${CURL_EXIT}
curl_err=${CURL_ERR}
timestamp=$(date +%s)
EOF
    exit 1
fi
