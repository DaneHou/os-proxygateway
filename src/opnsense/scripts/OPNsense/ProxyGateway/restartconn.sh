#!/bin/sh

# restartconn.sh — Start one connection whose tun2socks/interface is down.
# Called by configd: configctl proxygateway restartconn <name>
# (the "fix" action of the healthcheck for the tun2socks/interface checks).
#
# Idempotent and config.xml-free: a running connection is left alone, a dead
# one is set up again from desired.json (watchdog.py --restart). The name is
# validated here and again in Python against the enabled connections.
# Prints one JSON line; log lines go to watchdog.log.

SCRIPT_DIR=$(dirname "$0")
LOGDIR="/var/log/proxygateway"
WATCHDOG_LOG="${LOGDIR}/watchdog.log"

. "${SCRIPT_DIR}/lib/common.sh"

if ! pgw_valid_name "$1"; then
    echo '{"status":"error","message":"invalid connection name"}'
    exit 1
fi

mkdir -p "$LOGDIR"

# Same lock as reconfigure.sh / watchdog.sh: never race a setup/teardown.
/usr/bin/lockf -k -s -t 60 "$PGW_LOCKFILE" \
    /usr/local/bin/python3 "${SCRIPT_DIR}/watchdog.py" --restart "$1" 2>> "$WATCHDOG_LOG"
RC=$?
if [ "$RC" -eq 75 ]; then
    echo '{"status":"error","message":"busy: reconfigure or watchdog is running, try again"}'
fi
exit "$RC"
