#!/bin/sh

# clear_logs.sh — Clear proxy gateway log files
# Called by configd: configctl proxygateway clearlogs [name]
#
# If a connection name is provided, clears only that connection's log.
# Otherwise, clears all proxy gateway logs.

SCRIPT_DIR=$(dirname "$0")
LOGDIR="/var/log/proxygateway"

# Source structured logging library
. "${SCRIPT_DIR}/lib/logging.sh"

NAME="$1"

if [ -n "$NAME" ]; then
    # Validate name
    echo "$NAME" | grep -qE '^[a-zA-Z0-9_]{1,16}$' || {
        echo "ERROR: Invalid connection name: $NAME"
        exit 1
    }

    LOGFILE="${LOGDIR}/${NAME}.log"
    if [ -f "$LOGFILE" ]; then
        : > "$LOGFILE"
        echo "Cleared logs for connection: $NAME"
    else
        echo "No log file found for connection: $NAME"
    fi
else
    # Clear all logs
    CLEARED=0
    for logfile in "${LOGDIR}"/*.log; do
        [ -f "$logfile" ] || continue
        : > "$logfile"
        CLEARED=$((CLEARED + 1))
    done
    echo "Cleared $CLEARED log file(s)"
fi
