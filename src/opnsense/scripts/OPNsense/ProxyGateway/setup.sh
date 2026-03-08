#!/bin/sh

# setup.sh — Create tun device, start tun2socks, register gateway
# Called by configd: configctl proxygateway setup <name>
#
# Reads connection config from the model via inline parameters or
# from /var/run/proxygateway/<name>.conf

set -e

SCRIPT_DIR=$(dirname "$0")
RUNDIR="/var/run/proxygateway"
LOGDIR="/var/log/proxygateway"
TUN2SOCKS="/usr/local/bin/tun2socks"

# Source structured logging library
. "${SCRIPT_DIR}/lib/logging.sh"

usage() {
    echo "Usage: $0 <name> <proxy_type> <proxy_addr> <proxy_port> [options]"
    echo ""
    echo "Options:"
    echo "  --auth-user <user>       Proxy auth username"
    echo "  --auth-pass <pass>       Proxy auth password"
    echo "  --tun-addr <ip>          Local tunnel address (default: auto-assign)"
    echo "  --tun-mtu <mtu>          Tunnel MTU (default: 1500)"
    echo "  --loglevel <level>       Log level: debug|info|warn|error (default: warn)"
    echo "  --defer-routes           Skip route reconfiguration (for batch operations)"
    exit 1
}

# Parse required arguments
[ $# -lt 4 ] && usage

NAME="$1"
PROXY_TYPE="$2"
PROXY_ADDR="$3"
PROXY_PORT="$4"
shift 4

# Defaults
AUTH_USER=""
AUTH_PASS=""
TUN_ADDR=""
TUN_MTU="1500"
LOGLEVEL="warn"
DEFER_ROUTES="no"
PROXY_IFACE="wan"
SS_METHOD=""
SS_PASSWORD=""
SS_OBFS=""
SS_OBFS_HOST=""
SSH_KEY=""

# Parse optional arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --auth-user)  AUTH_USER="$2"; shift 2 ;;
        --auth-pass)  AUTH_PASS="$2"; shift 2 ;;
        --auth-pass-env)
            # Read password from environment variable for security
            AUTH_PASS="${PROXY_AUTH_PASS}"
            shift 1 ;;
        --tun-addr)   TUN_ADDR="$2"; shift 2 ;;
        --tun-mtu)    TUN_MTU="$2"; shift 2 ;;
        --proxy-iface) PROXY_IFACE="$2"; shift 2 ;;
        --ss-method)   SS_METHOD="$2"; shift 2 ;;
        --ss-password-env)
            SS_PASSWORD="${SS_AUTH_PASS}"
            shift 1 ;;
        --ss-obfs)     SS_OBFS="$2"; shift 2 ;;
        --ss-obfs-host) SS_OBFS_HOST="$2"; shift 2 ;;
        --ssh-key)     SSH_KEY="$2"; shift 2 ;;
        --defer-routes) DEFER_ROUTES="yes"; shift 1 ;;
        --loglevel)
            # tun2socks uses Go's zap logger: debug|info|warn|error|panic|fatal
            case "$2" in
                warning) LOGLEVEL="warn" ;;
                *)       LOGLEVEL="$2" ;;
            esac
            shift 2 ;;
        *)            echo "Unknown option: $1"; usage ;;
    esac
done

# Validate name (alphanumeric + underscore, max 16 chars — must match MVC model)
echo "$NAME" | grep -qE '^[a-zA-Z0-9_]{1,16}$' || {
    echo "ERROR: Invalid connection name: $NAME"
    exit 1
}

IFACE="pgw_${NAME}"
PIDFILE="${RUNDIR}/${NAME}.pid"
LOGFILE="${LOGDIR}/${NAME}.log"
CONFFILE="${RUNDIR}/${NAME}.conf"
TUNDEVFILE="${RUNDIR}/${NAME}.tundev"

# Ensure directories exist with restrictive permissions
mkdir -p -m 0750 "$RUNDIR"
mkdir -p "$LOGDIR"

# Initialize structured logging
log_init "setup" "$NAME" "$LOGLEVEL"
log_set_file "$LOGFILE"

# Check if already running
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        log_error "Connection already running (PID: $OLD_PID)"
        exit 1
    fi
fi

# Check tun2socks binary
if [ ! -x "$TUN2SOCKS" ]; then
    log_error "tun2socks binary not found at $TUN2SOCKS"
    exit 1
fi

# Auto-assign tunnel address if not specified
if [ -z "$TUN_ADDR" ]; then
    # Use a hash of the name to generate a deterministic address in 172.31.0.0/16
    HASH=$(echo -n "$NAME" | md5 | cut -c1-4)
    OCTET3=$(printf "%d" "0x$(echo "$HASH" | cut -c1-2)")
    OCTET4=$(printf "%d" "0x$(echo "$HASH" | cut -c3-4)")
    OCTET3=$(( (OCTET3 % 254) + 1 ))
    OCTET4=$(( (OCTET4 % 126) * 2 + 1 ))
    TUN_ADDR="172.31.${OCTET3}.${OCTET4}"
fi

TUN_LOCAL="${TUN_ADDR}"
# Peer address is local + 1
TUN_PEER_LAST=$(echo "$TUN_LOCAL" | awk -F. '{print $4}')
TUN_PEER_LAST=$((TUN_PEER_LAST + 1))
TUN_PEER="$(echo "$TUN_LOCAL" | awk -F. '{printf "%s.%s.%s.", $1, $2, $3}')${TUN_PEER_LAST}"

# Build proxy URL
case "$PROXY_TYPE" in
    socks5|socks5tls)
        PROXY_URL="socks5://"
        if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
            PROXY_URL="${PROXY_URL}${AUTH_USER}:${AUTH_PASS}@"
        fi
        PROXY_URL="${PROXY_URL}${PROXY_ADDR}:${PROXY_PORT}"
        ;;
    http|https)
        PROXY_URL="http://"
        if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
            PROXY_URL="${PROXY_URL}${AUTH_USER}:${AUTH_PASS}@"
        fi
        PROXY_URL="${PROXY_URL}${PROXY_ADDR}:${PROXY_PORT}"
        ;;
    ss)
        # Shadowsocks: ss://method:password@host:port/?obfs=xxx;obfs-host=xxx
        PROXY_URL="ss://"
        if [ -n "$SS_METHOD" ] && [ -n "$SS_PASSWORD" ]; then
            PROXY_URL="${PROXY_URL}${SS_METHOD}:${SS_PASSWORD}@"
        fi
        PROXY_URL="${PROXY_URL}${PROXY_ADDR}:${PROXY_PORT}"
        if [ -n "$SS_OBFS" ]; then
            PROXY_URL="${PROXY_URL}/?obfs=${SS_OBFS}"
            if [ -n "$SS_OBFS_HOST" ]; then
                PROXY_URL="${PROXY_URL};obfs-host=${SS_OBFS_HOST}"
            fi
        fi
        ;;
    ssh)
        # SSH: ssh://user:pass@host:port or ssh://host:port?privateKeyFile=xxx
        PROXY_URL="ssh://"
        if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
            PROXY_URL="${PROXY_URL}${AUTH_USER}:${AUTH_PASS}@"
        fi
        PROXY_URL="${PROXY_URL}${PROXY_ADDR}:${PROXY_PORT}"
        if [ -n "$SSH_KEY" ]; then
            PROXY_URL="${PROXY_URL}?privateKeyFile=${SSH_KEY}"
        fi
        ;;
    *)
        log_error "Unknown proxy type: $PROXY_TYPE"
        exit 1
        ;;
esac

log_separator "BEGIN SETUP"
log_info "Interface: $IFACE"
log_info "Tunnel: ${TUN_LOCAL} <-> ${TUN_PEER} (MTU: ${TUN_MTU})"
log_info "Proxy: ${PROXY_TYPE}://${PROXY_ADDR}:${PROXY_PORT}"

# Step 1: Ensure no conflicting interface exists
if ifconfig "$IFACE" >/dev/null 2>&1; then
    log_info "Destroying existing interface $IFACE for clean setup"
    ifconfig "$IFACE" destroy 2>/dev/null || true
fi

# Step 2: Start tun2socks with the final interface name directly.
log_info "Starting tun2socks (device=$IFACE, loglevel: ${LOGLEVEL})..."

# Build tun2socks command with proper quoting (no stored-in-variable expansion)
if [ "$PROXY_TYPE" = "socks5" ] || [ "$PROXY_TYPE" = "socks5tls" ] || [ "$PROXY_TYPE" = "ss" ]; then
    # SOCKS5: add UDP timeout for UDP relay support
    log_debug "Using UDP timeout (300s) for SOCKS5 proxy"
    "$TUN2SOCKS" -device "$IFACE" -proxy "$PROXY_URL" -loglevel "$LOGLEVEL" \
        -tcp-sndbuf 256KB -tcp-rcvbuf 256KB -tcp-auto-tuning \
        -udp-timeout 300s >> "$LOGFILE" 2>&1 &
else
    "$TUN2SOCKS" -device "$IFACE" -proxy "$PROXY_URL" -loglevel "$LOGLEVEL" \
        -tcp-sndbuf 256KB -tcp-rcvbuf 256KB -tcp-auto-tuning >> "$LOGFILE" 2>&1 &
fi

T2S_PID=$!
echo "$T2S_PID" > "$PIDFILE"
log_debug "tun2socks spawned with PID $T2S_PID"

# Wait for tun2socks to create the interface (poll every 0.25s, max 5s)
WAIT=0
while [ $WAIT -lt 20 ]; do
    if ! kill -0 "$T2S_PID" 2>/dev/null; then
        log_error "tun2socks exited prematurely — check ${LOGFILE} for details"
        tail -20 "$LOGFILE" 2>/dev/null || true
        rm -f "$PIDFILE"
        exit 1
    fi
    if ifconfig "$IFACE" >/dev/null 2>&1; then
        break
    fi
    sleep 0.25
    WAIT=$((WAIT + 1))
done

if ! ifconfig "$IFACE" >/dev/null 2>&1; then
    log_error "tun2socks started but interface $IFACE was not created within 5s"
    kill "$T2S_PID" 2>/dev/null || true
    rm -f "$PIDFILE"
    exit 1
fi

# Record the interface name (tun2socks owns the underlying device)
echo "$IFACE" > "$TUNDEVFILE"

# Add to proxygateway interface group
ifconfig "$IFACE" group proxygateway 2>/dev/null || true

# Step 3: Configure the interface
log_info "Configuring $IFACE: ${TUN_LOCAL} <-> ${TUN_PEER} mtu ${TUN_MTU}"
ifconfig "$IFACE" inet "$TUN_LOCAL" "$TUN_PEER" mtu "$TUN_MTU" up
log_debug "Device ${IFACE} configured: ${TUN_LOCAL}/${TUN_PEER}"

# Step 4: Write router and monitor files for OPNsense gateway auto-detection
ROUTER_FILE="/tmp/${IFACE}_router"
echo "$TUN_PEER" > "$ROUTER_FILE"
chmod 644 "$ROUTER_FILE"
log_debug "Wrote router file: ${ROUTER_FILE} -> ${TUN_PEER}"

MONITOR_FILE="/tmp/${IFACE}_monitorip"
echo "$PROXY_ADDR" > "$MONITOR_FILE"
chmod 644 "$MONITOR_FILE"
log_debug "Wrote monitor IP file: ${MONITOR_FILE} -> ${PROXY_ADDR}"

# Step 5: Save connection config for status/teardown/healthcheck
# Note: PROXY_URL contains credentials, so secure this file
cat > "$CONFFILE" <<EOF
NAME="${NAME}"
IFACE="${IFACE}"
TUN_DEV="${IFACE}"
PROXY_TYPE="${PROXY_TYPE}"
PROXY_ADDR="${PROXY_ADDR}"
PROXY_PORT="${PROXY_PORT}"
PROXY_URL="${PROXY_URL}"
TUN_LOCAL="${TUN_LOCAL}"
TUN_PEER="${TUN_PEER}"
TUN_MTU="${TUN_MTU}"
PROXY_IFACE="${PROXY_IFACE}"
PID="${T2S_PID}"
STARTED_AT="$(date +%s)"
EOF
chmod 600 "$CONFFILE"
chown root:wheel "$CONFFILE"
log_debug "Saved connection config to ${CONFFILE} (secure permissions)"

# Also secure the tundev file
chmod 600 "$TUNDEVFILE" 2>/dev/null || true

# Step 6: Trigger OPNsense route reconfiguration (unless deferred for batch operations)
if [ "$DEFER_ROUTES" = "no" ]; then
    /usr/local/sbin/configctl interface routes reconfigure >/dev/null 2>&1 || true
    log_debug "Triggered route reconfiguration"
else
    log_debug "Deferred route reconfiguration (batch mode)"
fi

log_info "Gateway peer: $TUN_PEER | PID: $T2S_PID"
log_separator "SETUP COMPLETE"
