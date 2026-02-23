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

# Parse optional arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --auth-user)  AUTH_USER="$2"; shift 2 ;;
        --auth-pass)  AUTH_PASS="$2"; shift 2 ;;
        --tun-addr)   TUN_ADDR="$2"; shift 2 ;;
        --tun-mtu)    TUN_MTU="$2"; shift 2 ;;
        --dns-mode)   DNS_MODE="$2"; shift 2 ;;
        --dns-server) DNS_SERVER="$2"; shift 2 ;;
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

# Check if already running
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "ERROR: Connection '$NAME' is already running (PID: $(cat "$PIDFILE"))"
    exit 1
fi

# Check tun2socks binary
if [ ! -x "$TUN2SOCKS" ]; then
    echo "ERROR: tun2socks binary not found at $TUN2SOCKS"
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
    *)         echo "ERROR: Unknown proxy type: $PROXY_TYPE"; exit 1 ;;
esac

if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
    PROXY_URL="${PROXY_URL}${AUTH_USER}:${AUTH_PASS}@"
fi
PROXY_URL="${PROXY_URL}${PROXY_ADDR}:${PROXY_PORT}"

echo "=== Setting up proxy gateway: $NAME ==="
echo "Interface: $IFACE"
echo "Tunnel: ${TUN_LOCAL} <-> ${TUN_PEER}"
echo "Proxy: ${PROXY_TYPE}://${PROXY_ADDR}:${PROXY_PORT}"

# Step 1: Create tun device
# On FreeBSD, tun devices must be created via the tun cloner, then renamed.
# "ifconfig <custom_name> create" does NOT work for tun devices.
# We create a tunN device, rename it, and pass the original name to tun2socks
# so it can open /dev/tunN (which still exists after renaming).
TUN_DEV=""
if ifconfig "$IFACE" >/dev/null 2>&1; then
    echo "Interface $IFACE already exists"
    # Read saved tun device name (created by proxygateway_prepare or previous run)
    if [ -f "$TUNDEVFILE" ]; then
        TUN_DEV=$(cat "$TUNDEVFILE")
        echo "Using saved tun device: $TUN_DEV"
    else
        # Unknown original device; destroy and recreate for clean state
        echo "No saved tun device found, recreating..."
        ifconfig "$IFACE" destroy 2>/dev/null || true
    fi
fi

if [ -z "$TUN_DEV" ] || ! [ -c "/dev/${TUN_DEV}" ]; then
    echo "Creating tun device..."
    TUN_DEV=$(ifconfig tun create)
    if [ -z "$TUN_DEV" ]; then
        echo "ERROR: Failed to create tun device"
        exit 1
    fi
    echo "Created $TUN_DEV, renaming to $IFACE..."
    ifconfig "$TUN_DEV" name "$IFACE" || {
        echo "ERROR: Failed to rename $TUN_DEV to $IFACE"
        ifconfig "$TUN_DEV" destroy 2>/dev/null || true
        exit 1
    }
    echo "$TUN_DEV" > "$TUNDEVFILE"
fi

# Add to proxygateway interface group
ifconfig "$IFACE" group proxygateway 2>/dev/null || true

# Configure tunnel IP addresses
echo "Configuring $IFACE: ${TUN_LOCAL} <-> ${TUN_PEER} mtu ${TUN_MTU}"
ifconfig "$IFACE" inet "$TUN_LOCAL" "$TUN_PEER" mtu "$TUN_MTU" up

# Step 2: Start tun2socks
# Pass the original tun device name (e.g., tun0) so tun2socks opens /dev/tun0.
# The /dev/tunN node persists even after the interface is renamed to pgw_xxx.
echo "Starting tun2socks (device=$TUN_DEV, proxy=$PROXY_URL)..."
$TUN2SOCKS \
    -device "$TUN_DEV" \
    -proxy "$PROXY_URL" \
    -loglevel "$LOGLEVEL" \
    >> "$LOGFILE" 2>&1 &

T2S_PID=$!
echo "$T2S_PID" > "$PIDFILE"

# Wait briefly and verify the process is still alive
sleep 1
if ! kill -0 "$T2S_PID" 2>/dev/null; then
    echo "ERROR: tun2socks failed to start. Check ${LOGFILE}"
    echo "--- Last 20 lines of log ---"
    tail -20 "$LOGFILE" 2>/dev/null || true
    rm -f "$PIDFILE" "$TUNDEVFILE"
    ifconfig "$IFACE" destroy 2>/dev/null || true
    exit 1
fi

# Step 3: Write router file for OPNsense gateway auto-detection
echo "$TUN_PEER" > "/tmp/${IFACE}_router"

# Step 4: Save connection config for status/teardown
cat > "$CONFFILE" <<EOF
NAME="${NAME}"
IFACE="${IFACE}"
TUN_DEV="${TUN_DEV}"
PROXY_TYPE="${PROXY_TYPE}"
PROXY_ADDR="${PROXY_ADDR}"
PROXY_PORT="${PROXY_PORT}"
TUN_LOCAL="${TUN_LOCAL}"
TUN_PEER="${TUN_PEER}"
TUN_MTU="${TUN_MTU}"
DNS_MODE="${DNS_MODE}"
DNS_SERVER="${DNS_SERVER}"
PID="${T2S_PID}"
EOF

# Step 5: Trigger OPNsense route reconfiguration
/usr/local/sbin/configctl interface routes reconfigure >/dev/null 2>&1 || true

echo "=== Proxy gateway '$NAME' is UP ==="
echo "Gateway peer: $TUN_PEER"
echo "PID: $T2S_PID"
echo "Log: $LOGFILE"
