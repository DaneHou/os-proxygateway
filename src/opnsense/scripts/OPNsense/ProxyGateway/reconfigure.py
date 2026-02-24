#!/usr/local/bin/python3

"""
reconfigure.py — Diff desired config against running state, start/stop connections.

Reads the desired configuration JSON and compares with currently running
connections (by checking /var/run/proxygateway/*.conf). Starts new connections,
stops removed ones, and restarts changed ones.
"""

import json
import logging
import os
import subprocess
import sys

RUNDIR = "/var/run/proxygateway"
LOGDIR = "/var/log/proxygateway"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_SCRIPT = os.path.join(SCRIPT_DIR, "setup.sh")
TEARDOWN_SCRIPT = os.path.join(SCRIPT_DIR, "teardown.sh")
HEALTHCHECK_SCRIPT = os.path.join(SCRIPT_DIR, "healthcheck.sh")

# Structured log format matching the shell logging library
LOG_FORMAT = "%(asctime)s [%(levelname)-5s] [%(name)-10s] %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"


def setup_logging(log_level="info"):
    """Configure structured logging to stdout and aggregate log file."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    formatter.converter = lambda *args: __import__("time").gmtime()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    # File handler — aggregate reconfigure log
    os.makedirs(LOGDIR, exist_ok=True)
    file_handler = logging.FileHandler(
        os.path.join(LOGDIR, "reconfigure.log"), mode="a"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)


log = logging.getLogger("reconfig")


def get_running_connections():
    """Get dict of currently running connections from .conf files."""
    running = {}
    conf_dir = RUNDIR
    if not os.path.isdir(conf_dir):
        return running

    for entry in sorted(os.listdir(conf_dir)):
        if not entry.endswith(".conf"):
            continue
        conf_path = os.path.join(conf_dir, entry)
        name = entry.replace(".conf", "")
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

    # Prepare environment variables for secure credential passing
    env = os.environ.copy()

    if conn.get("authEnabled") == "1" and conn.get("authUser"):
        cmd.extend(["--auth-user", conn["authUser"]])
        # Pass password via environment variable instead of command line
        cmd.append("--auth-pass-env")
        env["PROXY_AUTH_PASS"] = conn.get("authPass", "")

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

    log.info("Starting connection: %s", conn["name"])
    print(f"  Command: {' '.join(cmd)}")  # Safe to print now - no password in args
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    # Always print stdout (contains setup.sh progress messages)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        log.error("Failed to start %s: %s", conn["name"], result.stderr.strip())
        print(f"ERROR starting {conn['name']} (exit code {result.returncode})")
        if result.stderr:
            print(f"STDERR: {result.stderr.rstrip()}")
    else:
        # Log setup output at debug level (it has its own structured logs)
        for line in result.stdout.strip().splitlines():
            log.debug("  %s", line)
        log.info("Started %s successfully", conn["name"])
    return result.returncode


def run_healthcheck(conn):
    """Run a quick health check after starting a connection.

    Tests actual proxy connectivity by sending traffic through the proxy.
    Only passes a custom target if the user explicitly configured one
    (non-empty healthCheckTarget). Otherwise the healthcheck script uses
    its built-in default (http://1.1.1.1/).
    """
    name = conn["name"]
    cmd = ["/bin/sh", HEALTHCHECK_SCRIPT, name]
    target = conn.get("healthCheckTarget", "")
    if target:
        cmd.append(target)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
        if result.returncode == 0:
            print(f"  Health check: {output}")
        else:
            print(f"  Health check: FAILED — {output}")
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"  Health check: FAILED — timed out after 15s")
        return 1


def run_teardown(name):
    """Stop a connection using teardown.sh."""
    log.info("Stopping connection: %s", name)
    result = subprocess.run(
        ["/bin/sh", TEARDOWN_SCRIPT, name],
        capture_output=True, text=True
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        log.error("Failed to stop %s: %s", name, result.stderr.strip())
        print(f"ERROR stopping {name} (exit code {result.returncode})")
        if result.stderr:
            print(f"STDERR: {result.stderr.rstrip()}")
    else:
        for line in result.stdout.strip().splitlines():
            log.debug("  %s", line)
        log.info("Stopped %s successfully", name)
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

    # Pre-flight checks
    tun2socks = "/usr/local/bin/tun2socks"
    if not os.path.isfile(tun2socks):
        print(f"ERROR: tun2socks binary not found at {tun2socks}")
        print("Install it with: make install-tun2socks")
        sys.exit(1)
    if not os.access(tun2socks, os.X_OK):
        print(f"ERROR: tun2socks binary is not executable: {tun2socks}")
        sys.exit(1)

    # Initialize logging with configured level
    log_level = desired_config.get("logLevel", "info")
    setup_logging(log_level)

    log.info("──── BEGIN RECONFIGURE ────")

    # Get desired connections (only enabled ones)
    desired = {}
    all_conns = desired_config.get("connections", [])
    for conn in all_conns:
        if conn.get("enabled", "0") == "1":
            desired[conn["name"]] = conn

    print(f"Desired config: {len(all_conns)} total, {len(desired)} enabled")
    for name, conn in desired.items():
        print(f"  {name}: {conn.get('proxyType', '?')}://{conn.get('proxyServer', '?')}:{conn.get('proxyPort', '?')}")

    # Get running connections
    running = get_running_connections()
    print(f"Running connections: {len(running)}")
    for name in running:
        print(f"  {name}")

    log.info("Desired: %d connection(s) — Running: %d connection(s)",
             len(desired), len(running))

    # Determine actions
    to_stop = set(running.keys()) - set(desired.keys())
    to_start = set(desired.keys()) - set(running.keys())
    to_check = set(desired.keys()) & set(running.keys())

    # Check for config changes in existing connections
    to_restart = set()
    for name in to_check:
        if connection_changed(desired[name], running[name]):
            log.info("Config changed for '%s' — will restart", name)
            to_restart.add(name)

    # Execute: stop removed/changed connections
    for name in sorted(to_stop | to_restart):
        run_teardown(name)

    # Execute: start new/changed connections, then verify connectivity
    for name in sorted(to_start | to_restart):
        if run_setup(desired[name]) == 0:
            run_healthcheck(desired[name])

    # Summary
    unchanged = to_check - to_restart
    parts = []
    if unchanged:
        parts.append(f"unchanged={','.join(sorted(unchanged))}")
    if to_start:
        parts.append(f"started={','.join(sorted(to_start))}")
    if to_stop:
        parts.append(f"stopped={','.join(sorted(to_stop))}")
    if to_restart:
        parts.append(f"restarted={','.join(sorted(to_restart))}")

    if parts:
        log.info("Summary: %s", " | ".join(parts))
    else:
        log.info("Summary: no connections configured")

    log.info("──── RECONFIGURE COMPLETE ────")


if __name__ == "__main__":
    main()
