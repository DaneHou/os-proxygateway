#!/bin/sh

# speedtest.sh — Measure download throughput through a proxy gateway connection
# Called by configd or speedtest_cron.sh
# Exit code: 0 = success, 1 = failure
#
# Downloads a test file through the proxy and measures speed using curl.
# Results written to /var/run/proxygateway/{name}.speedtest
# History appended to /var/log/proxygateway/{name}_speedtest.log

SCRIPT_DIR=$(dirname "$0")
RUNDIR="/var/run/proxygateway"
LOGDIR="/var/log/proxygateway"

# Source structured logging library
. "${SCRIPT_DIR}/lib/logging.sh"
. "${SCRIPT_DIR}/lib/common.sh"

# Default test URL (~10MB, no browser verification)
DEFAULT_URL="http://speedtest.tele2.net/10MB.zip"

NAME="$1"
TIMEOUT="${2:-60}"
TEST_URL=""

if [ -z "$NAME" ]; then
    echo "Usage: $0 <name> [timeout]"
    exit 1
fi

# Validate name
pgw_valid_name "$NAME" || {
    echo "ERROR: Invalid connection name"
    exit 1
}

CONFFILE="${RUNDIR}/${NAME}.conf"
HISTORYFILE="${LOGDIR}/${NAME}_speedtest.log"
RESULTFILE="${RUNDIR}/${NAME}.speedtest"

# Initialize structured logging
log_init "speedtest" "$NAME" "info"
log_set_file "${LOGDIR}/${NAME}.log"

# Check if connection config exists
if [ ! -f "$CONFFILE" ]; then
    log_error "Connection config not found"
    cat > "$RESULTFILE" <<EOF
status=error
error=no_config
timestamp=$(date +%s)
EOF
    exit 1
fi

# Read only the keys we need — never source the .conf (user-controlled values)
IFACE=$(conf_get IFACE "$CONFFILE")
PROXY_TYPE=$(conf_get PROXY_TYPE "$CONFFILE")
PROXY_URL=$(conf_get PROXY_URL "$CONFFILE")
SPEED_TEST_URL=$(conf_get SPEED_TEST_URL "$CONFFILE")
IFACE="${IFACE:-pgw_${NAME}}"

# Determine test URL (from .conf or default)
if [ -z "$TEST_URL" ]; then
    TEST_URL="${SPEED_TEST_URL:-$DEFAULT_URL}"
fi
case "$TEST_URL" in
    http://*|https://*) ;;
    *) log_error "Speed test URL must be an http(s) URL"; exit 1 ;;
esac
case "$TIMEOUT" in
    ''|*[!0-9]*) TIMEOUT=60 ;;
esac

# Check if tun2socks process is alive
if [ -f "${RUNDIR}/${NAME}.pid" ]; then
    PID=$(cat "${RUNDIR}/${NAME}.pid")
    if ! kill -0 "$PID" 2>/dev/null; then
        log_error "tun2socks process (PID: $PID) is dead — skipping speed test"
        cat > "$RESULTFILE" <<EOF
status=error
error=process_dead
timestamp=$(date +%s)
EOF
        exit 1
    fi
else
    log_error "No PID file found — skipping speed test"
    cat > "$RESULTFILE" <<EOF
status=error
error=no_pidfile
timestamp=$(date +%s)
EOF
    exit 1
fi

# Build curl proxy settings (same logic as healthcheck.sh). curl can't speak
# Shadowsocks, so for ss go through the TUN interface instead.
case "$PROXY_TYPE" in
    socks5|socks5tls) CURL_CFG="proxy = \"$(pgw_curl_cfg_escape "socks5h${PROXY_URL#socks5}")\"" ;;
    http|https)       CURL_CFG="proxy = \"$(pgw_curl_cfg_escape "$PROXY_URL")\"" ;;
    *)                CURL_CFG="interface = \"$(pgw_curl_cfg_escape "$IFACE")\"" ;;
esac

log_info "Speed test starting: url=${TEST_URL} via ${PROXY_TYPE}"

# Run the download and capture metrics. Proxy settings come from a curl
# config on stdin so credentials don't appear in ps(1) output.
# %{speed_download} = average bytes/sec, %{size_download} = total bytes, %{time_total} = seconds
CURL_OUTPUT=$(printf '%s\n' "$CURL_CFG" | curl -K - -s -o /dev/null \
    -w "%{speed_download}\n%{size_download}\n%{time_total}\n%{http_code}" \
    --connect-timeout 15 \
    --max-time "$TIMEOUT" \
    -- "$TEST_URL" 2>/dev/null)
CURL_EXIT=$?

TIMESTAMP=$(date +%s)

# Parse curl output
SPEED_BPS=$(echo "$CURL_OUTPUT" | sed -n '1p')
SIZE_DL=$(echo "$CURL_OUTPUT" | sed -n '2p')
TIME_TOTAL=$(echo "$CURL_OUTPUT" | sed -n '3p')
HTTP_CODE=$(echo "$CURL_OUTPUT" | sed -n '4p')

# Handle missing/empty values
SPEED_BPS="${SPEED_BPS:-0}"
SIZE_DL="${SIZE_DL:-0}"
TIME_TOTAL="${TIME_TOTAL:-0}"
HTTP_CODE="${HTTP_CODE:-000}"

# Convert speed to Mbps (bytes/sec * 8 / 1000000)
# Use awk for floating point arithmetic
SPEED_MBPS=$(echo "$SPEED_BPS" | awk '{printf "%.2f", $1 * 8 / 1000000}')

# Determine status
if [ "$CURL_EXIT" -eq 0 ] && [ "$HTTP_CODE" != "000" ]; then
    STATUS="ok"
    log_info "Speed test complete: ${SPEED_MBPS} Mbps (${SIZE_DL} bytes in ${TIME_TOTAL}s)"
elif [ "$CURL_EXIT" -eq 28 ]; then
    # Timeout — still report partial speed
    STATUS="timeout"
    log_warning "Speed test timed out after ${TIMEOUT}s — partial: ${SPEED_MBPS} Mbps"
else
    STATUS="error"
    log_error "Speed test failed: curl_exit=${CURL_EXIT} http=${HTTP_CODE}"
fi

# Write latest result
cat > "$RESULTFILE" <<EOF
status=${STATUS}
speed_bps=${SPEED_BPS}
speed_mbps=${SPEED_MBPS}
size_bytes=${SIZE_DL}
time_total=${TIME_TOTAL}
test_url=${TEST_URL}
http_code=${HTTP_CODE}
timestamp=${TIMESTAMP}
EOF

# Append to history log as JSON-line (escape the URL for JSON)
mkdir -p "$LOGDIR"
TEST_URL_JSON=$(printf '%s' "$TEST_URL" | sed 's/[\\"]/\\&/g')
printf '{"timestamp":%s,"name":"%s","status":"%s","speed_bps":%s,"speed_mbps":%s,"size_bytes":%s,"time_total":%s,"test_url":"%s","http_code":"%s"}\n' \
    "$TIMESTAMP" "$NAME" "$STATUS" \
    "${SPEED_BPS:-0}" "${SPEED_MBPS:-0}" "${SIZE_DL:-0}" "${TIME_TOTAL:-0}" \
    "$TEST_URL_JSON" "$HTTP_CODE" >> "$HISTORYFILE"

if [ "$STATUS" = "ok" ] || [ "$STATUS" = "timeout" ]; then
    echo "OK ${SPEED_MBPS} Mbps"
    exit 0
else
    echo "FAILED curl_exit=${CURL_EXIT}"
    exit 1
fi
