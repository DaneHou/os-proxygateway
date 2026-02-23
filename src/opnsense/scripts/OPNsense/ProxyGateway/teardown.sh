#!/bin/sh

# teardown.sh — Stop tun2socks, destroy tun device, clean up
# Called by configd: configctl proxygateway teardown <name>

set -e

SCRIPT_DIR=$(dirname "$0")
RUNDIR="/var/run/proxygateway"
LOGDIR="/var/log/proxygateway"

# Source structured logging library
. "${SCRIPT_DIR}/lib/logging.sh"

NAME="$1"

if [ -z "$NAME" ]; then
    echo "Usage: $0 <name>"
    exit 1
fi

IFACE="pgw_${NAME}"
PIDFILE="${RUNDIR}/${NAME}.pid"
CONFFILE="${RUNDIR}/${NAME}.conf"
LOGFILE="${LOGDIR}/${NAME}.log"

# Initialize structured logging
log_init "teardown" "$NAME" "info"
log_set_file "$LOGFILE"

log_separator "BEGIN TEARDOWN"

# Step 1: Kill tun2socks process
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        log_info "Stopping tun2socks (PID: $PID)..."
        kill "$PID"
        # Wait for graceful shutdown (max 5 seconds)
        WAIT=0
        while kill -0 "$PID" 2>/dev/null && [ $WAIT -lt 5 ]; do
            sleep 1
            WAIT=$((WAIT + 1))
        done
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            log_warning "Graceful shutdown timed out — force killing tun2socks"
            kill -9 "$PID" 2>/dev/null || true
        else
            log_info "tun2socks stopped gracefully"
        fi
    else
        log_warning "PID file exists but process $PID is not running"
    fi
    rm -f "$PIDFILE"
else
    log_info "No PID file found — process may already be stopped"
fi

# Step 2: Remove router file (deregisters gateway)
# Updated to use /var/run for consistency with setup.sh
rm -f "/var/run/${IFACE}_router"
rm -f "/var/run/${IFACE}_routerv6"
# Also remove old /tmp files for backward compatibility
rm -f "/tmp/${IFACE}_router"
rm -f "/tmp/${IFACE}_routerv6"
log_debug "Removed router files"

# Step 3: Destroy tun interface
if ifconfig "$IFACE" >/dev/null 2>&1; then
    log_info "Destroying interface ${IFACE}..."
    ifconfig "$IFACE" destroy
else
    log_debug "Interface ${IFACE} does not exist — nothing to destroy"
fi

# Step 4: Clean up config and device tracking files
rm -f "$CONFFILE"
rm -f "${RUNDIR}/${NAME}.tundev"
rm -f "${RUNDIR}/${NAME}.status"
log_debug "Removed config and tracking files"

# Step 5: Trigger OPNsense route reconfiguration
/usr/local/sbin/configctl interface routes reconfigure >/dev/null 2>&1 || true
log_debug "Triggered route reconfiguration"

log_separator "TEARDOWN COMPLETE"
