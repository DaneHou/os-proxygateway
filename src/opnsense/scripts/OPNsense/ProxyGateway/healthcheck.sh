#!/bin/sh

# healthcheck.sh — Probe connectivity through a proxy gateway tunnel
# Called periodically by cron or configd
# Exit code: 0 = healthy, 1 = unhealthy
#
# Tests connectivity using TCP connection to well-known anycast IP addresses.
# This avoids dependence on DNS resolution and is not affected by country-level
# domain blocking. Falls back to HTTP probe if a custom target URL is configured.

RUNDIR="/var/run/proxygateway"

# Default TCP probe targets: well-known anycast DNS servers (IP:port)
# These are operated globally and reachable from virtually every country.
DEFAULT_TCP_TARGETS="1.1.1.1:53 8.8.8.8:53 9.9.9.9:53"

NAME="$1"
TARGET="${2:-}"
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

# --- Connectivity probe ---
# If a custom HTTP target is configured, use curl. Otherwise use TCP probes
# to well-known anycast IPs which work universally across countries.

probe_tcp() {
    # TCP connect test using nc (netcat), bound to the tunnel source IP.
    # Succeeds if ANY of the targets respond.
    for ENTRY in $DEFAULT_TCP_TARGETS; do
        HOST=$(echo "$ENTRY" | cut -d: -f1)
        PORT=$(echo "$ENTRY" | cut -d: -f2)
        if nc -z -w "$TIMEOUT" -s "$TUN_LOCAL" "$HOST" "$PORT" 2>/dev/null; then
            echo "$HOST:$PORT"
            return 0
        fi
    done
    return 1
}

probe_http() {
    curl -s -o /dev/null -w "%{http_code}" \
        --interface "$TUN_LOCAL" \
        --connect-timeout "$TIMEOUT" \
        --max-time "$TIMEOUT" \
        "$1" 2>/dev/null
}

START_MS=$(date +%s%N 2>/dev/null || echo "0")

if [ -n "$TARGET" ]; then
    # Custom HTTP target configured — use curl probe
    HTTP_CODE=$(probe_http "$TARGET")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "204" ] || \
       [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
        PROBE_OK=1
        PROBE_DETAIL="http=$HTTP_CODE target=$TARGET"
    else
        PROBE_OK=0
        PROBE_DETAIL="http=$HTTP_CODE target=$TARGET"
    fi
else
    # Default: TCP connectivity test to anycast DNS IPs
    REACHED=$(probe_tcp)
    if [ $? -eq 0 ]; then
        PROBE_OK=1
        PROBE_DETAIL="tcp=$REACHED"
    else
        PROBE_OK=0
        PROBE_DETAIL="tcp=none_reachable targets=\"$DEFAULT_TCP_TARGETS\""
    fi
fi

END_MS=$(date +%s%N 2>/dev/null || echo "0")

# Calculate latency
LATENCY_MS="-1"
if [ "$START_MS" != "0" ] && [ "$END_MS" != "0" ]; then
    LATENCY_NS=$((END_MS - START_MS))
    LATENCY_MS=$((LATENCY_NS / 1000000))
fi

if [ "$PROBE_OK" = "1" ]; then
    echo "OK: $NAME is healthy ($PROBE_DETAIL, ${LATENCY_MS}ms)"
    cat > "$STATUSFILE" <<EOF
status=up
probe=${PROBE_DETAIL}
latency_ms=${LATENCY_MS}
timestamp=$(date +%s)
EOF
    exit 0
else
    echo "FAIL: $NAME probe failed ($PROBE_DETAIL)"
    cat > "$STATUSFILE" <<EOF
status=down
probe=${PROBE_DETAIL}
reason=probe_failed
timestamp=$(date +%s)
EOF
    exit 1
fi
