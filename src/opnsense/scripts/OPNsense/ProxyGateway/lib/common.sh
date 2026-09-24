#!/bin/sh

# common.sh — Shared helpers for Proxy Gateway shell scripts
#
# Usage:
#   . /usr/local/opnsense/scripts/OPNsense/ProxyGateway/lib/common.sh
#
# The runtime .conf files hold user-controlled values (passwords, URLs), so
# they are written with shell single-quoting and read back with conf_get —
# never sourced with ".", which would execute any "$(...)" in a value.

# Lock shared by reconfigure.sh and watchdog.sh (via lockf(1)) so they never
# start/stop the same connection concurrently.
PGW_LOCKFILE="/var/run/proxygateway/pgw.lock"

# Return 0 if $1 is a valid connection name (must match the MVC model).
# Uses case instead of "echo | grep" because grep matches per line, so a
# name with an embedded newline would slip through.
pgw_valid_name() {
    case "$1" in
        ''|*[!a-zA-Z0-9_]*) return 1 ;;
    esac
    [ "${#1}" -le 16 ]
}

# Quote a value for safe inclusion in a shell-style KEY='value' line.
# Every ' becomes '\'' and the result is wrapped in single quotes.
pgw_shquote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# Read KEY from a .conf file without executing it.
# Accepts both the current single-quoted format and the legacy
# double-quoted format. The last assignment wins, like sourcing would.
# Usage: VALUE=$(conf_get KEY /path/to/file.conf)
conf_get() {
    _cg_val=$(grep "^$1=" "$2" 2>/dev/null | tail -n 1)
    _cg_val="${_cg_val#*=}"
    case "$_cg_val" in
        \'*\')
            _cg_val="${_cg_val#\'}"
            _cg_val="${_cg_val%\'}"
            printf '%s' "$_cg_val" | sed "s/'\\\\''/'/g"
            ;;
        \"*\")
            _cg_val="${_cg_val#\"}"
            printf '%s' "${_cg_val%\"}"
            ;;
        *)
            printf '%s' "$_cg_val"
            ;;
    esac
}

# Percent-encode a string for use as URL userinfo (RFC 3986 unreserved kept).
# Needed so passwords containing @ : / ? # % do not break URL parsing.
pgw_urlencode() {
    printf '%s' "$1" | LC_ALL=C awk '
        BEGIN { for (i = 1; i < 256; i++) ord[sprintf("%c", i)] = i }
        {
            if (NR > 1) printf "%%0A"
            for (i = 1; i <= length($0); i++) {
                c = substr($0, i, 1)
                if (c ~ /[A-Za-z0-9._~-]/) printf "%s", c
                else printf "%%%02X", ord[c]
            }
        }'
}

# Escape a value for a double-quoted string in a curl config file (-K).
pgw_curl_cfg_escape() {
    printf '%s' "$1" | sed 's/[\\"]/\\&/g'
}
