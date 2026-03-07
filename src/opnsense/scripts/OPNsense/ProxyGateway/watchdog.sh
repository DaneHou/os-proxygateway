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

# Run the watchdog, append to log
/usr/local/bin/python3 "${SCRIPT_DIR}/watchdog.py" >> "$WATCHDOG_LOG" 2>&1
