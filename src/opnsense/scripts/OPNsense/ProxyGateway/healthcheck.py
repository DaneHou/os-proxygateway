#!/usr/local/bin/python3

"""
healthcheck.py — Probe connectivity of one Proxy Gateway connection.

Usage: healthcheck.py <name> [target_url] [timeout_seconds]
Exit code: 0 = healthy, 1 = unhealthy or error.

The probe goes through the tunnel when pf would really route it there and
through the proxy directly otherwise (see pgwhealth.py). The result is
written to /var/run/proxygateway/<name>.status, the connection log and the
health history (<name>_health.log).
"""

import sys
import time

import pgwhealth


def main(argv):
    if len(argv) < 2 or not argv[1]:
        print("Usage: healthcheck.py <name> [target_url] [timeout_seconds]")
        return 1
    name = argv[1]
    if not pgwhealth.valid_name(name):
        print("ERROR: Invalid connection name")
        return 1
    target = argv[2] if len(argv) > 2 else ""
    timeout = pgwhealth.DEFAULT_TIMEOUT
    if len(argv) > 3 and argv[3].isdigit() and 0 < int(argv[3]) <= 60:
        timeout = int(argv[3])

    result = pgwhealth.check(name, target, timeout)
    print(pgwhealth.record(name, result, time.time()))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
