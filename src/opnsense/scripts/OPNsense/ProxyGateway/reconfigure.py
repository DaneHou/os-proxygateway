#!/usr/local/bin/python3

"""
reconfigure.py — Diff desired config against running state, start/stop connections.

Reads the desired configuration JSON and compares with currently running
connections (by checking /var/run/proxygateway/*.conf). Starts new connections,
stops removed ones, and restarts changed ones.
"""

import json
import os
import subprocess
import sys
import glob

RUNDIR = "/var/run/proxygateway"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_SCRIPT = os.path.join(SCRIPT_DIR, "setup.sh")
TEARDOWN_SCRIPT = os.path.join(SCRIPT_DIR, "teardown.sh")


def get_running_connections():
    """Get dict of currently running connections from .conf files."""
    running = {}
    for conf_path in glob.glob(os.path.join(RUNDIR, "*.conf")):
        name = os.path.basename(conf_path).replace(".conf", "")
        config = {}
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    config[key] = val.strip('"')
        running[name] = config
    return running


def run_setup(conn):
    """Start a connection using setup.sh."""
    cmd = [
        "/bin/sh", SETUP_SCRIPT,
        conn["name"],
        conn.get("proxyType", "socks5"),
        conn.get("proxyServer", ""),
        conn.get("proxyPort", "1080"),
    ]

    if conn.get("authEnabled") == "1" and conn.get("authUser"):
        cmd.extend(["--auth-user", conn["authUser"]])
        cmd.extend(["--auth-pass", conn.get("authPass", "")])

    if conn.get("tunAddress"):
        cmd.extend(["--tun-addr", conn["tunAddress"]])

    if conn.get("tunMTU"):
        cmd.extend(["--tun-mtu", conn["tunMTU"]])

    if conn.get("dnsMode"):
        cmd.extend(["--dns-mode", conn["dnsMode"]])

    if conn.get("dnsServer"):
        cmd.extend(["--dns-server", conn["dnsServer"]])

    if conn.get("logLevel"):
        cmd.extend(["--loglevel", conn["logLevel"]])

    print(f"Starting connection: {conn['name']}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR starting {conn['name']}: {result.stderr}")
    else:
        print(result.stdout)
    return result.returncode


def run_teardown(name):
    """Stop a connection using teardown.sh."""
    print(f"Stopping connection: {name}")
    result = subprocess.run(
        ["/bin/sh", TEARDOWN_SCRIPT, name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR stopping {name}: {result.stderr}")
    else:
        print(result.stdout)
    return result.returncode


def connection_changed(desired, running_config):
    """Check if a connection's config has changed vs. running state."""
    checks = [
        ("proxyType", "PROXY_TYPE"),
        ("proxyServer", "PROXY_ADDR"),
        ("proxyPort", "PROXY_PORT"),
    ]
    for desired_key, running_key in checks:
        if str(desired.get(desired_key, "")) != str(running_config.get(running_key, "")):
            return True
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: reconfigure.py <desired_config.json>")
        sys.exit(1)

    config_path = sys.argv[1]

    with open(config_path) as f:
        desired_config = json.load(f)

    # Get desired connections (only enabled ones)
    desired = {}
    for conn in desired_config.get("connections", []):
        if conn.get("enabled", "0") == "1":
            desired[conn["name"]] = conn

    # Get running connections
    running = get_running_connections()

    # Determine actions
    to_stop = set(running.keys()) - set(desired.keys())
    to_start = set(desired.keys()) - set(running.keys())
    to_check = set(desired.keys()) & set(running.keys())

    # Check for config changes in existing connections
    to_restart = set()
    for name in to_check:
        if connection_changed(desired[name], running[name]):
            to_restart.add(name)

    # Execute: stop removed/changed connections
    for name in to_stop | to_restart:
        run_teardown(name)

    # Execute: start new/changed connections
    for name in to_start | to_restart:
        run_setup(desired[name])

    # Summary
    unchanged = to_check - to_restart
    if unchanged:
        print(f"Unchanged: {', '.join(sorted(unchanged))}")
    if to_start:
        print(f"Started: {', '.join(sorted(to_start))}")
    if to_stop:
        print(f"Stopped: {', '.join(sorted(to_stop))}")
    if to_restart:
        print(f"Restarted: {', '.join(sorted(to_restart))}")

    print("Reconfiguration complete.")


if __name__ == "__main__":
    main()
