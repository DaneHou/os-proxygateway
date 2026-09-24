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
import time

import pgwconf

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
    """Configure structured logging to stdout only.

    File logging is handled by reconfigure.sh which pipes our stdout
    through ``tee -a reconfigure.log``.  Having a Python FileHandler
    on the same file caused every log line to appear twice.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    formatter.converter = lambda *args: __import__("time").gmtime()

    # Console handler (stdout → reconfigure.sh tee → log file)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)


log = logging.getLogger("reconfig")


def get_running_connections():
    """Get dict of currently running connections from .conf files."""
    running = {}
    if not os.path.isdir(RUNDIR):
        return running

    for entry in sorted(os.listdir(RUNDIR)):
        if not entry.endswith(".conf"):
            continue
        name = entry[:-len(".conf")]
        running[name] = pgwconf.read_conf(os.path.join(RUNDIR, entry))
    return running


def run_setup(conn):
    """Start a connection using setup.sh."""
    cmd = [
        "/bin/sh", SETUP_SCRIPT,
        conn["name"],
        conn.get("proxyType", "socks5"),
        conn.get("proxyServer", ""),
        conn.get("proxyPort", "1080"),
        "--defer-routes",  # Defer route reconfiguration for batch operations
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

    if conn.get("proxyInterface"):
        cmd.extend(["--proxy-iface", conn["proxyInterface"]])

    if conn.get("logLevel"):
        cmd.extend(["--loglevel", conn["logLevel"]])

    # Shadowsocks settings
    if conn.get("proxyType") == "ss":
        if conn.get("ssMethod"):
            cmd.extend(["--ss-method", conn["ssMethod"]])
        if conn.get("ssPassword"):
            cmd.append("--ss-password-env")
            env["SS_AUTH_PASS"] = conn.get("ssPassword", "")
        if conn.get("ssObfs"):
            cmd.extend(["--ss-obfs", conn["ssObfs"]])
        if conn.get("ssObfsHost"):
            cmd.extend(["--ss-obfs-host", conn["ssObfsHost"]])

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


def save_extra_config(conn):
    """Hot-update health check, speed test and backup settings in the .conf."""
    pgwconf.write_extra_config(conn)


def run_healthcheck(conn):
    """Run a quick health check after starting a connection.

    Tests actual proxy connectivity by sending traffic through the proxy.
    The target URL is read from the .conf file by healthcheck.sh (written
    by save_extra_config), so we don't pass it as an argument.
    """
    name = conn["name"]
    cmd = ["/bin/sh", HEALTHCHECK_SCRIPT, name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        output = result.stdout.strip()
        if result.returncode == 0:
            print(f"  Health check: {output}")
        else:
            print(f"  Health check: FAILED — {output}")
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"  Health check: FAILED — timed out after 20s")
        return 1


def run_teardown(name):
    """Stop a connection using teardown.sh."""
    log.info("Stopping connection: %s", name)
    result = subprocess.run(
        ["/bin/sh", TEARDOWN_SCRIPT, name, "--defer-routes"],
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
    """Check if a connection needs a restart to apply the desired config.

    Compares a fingerprint of all restart-relevant settings (including
    credentials and backup proxy). A .conf without a fingerprint was written
    by an older version, so restart it once to pick up the current format.
    """
    return running_config.get("CONFIG_HASH") != pgwconf.config_hash(desired)


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

    # Initialize logging — logLevel is per-connection in the JSON, use the first one
    log_level = "info"
    for conn in desired_config.get("connections", []):
        if conn.get("logLevel"):
            log_level = conn["logLevel"]
            break
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

    # Execute: stop removed/changed connections. A restarted connection comes
    # back on the primary proxy, so its failover state is reset too.
    for name in sorted(to_stop | to_restart):
        run_teardown(name)
        pgwconf.clear_failover_state(name)

    # Execute: start new/changed connections, then verify connectivity
    started = []
    for name in sorted(to_start | to_restart):
        pgwconf.clear_failover_state(name)
        if run_setup(desired[name]) == 0:
            started.append(name)
            save_extra_config(desired[name])

    # Give tun2socks time to complete the SOCKS handshake before probing.
    # setup.sh exits once the TUN interface is up, but the proxy connection
    # needs another moment to become usable.
    if started:
        time.sleep(2)

    for name in started:
        if desired[name].get("healthCheckEnabled", "1") == "1":
            run_healthcheck(desired[name])

    # Hot-update extra config (URLs, thresholds) for unchanged connections
    unchanged = to_check - to_restart
    for name in sorted(unchanged):
        save_extra_config(desired[name])

    # Summary
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
