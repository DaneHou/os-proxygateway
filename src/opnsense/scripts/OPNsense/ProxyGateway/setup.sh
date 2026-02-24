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
    echo "  --dns-mode <mode>        DNS mode: tunnel|custom (default: tunnel)"
    echo "  --dns-server <ip>        Custom DNS server (requires --dns-mode custom)"
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
DNS_MODE="tunnel"
DNS_SERVER=""
LOGLEVEL="warn"
DEFER_ROUTES="no"
PROXY_IFACE="wan"

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
        --dns-mode)   DNS_MODE="$2"; shift 2 ;;
        --dns-server) DNS_SERVER="$2"; shift 2 ;;
        --proxy-iface) PROXY_IFACE="$2"; shift 2 ;;
        --defer-routes) DEFER_ROUTES="yes"; shift 1 ;;
        --loglevel)
            # tun2socks uses Go's zap logger: debug|info|warn|error|panic|fatal
            # Map user-friendly "warning" to "warn" for compatibility
            case "$2" in
                warning) LOGLEVEL="warn" ;;
                *)       LOGLEVEL="$2" ;;
            esac
            shift 2 ;;
        *)            echo "Unknown option: $1"; usage ;;
    esac
done

# Validate name (alphanumeric + underscore/hyphen, max 16 chars)
echo "$NAME" | grep -qE '^[a-zA-Z0-9_-]{1,16}$' || {
    echo "ERROR: Invalid connection name: $NAME"
    exit 1
}

IFACE="pgw_${NAME}"
PIDFILE="${RUNDIR}/${NAME}.pid"
LOGFILE="${LOGDIR}/${NAME}.log"
CONFFILE="${RUNDIR}/${NAME}.conf"
TUNDEVFILE="${RUNDIR}/${NAME}.tundev"

# Ensure directories exist
mkdir -p "$RUNDIR" "$LOGDIR"

# Initialize structured logging
log_init "setup" "$NAME" "$LOGLEVEL"
log_set_file "$LOGFILE"

# Check if already running
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    log_error "Connection already running (PID: $(cat "$PIDFILE"))"
    exit 1
fi

# Check tun2socks binary
if [ ! -x "$TUN2SOCKS" ]; then
    log_error "tun2socks binary not found at $TUN2SOCKS"
    exit 1
fi

# Auto-assign tunnel address if not specified
if [ -z "$TUN_ADDR" ]; then
    # Use a hash of the name to generate a deterministic address in 172.31.0.0/16
    # This avoids conflicts between different named connections
    HASH=$(echo -n "$NAME" | md5 | cut -c1-4)
    OCTET3=$(printf "%d" "0x$(echo "$HASH" | cut -c1-2)")
    OCTET4=$(printf "%d" "0x$(echo "$HASH" | cut -c3-4)")
    # Ensure octets are in valid range (1-254) and even for .1/.2 pair
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
    socks5)    PROXY_URL="socks5://" ;;
    socks5tls) PROXY_URL="socks5://" ;;  # TLS handled via tun2socks flag
    http)      PROXY_URL="http://" ;;
    https)     PROXY_URL="http://" ;;     # TLS handled via tun2socks flag
    *)         log_error "Unknown proxy type: $PROXY_TYPE"; exit 1 ;;
esac

if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
    PROXY_URL="${PROXY_URL}${AUTH_USER}:${AUTH_PASS}@"
fi
PROXY_URL="${PROXY_URL}${PROXY_ADDR}:${PROXY_PORT}"

log_separator "BEGIN SETUP"
log_info "Interface: $IFACE"
log_info "Tunnel: ${TUN_LOCAL} <-> ${TUN_PEER} (MTU: ${TUN_MTU})"
log_info "Proxy: ${PROXY_TYPE}://${PROXY_ADDR}:${PROXY_PORT}"
log_info "DNS mode: ${DNS_MODE}${DNS_SERVER:+ (server: $DNS_SERVER)}"

# Step 1: Create tun device
# On FreeBSD, tun devices must be created via the tun cloner, then renamed.
# "ifconfig <custom_name> create" does NOT work for tun devices.
# We create a tunN device, rename it, and pass the original name to tun2socks
# so it can open /dev/tunN (which still exists after renaming).
TUN_DEV=""
if ifconfig "$IFACE" >/dev/null 2>&1; then
    log_info "Interface $IFACE already exists"
    if [ -f "$TUNDEVFILE" ]; then
        TUN_DEV=$(cat "$TUNDEVFILE")
        log_debug "Using saved tun device: $TUN_DEV"
    else
        log_info "No saved tun device found, recreating..."
        ifconfig "$IFACE" destroy 2>/dev/null || true
    fi
fi

if [ -z "$TUN_DEV" ] || ! [ -c "/dev/${TUN_DEV}" ]; then
    log_info "Creating tun device..."
    TUN_DEV=$(ifconfig tun create)
    if [ -z "$TUN_DEV" ]; then
        log_error "Failed to create tun device"
        exit 1
    fi
    log_debug "Created $TUN_DEV, renaming to $IFACE..."
    ifconfig "$TUN_DEV" name "$IFACE" || {
        log_error "Failed to rename $TUN_DEV to $IFACE"
        ifconfig "$TUN_DEV" destroy 2>/dev/null || true
        exit 1
    }
    echo "$TUN_DEV" > "$TUNDEVFILE"
fi

# Add to proxygateway interface group
ifconfig "$IFACE" group proxygateway 2>/dev/null || true

log_info "Configuring $IFACE: ${TUN_LOCAL} <-> ${TUN_PEER} mtu ${TUN_MTU}"
ifconfig "$IFACE" inet "$TUN_LOCAL" "$TUN_PEER" mtu "$TUN_MTU" up
log_debug "Device ${IFACE} configured: ${TUN_LOCAL}/${TUN_PEER}"

# Step 2: Start tun2socks
# Pass the original tun device name (e.g., tun0) so tun2socks opens /dev/tun0.
# The /dev/tunN node persists even after the interface is renamed to pgw_xxx.
log_info "Starting tun2socks (device=$TUN_DEV, loglevel: ${LOGLEVEL})..."

# Build tun2socks command with optional UDP timeout
TUN2SOCKS_CMD="$TUN2SOCKS -device $TUN_DEV -proxy $PROXY_URL -loglevel $LOGLEVEL"

# For SOCKS5 proxies, add UDP timeout to ensure UDP relay works properly
# This is especially important for Tailscale and other SOCKS5 proxies that support UDP
if [ "$PROXY_TYPE" = "socks5" ] || [ "$PROXY_TYPE" = "socks5tls" ]; then
    # Set UDP timeout to 5 minutes (300s) to keep UDP associations alive
    # This helps with DNS and other UDP-based protocols
    TUN2SOCKS_CMD="$TUN2SOCKS_CMD -udp-timeout 300s"
    log_debug "Added UDP timeout (300s) for SOCKS5 proxy"
fi

$TUN2SOCKS_CMD >> "$LOGFILE" 2>&1 &

T2S_PID=$!
echo "$T2S_PID" > "$PIDFILE"
log_debug "tun2socks spawned with PID $T2S_PID"

# Wait briefly and verify the process is still alive
sleep 0.1
if ! kill -0 "$T2S_PID" 2>/dev/null; then
    log_error "tun2socks failed to start — check ${LOGFILE} for details"
    tail -20 "$LOGFILE" 2>/dev/null || true
    rm -f "$PIDFILE" "$TUNDEVFILE"
    ifconfig "$IFACE" destroy 2>/dev/null || true
    exit 1
fi

# Step 3: Write router and monitor files for OPNsense gateway auto-detection
# OPNsense's Autoconf::getRouter() reads from /tmp/{interface}_router
ROUTER_FILE="/tmp/${IFACE}_router"
echo "$TUN_PEER" > "$ROUTER_FILE"
chmod 644 "$ROUTER_FILE"
log_debug "Wrote router file: ${ROUTER_FILE} -> ${TUN_PEER}"

# Write monitor IP file for dpinger health checks.
# Use the proxy server address as the monitor target — it's reachable via
# the physical interface without going through the TUN, making ICMP pings
# reliable (SOCKS5 does not natively support ICMP, so pinging the TUN peer
# through tun2socks would be unreliable).
MONITOR_FILE="/tmp/${IFACE}_monitorip"
echo "$PROXY_ADDR" > "$MONITOR_FILE"
chmod 644 "$MONITOR_FILE"
log_debug "Wrote monitor IP file: ${MONITOR_FILE} -> ${PROXY_ADDR}"

# Step 4: Save connection config for status/teardown/healthcheck
# Note: PROXY_URL contains credentials, so secure this file
cat > "$CONFFILE" <<EOF
NAME="${NAME}"
IFACE="${IFACE}"
TUN_DEV="${TUN_DEV}"
PROXY_TYPE="${PROXY_TYPE}"
PROXY_ADDR="${PROXY_ADDR}"
PROXY_PORT="${PROXY_PORT}"
PROXY_URL="${PROXY_URL}"
TUN_LOCAL="${TUN_LOCAL}"
TUN_PEER="${TUN_PEER}"
TUN_MTU="${TUN_MTU}"
DNS_MODE="${DNS_MODE}"
DNS_SERVER="${DNS_SERVER}"
PROXY_IFACE="${PROXY_IFACE}"
PID="${T2S_PID}"
EOF
# Secure file permissions: owner (root) read/write only
chmod 600 "$CONFFILE"
chown root:wheel "$CONFFILE"
log_debug "Saved connection config to ${CONFFILE} (secure permissions)"

# Also secure the tundev file
chmod 600 "$TUNDEVFILE" 2>/dev/null || true

# Step 5: Trigger OPNsense route reconfiguration (unless deferred for batch operations)
if [ "$DEFER_ROUTES" = "no" ]; then
    /usr/local/sbin/configctl interface routes reconfigure >/dev/null 2>&1 || true
    log_debug "Triggered route reconfiguration"
else
    log_debug "Deferred route reconfiguration (batch mode)"
fi

log_info "Gateway peer: $TUN_PEER | PID: $T2S_PID"
log_separator "SETUP COMPLETE"
