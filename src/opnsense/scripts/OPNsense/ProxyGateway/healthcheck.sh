#!/bin/sh

# healthcheck.sh — Probe connectivity through a proxy gateway connection
# Usage: healthcheck.sh <name> [target_url] [timeout_seconds]
# Exit code: 0 = healthy, 1 = unhealthy
#
# Kept as the stable entry point for configd ("configctl proxygateway
# healthcheck NAME") and reconfigure.py; the logic lives in healthcheck.py /
# pgwhealth.py (tunnel probe when pf really routes it through the tunnel,
# direct proxy probe otherwise).

exec /usr/local/bin/python3 "$(dirname "$0")/healthcheck.py" "$@"
