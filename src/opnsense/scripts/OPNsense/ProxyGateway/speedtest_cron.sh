#!/bin/sh

# speedtest_cron.sh — Periodic speed test for all proxy gateway connections
# Called by cron every 5 minutes; self-gates based on configured interval.
# Tests are run sequentially to avoid bandwidth competition.

SCRIPT_DIR=$(dirname "$0")
RUNDIR="/var/run/proxygateway"
SPEEDTEST_SCRIPT="${SCRIPT_DIR}/speedtest.sh"

# Check if speed test is enabled (flag file written by proxygateway.inc)
if [ ! -f "${RUNDIR}/speedtest.enabled" ]; then
    exit 0
fi

# Read configured interval (minutes)
INTERVAL=15
if [ -f "${RUNDIR}/speedtest.interval" ]; then
    INTERVAL=$(cat "${RUNDIR}/speedtest.interval")
fi
INTERVAL_SECS=$((INTERVAL * 60))

# Fixed timeout — actual file size depends on the URL, not a config setting
TIMEOUT=60

# Read desired.json to get list of enabled connections
DESIRED="${RUNDIR}/desired.json"
if [ ! -f "$DESIRED" ]; then
    exit 0
fi

# Extract enabled connection names from desired.json
# Use simple grep/sed since jq may not be available on FreeBSD
CONNECTIONS=$(cat "$DESIRED" | \
    grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | \
    sed 's/"name"[[:space:]]*:[[:space:]]*"//;s/"//')

NOW=$(date +%s)

for NAME in $CONNECTIONS; do
    # Check if this connection has a running process
    if [ ! -f "${RUNDIR}/${NAME}.pid" ]; then
        continue
    fi

    # Skip if result is still fresh
    RESULTFILE="${RUNDIR}/${NAME}.speedtest"
    if [ -f "$RESULTFILE" ]; then
        LAST_TS=$(grep '^timestamp=' "$RESULTFILE" | head -1 | cut -d= -f2)
        if [ -n "$LAST_TS" ]; then
            AGE=$((NOW - LAST_TS))
            if [ "$AGE" -lt "$INTERVAL_SECS" ]; then
                continue
            fi
        fi
    fi

    /bin/sh "$SPEEDTEST_SCRIPT" "$NAME" "$TIMEOUT"
done
