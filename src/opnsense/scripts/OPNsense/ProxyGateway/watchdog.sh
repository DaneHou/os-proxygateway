#!/bin/sh

# watchdog.sh — Check if watchdog is enabled, then run watchdog.py
# Called by configd: configctl proxygateway watchdog
# Called by cron every minute

SCRIPT_DIR=$(dirname "$0")
RUNDIR="/var/run/proxygateway"
LOGDIR="/var/log/proxygateway"
WATCHDOG_LOG="${LOGDIR}/watchdog.log"

mkdir -p "$LOGDIR"

# Check if the plugin is globally enabled and watchdog is on.
# Read from desired.json metadata (avoids loading PHP in cron).
# The flag file is written by reconfigureAction / boot handler.
if [ ! -f "${RUNDIR}/watchdog.enabled" ]; then
    exit 0
fi

# Quick shell-level PID liveness check — skip Python if everything is healthy
NEED_RESTART=0
for pidfile in "${RUNDIR}"/*.pid; do
    [ -f "$pidfile" ] || continue
    PID=$(cat "$pidfile")
    if ! kill -0 "$PID" 2>/dev/null; then
        NEED_RESTART=1
        break
    fi
done

# Also check: enabled connections missing a PID file
if [ "$NEED_RESTART" = "0" ]; then
    EXPECTED=$(grep -c '"enabled": "1"' "${RUNDIR}/desired.json" 2>/dev/null || echo 0)
    ACTUAL=$(ls "${RUNDIR}"/*.pid 2>/dev/null | wc -l | tr -d ' ')
    [ "$ACTUAL" -lt "$EXPECTED" ] && NEED_RESTART=1
fi

if [ "$NEED_RESTART" = "0" ]; then
    # Route-to integrity check: if approuter rules exist but none have
    # route-to for pgw_* gateways, a filter reload during gateway bounce
    # dropped the routing directives. Trigger reload to restore them.
    APPROUTER_RULES=$(/sbin/pfctl -sr 2>/dev/null | grep -c "approuter_" || echo 0)
    APPROUTER_ROUTETO=$(/sbin/pfctl -sr 2>/dev/null | grep "approuter_" | grep -c "route-to" || echo 0)

    if [ "$APPROUTER_RULES" -gt 0 ] && [ "$APPROUTER_ROUTETO" -eq 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') route-to missing from approuter rules, reloading filter" >> "$WATCHDOG_LOG"
        /usr/local/bin/configctl filter reload >> "$WATCHDOG_LOG" 2>&1
    fi

    exit 0
fi

# A process is dead or missing — invoke Python for restart logic
/usr/local/bin/python3 "${SCRIPT_DIR}/watchdog.py" >> "$WATCHDOG_LOG" 2>&1
