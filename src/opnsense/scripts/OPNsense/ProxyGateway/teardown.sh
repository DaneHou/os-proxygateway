#!/bin/sh

# teardown.sh — Stop tun2socks, destroy tun device, clean up
# Called by configd: configctl proxygateway teardown <name>

set -e

RUNDIR="/var/run/proxygateway"
LOGDIR="/var/log/proxygateway"

NAME="$1"

if [ -z "$NAME" ]; then
    echo "Usage: $0 <name>"
    exit 1
fi

IFACE="pgw_${NAME}"
PIDFILE="${RUNDIR}/${NAME}.pid"
CONFFILE="${RUNDIR}/${NAME}.conf"

echo "=== Tearing down proxy gateway: $NAME ==="

# Step 1: Kill tun2socks process
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping tun2socks (PID: $PID)..."
        kill "$PID"
        # Wait for graceful shutdown (max 5 seconds)
        WAIT=0
        while kill -0 "$PID" 2>/dev/null && [ $WAIT -lt 5 ]; do
            sleep 1
            WAIT=$((WAIT + 1))
        done
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing tun2socks..."
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$PIDFILE"
fi

# Step 2: Remove router file (deregisters gateway)
rm -f "/tmp/${IFACE}_router"
rm -f "/tmp/${IFACE}_routerv6"

# Step 3: Destroy tun interface
if ifconfig "$IFACE" >/dev/null 2>&1; then
    echo "Destroying interface ${IFACE}..."
    ifconfig "$IFACE" destroy
fi

# Step 4: Clean up config file
rm -f "$CONFFILE"

# Step 5: Trigger OPNsense route reconfiguration
/usr/local/sbin/configctl interface routes reconfigure 2>/dev/null || true

echo "=== Proxy gateway '$NAME' is DOWN ==="
