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

RUNDIR="/var/run/proxygateway"

# Default probe target: Cloudflare anycast IP (returns 301, no DNS needed)
DEFAULT_TARGET="http://1.1.1.1/"

NAME="$1"
TARGET="${2:-$DEFAULT_TARGET}"
TIMEOUT="${3:-5}"

if [ -z "$NAME" ]; then
    echo "Usage: $0 <name> [target_url] [timeout_seconds]"
    exit 1
fi

CONFFILE="${RUNDIR}/${NAME}.conf"
STATUSFILE="${RUNDIR}/${NAME}.status"

# Check if connection config exists
if [ ! -f "$CONFFILE" ]; then
    echo "ERROR: Connection '$NAME' not found"
    echo "status=error" > "$STATUSFILE"
    exit 1
fi

. "$CONFFILE"

# Check if tun2socks process is alive
if [ -f "${RUNDIR}/${NAME}.pid" ]; then
    PID=$(cat "${RUNDIR}/${NAME}.pid")
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "FAIL: tun2socks process (PID: $PID) is dead"
        echo "status=down" > "$STATUSFILE"
        echo "reason=process_dead" >> "$STATUSFILE"
        echo "timestamp=$(date +%s)" >> "$STATUSFILE"
        exit 1
    fi
else
    echo "FAIL: No PID file found"
    echo "status=down" > "$STATUSFILE"
    echo "reason=no_pidfile" >> "$STATUSFILE"
    echo "timestamp=$(date +%s)" >> "$STATUSFILE"
    exit 1
fi

# Check if interface exists and is up
if ! ifconfig "$IFACE" >/dev/null 2>&1; then
    echo "FAIL: Interface $IFACE does not exist"
    echo "status=down" > "$STATUSFILE"
    echo "reason=no_interface" >> "$STATUSFILE"
    echo "timestamp=$(date +%s)" >> "$STATUSFILE"
    exit 1
fi

# --- Connectivity probe through the proxy ---
# Build a curl-compatible proxy URL from the connection config.
# PROXY_URL from .conf may contain auth (user:pass@host:port).
# Map proxy types to curl-supported schemes.
case "$PROXY_TYPE" in
    socks5|socks5tls) CURL_PROXY="socks5h://${PROXY_ADDR}:${PROXY_PORT}" ;;
    http|https)       CURL_PROXY="http://${PROXY_ADDR}:${PROXY_PORT}" ;;
    *)                CURL_PROXY="socks5h://${PROXY_ADDR}:${PROXY_PORT}" ;;
esac

START_MS=$(date +%s%N 2>/dev/null || echo "0")

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    --proxy "$CURL_PROXY" \
    --connect-timeout "$TIMEOUT" \
    --max-time "$TIMEOUT" \
    "$TARGET" 2>/dev/null)

END_MS=$(date +%s%N 2>/dev/null || echo "0")

# Calculate latency
LATENCY_MS="-1"
if [ "$START_MS" != "0" ] && [ "$END_MS" != "0" ]; then
    LATENCY_NS=$((END_MS - START_MS))
    LATENCY_MS=$((LATENCY_NS / 1000000))
fi

PROBE_DETAIL="via=${CURL_PROXY} target=${TARGET} http=${HTTP_CODE}"

# Any HTTP response (even 4xx/5xx) means the proxy forwarded the request.
# Only 000 means the proxy itself is unreachable or not working.
if [ "$HTTP_CODE" != "000" ] && [ -n "$HTTP_CODE" ]; then
    echo "OK: $NAME is healthy ($PROBE_DETAIL, ${LATENCY_MS}ms)"
    cat > "$STATUSFILE" <<EOF
status=up
probe=${PROBE_DETAIL}
latency_ms=${LATENCY_MS}
timestamp=$(date +%s)
EOF
    exit 0
else
    echo "FAIL: $NAME proxy unreachable ($PROBE_DETAIL)"
    cat > "$STATUSFILE" <<EOF
status=down
probe=${PROBE_DETAIL}
reason=proxy_unreachable
timestamp=$(date +%s)
EOF
    exit 1
fi
