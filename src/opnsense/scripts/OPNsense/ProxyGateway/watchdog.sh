#!/bin/sh

# watchdog.sh — Check if watchdog is enabled, then run watchdog.py
# Called by configd: configctl proxygateway watchdog
# Called by cron every minute

SCRIPT_DIR=$(dirname "$0")
RUNDIR="/var/run/proxygateway"
LOGDIR="/var/log/proxygateway"
WATCHDOG_LOG="${LOGDIR}/watchdog.log"

. "${SCRIPT_DIR}/lib/common.sh"

mkdir -p "$LOGDIR"

# Check if the plugin is globally enabled and watchdog is on.
# Read from desired.json metadata (avoids loading PHP in cron).
# The flag file is written by reconfigureAction / boot handler.
if [ ! -f "${RUNDIR}/watchdog.enabled" ]; then
    exit 0
fi

# Route-to integrity check: if approuter rules exist but none have
# route-to for pgw_* gateways, a filter reload during gateway bounce
# dropped the routing directives. Trigger reload to restore them.
APPROUTER_RULES=$(/sbin/pfctl -sr 2>/dev/null | grep -c "approuter_")
APPROUTER_ROUTETO=$(/sbin/pfctl -sr 2>/dev/null | grep "approuter_" | grep -c "route-to")

if [ "${APPROUTER_RULES:-0}" -gt 0 ] && [ "${APPROUTER_ROUTETO:-0}" -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') route-to missing from approuter rules, reloading filter" >> "$WATCHDOG_LOG"
    /usr/local/sbin/configctl filter reload >> "$WATCHDOG_LOG" 2>&1
fi

# Always run watchdog.py: besides restarting dead processes it runs the
# periodic health checks that drive failover and force-down, which are
# needed precisely when every tun2socks process is still alive.
# lockf -t 0: skip this tick if the previous run or a reconfigure still
# holds the lock, instead of piling up overlapping runs.
/usr/bin/lockf -k -s -t 0 "$PGW_LOCKFILE" \
    /usr/local/bin/python3 "${SCRIPT_DIR}/watchdog.py" >> "$WATCHDOG_LOG" 2>&1
