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

# Default test URLs
DEFAULT_URL_INTL="https://speed.cloudflare.com/__down?bytes=10000000"
DEFAULT_URL_DOMESTIC="http://mirrors.ustc.edu.cn/ubuntu-releases/ls-lR.gz"

NAME="$1"
TEST_TYPE="${2:-international}"
SIZE_BYTES="${3:-10000000}"
TIMEOUT="${4:-60}"
TEST_URL=""

if [ -z "$NAME" ]; then
    echo "Usage: $0 <name> [test_type] [size_bytes] [timeout]"
    exit 1
fi

# Validate name
echo "$NAME" | grep -qE '^[a-zA-Z0-9_]{1,16}$' || {
    echo "ERROR: Invalid connection name: $NAME"
    exit 1
}

CONFFILE="${RUNDIR}/${NAME}.conf"
HISTORYFILE="${LOGDIR}/${NAME}_speedtest.log"

# Result file varies by test type: .speedtest (intl) or .speedtest_domestic
if [ "$TEST_TYPE" = "domestic" ]; then
    RESULTFILE="${RUNDIR}/${NAME}.speedtest_domestic"
else
    RESULTFILE="${RUNDIR}/${NAME}.speedtest"
fi

# Initialize structured logging
log_init "speedtest" "$NAME" "info"
log_set_file "${LOGDIR}/${NAME}.log"

# Check if connection config exists
if [ ! -f "$CONFFILE" ]; then
    log_error "Connection config not found"
    echo "status=error" > "$RESULTFILE"
    echo "error=no_config" >> "$RESULTFILE"
    echo "timestamp=$(date +%s)" >> "$RESULTFILE"
    exit 1
fi

. "$CONFFILE"

# Determine test URL
if [ -z "$TEST_URL" ]; then
    case "$TEST_TYPE" in
        domestic)
            TEST_URL="${SPEED_TEST_URL_DOMESTIC:-$DEFAULT_URL_DOMESTIC}"
            ;;
        *)
            TEST_URL="${SPEED_TEST_URL:-$DEFAULT_URL_INTL}"
            ;;
    esac
fi

# Check if tun2socks process is alive
if [ -f "${RUNDIR}/${NAME}.pid" ]; then
    PID=$(cat "${RUNDIR}/${NAME}.pid")
    if ! kill -0 "$PID" 2>/dev/null; then
        log_error "tun2socks process (PID: $PID) is dead — skipping speed test"
        cat > "$RESULTFILE" <<EOF
status=error
error=process_dead
test_type=${TEST_TYPE}
timestamp=$(date +%s)
EOF
        exit 1
    fi
else
    log_error "No PID file found — skipping speed test"
    cat > "$RESULTFILE" <<EOF
status=error
error=no_pidfile
test_type=${TEST_TYPE}
timestamp=$(date +%s)
EOF
    exit 1
fi

# Build curl proxy URL (same logic as healthcheck.sh)
case "$PROXY_TYPE" in
    socks5|socks5tls) CURL_PROXY="socks5h${PROXY_URL#socks5}" ;;
    http|https)       CURL_PROXY="$PROXY_URL" ;;
    *)                CURL_PROXY="socks5h${PROXY_URL#socks5}" ;;
esac

CURL_PROXY_LOG=$(echo "$CURL_PROXY" | sed 's|://[^@]*@|://***@|')

log_info "Speed test starting: type=${TEST_TYPE} url=${TEST_URL} via ${CURL_PROXY_LOG}"

# For Cloudflare speed test, override size in URL if configured
case "$TEST_URL" in
    *speed.cloudflare.com/__down*)
        TEST_URL="https://speed.cloudflare.com/__down?bytes=${SIZE_BYTES}"
        ;;
esac

# Run the download and capture metrics
# %{speed_download} = average bytes/sec, %{size_download} = total bytes, %{time_total} = seconds
CURL_OUTPUT=$(curl -s -o /dev/null \
    -w "%{speed_download}\n%{size_download}\n%{time_total}\n%{http_code}" \
    --proxy "$CURL_PROXY" \
    --connect-timeout 15 \
    --max-time "$TIMEOUT" \
    "$TEST_URL" 2>/dev/null)
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
test_type=${TEST_TYPE}
http_code=${HTTP_CODE}
timestamp=${TIMESTAMP}
EOF

# Append to history log as JSON-line
mkdir -p "$LOGDIR"
printf '{"timestamp":%s,"name":"%s","test_type":"%s","status":"%s","speed_bps":%s,"speed_mbps":%s,"size_bytes":%s,"time_total":%s,"test_url":"%s","http_code":"%s"}\n' \
    "$TIMESTAMP" "$NAME" "$TEST_TYPE" "$STATUS" \
    "${SPEED_BPS:-0}" "${SPEED_MBPS:-0}" "${SIZE_DL:-0}" "${TIME_TOTAL:-0}" \
    "$TEST_URL" "$HTTP_CODE" >> "$HISTORYFILE"

if [ "$STATUS" = "ok" ] || [ "$STATUS" = "timeout" ]; then
    echo "OK ${SPEED_MBPS} Mbps (${TEST_TYPE})"
    exit 0
else
    echo "FAILED curl_exit=${CURL_EXIT}"
    exit 1
fi
