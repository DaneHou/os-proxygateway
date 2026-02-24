#!/bin/sh

# logging.sh — Shared structured logging library for Proxy Gateway scripts
#
# Usage:
#   . /usr/local/opnsense/scripts/OPNsense/ProxyGateway/lib/logging.sh
#   log_init "connection_name"
#   log_info "Message here"
#   log_error "Something failed"
#
# Log Format:
#   2026-02-23T14:30:00Z [INFO ] [setup    ] [conn_name] Message text
#
# Environment:
#   LOG_COMPONENT  — Set automatically by log_init (setup, teardown, etc.)
#   LOG_CONNECTION  — Connection name, set by log_init
#   LOG_LEVEL      — Minimum level to output: debug|info|warning|error (default: info)
#   LOG_FILE       — If set, logs are also appended to this file

LOGDIR="/var/log/proxygateway"

# Numeric log levels for comparison
_LOG_LEVEL_DEBUG=0
_LOG_LEVEL_INFO=1
_LOG_LEVEL_WARNING=2
_LOG_LEVEL_ERROR=3

# Internal state
_LOG_COMPONENT="unknown"
_LOG_CONNECTION="-"
_LOG_MIN_LEVEL=$_LOG_LEVEL_INFO
_LOG_FILE=""
_LOG_TIMESTAMP_CACHE=""
_LOG_TIMESTAMP_EPOCH=0

# Initialize logging for a script
# Usage: log_init <component> [connection_name] [log_level]
log_init() {
    _LOG_COMPONENT="$1"
    _LOG_CONNECTION="${2:--}"
    _log_set_level "${3:-info}"
    if [ -n "$_LOG_CONNECTION" ] && [ "$_LOG_CONNECTION" != "-" ]; then
        mkdir -p "$LOGDIR"
        _LOG_FILE="${LOGDIR}/${_LOG_CONNECTION}.log"
    fi
}

# Set the file to log to (override auto-detection)
log_set_file() {
    _LOG_FILE="$1"
}

# Internal: set minimum log level
_log_set_level() {
    case "$1" in
        debug)   _LOG_MIN_LEVEL=$_LOG_LEVEL_DEBUG ;;
        info)    _LOG_MIN_LEVEL=$_LOG_LEVEL_INFO ;;
        warning) _LOG_MIN_LEVEL=$_LOG_LEVEL_WARNING ;;
        error)   _LOG_MIN_LEVEL=$_LOG_LEVEL_ERROR ;;
        *)       _LOG_MIN_LEVEL=$_LOG_LEVEL_INFO ;;
    esac
}

# Internal: format and output a log line
# Usage: _log_emit <LEVEL> <level_num> <message>
_log_emit() {
    _level_label="$1"
    _level_num="$2"
    shift 2
    _message="$*"

    # Check minimum level
    [ "$_level_num" -lt "$_LOG_MIN_LEVEL" ] && return 0

    # Format timestamp - cache it to avoid calling date multiple times per second
    _current_epoch=$(date +%s 2>/dev/null || echo "0")
    if [ "$_current_epoch" != "$_LOG_TIMESTAMP_EPOCH" ]; then
        _LOG_TIMESTAMP_CACHE=$(date -u "+%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date "+%Y-%m-%dT%H:%M:%S")
        _LOG_TIMESTAMP_EPOCH="$_current_epoch"
    fi
    _timestamp="$_LOG_TIMESTAMP_CACHE"

    # Pad component to 10 chars for alignment
    _comp=$(printf "%-10s" "$_LOG_COMPONENT")

    # Pad connection to 16 chars for alignment
    _conn=$(printf "%-16s" "$_LOG_CONNECTION")

    _line="${_timestamp} [${_level_label}] [${_comp}] [${_conn}] ${_message}"

    # Output to stdout
    echo "$_line"

    # Append to file if configured
    if [ -n "$_LOG_FILE" ]; then
        echo "$_line" >> "$_LOG_FILE"
    fi
}

# Public logging functions
log_debug() {
    _log_emit "DEBUG" "$_LOG_LEVEL_DEBUG" "$@"
}

log_info() {
    _log_emit "INFO " "$_LOG_LEVEL_INFO" "$@"
}

log_warning() {
    _log_emit "WARN " "$_LOG_LEVEL_WARNING" "$@"
}

log_error() {
    _log_emit "ERROR" "$_LOG_LEVEL_ERROR" "$@"
}

# Log a section separator — always outputs regardless of level
log_separator() {
    _action="${1:-}"
    # Reuse timestamp cache
    _current_epoch=$(date +%s 2>/dev/null || echo "0")
    if [ "$_current_epoch" != "$_LOG_TIMESTAMP_EPOCH" ]; then
        _LOG_TIMESTAMP_CACHE=$(date -u "+%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date "+%Y-%m-%dT%H:%M:%S")
        _LOG_TIMESTAMP_EPOCH="$_current_epoch"
    fi
    _timestamp="$_LOG_TIMESTAMP_CACHE"
    _comp=$(printf "%-10s" "$_LOG_COMPONENT")
    _conn=$(printf "%-16s" "$_LOG_CONNECTION")
    _line="${_timestamp} [-----] [${_comp}] [${_conn}] ──── ${_action} ────"
    echo "$_line"
    if [ -n "$_LOG_FILE" ]; then
        echo "$_line" >> "$_LOG_FILE"
    fi
}
