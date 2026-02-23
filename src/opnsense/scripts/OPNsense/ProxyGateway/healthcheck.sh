#!/bin/sh

# healthcheck.sh — Probe connectivity through a proxy gateway tunnel
# Called periodically by cron or configd
# Exit code: 0 = healthy, 1 = unhealthy

RUNDIR="/var/run/proxygateway"

NAME="$1"
TARGET="${2:-http://cp.cloudflare.com}"
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

# Probe connectivity through the tunnel
# Use curl with --interface to force traffic through the tunnel IP
START_MS=$(date +%s%N 2>/dev/null || echo "0")
RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
    --interface "$TUN_LOCAL" \
    --connect-timeout "$TIMEOUT" \
    --max-time "$TIMEOUT" \
    "$TARGET" 2>/dev/null)
END_MS=$(date +%s%N 2>/dev/null || echo "0")

if [ "$RESULT" = "200" ] || [ "$RESULT" = "204" ] || [ "$RESULT" = "301" ] || [ "$RESULT" = "302" ]; then
    # Calculate latency in milliseconds
    if [ "$START_MS" != "0" ] && [ "$END_MS" != "0" ]; then
        LATENCY_NS=$((END_MS - START_MS))
        LATENCY_MS=$((LATENCY_NS / 1000000))
    else
        LATENCY_MS="-1"
    fi

    echo "OK: $NAME is healthy (HTTP $RESULT, ${LATENCY_MS}ms)"
    cat > "$STATUSFILE" <<EOF
status=up
http_code=${RESULT}
latency_ms=${LATENCY_MS}
timestamp=$(date +%s)
EOF
    exit 0
else
    echo "FAIL: $NAME probe failed (HTTP $RESULT)"
    cat > "$STATUSFILE" <<EOF
status=down
http_code=${RESULT}
reason=probe_failed
timestamp=$(date +%s)
EOF
    exit 1
fi
