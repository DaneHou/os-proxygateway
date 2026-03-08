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

# Read configured test size
SIZE_BYTES=10000000
if [ -f "${RUNDIR}/speedtest.size" ]; then
    SIZE_BYTES=$(cat "${RUNDIR}/speedtest.size")
fi

# Calculate timeout based on size (allow ~100KB/s minimum + 15s connect)
TIMEOUT=$(echo "$SIZE_BYTES" | awk '{t = int($1 / 100000) + 15; if (t > 120) t = 120; print t}')

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

# Run speed test if result file is stale or missing
run_if_stale() {
    _resultfile="$1"
    _name="$2"
    _type="$3"

    if [ -f "$_resultfile" ]; then
        _last_ts=$(grep '^timestamp=' "$_resultfile" | head -1 | cut -d= -f2)
        if [ -n "$_last_ts" ]; then
            _age=$((NOW - _last_ts))
            if [ "$_age" -lt "$INTERVAL_SECS" ]; then
                return
            fi
        fi
    fi

    /bin/sh "$SPEEDTEST_SCRIPT" "$_name" "$_type" "$SIZE_BYTES" "$TIMEOUT"
}

for NAME in $CONNECTIONS; do
    # Check if this connection has a running process
    if [ ! -f "${RUNDIR}/${NAME}.pid" ]; then
        continue
    fi

    # Test international if result is stale or missing
    run_if_stale "${RUNDIR}/${NAME}.speedtest" "$NAME" "international"

    # Test domestic if result is stale or missing
    run_if_stale "${RUNDIR}/${NAME}.speedtest_domestic" "$NAME" "domestic"
done
