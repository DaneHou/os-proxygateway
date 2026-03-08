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

    # SSH settings
    if conn.get("proxyType") == "ssh" and conn.get("sshKeyFile"):
        cmd.extend(["--ssh-key", conn["sshKeyFile"]])

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


def save_healthcheck_config(conn):
    """Append health check and speed test settings to the connection's .conf file.

    This makes the custom targets available to healthcheck.sh and speedtest.sh
    regardless of whether they're called from reconfigure.py or configd.
    """
    name = conn["name"]
    conf_file = os.path.join(RUNDIR, f"{name}.conf")
    if not os.path.isfile(conf_file):
        return

    with open(conf_file, "a") as f:
        target = conn.get("healthCheckTarget", "")
        if target:
            f.write(f'HEALTH_TARGET="{target}"\n')

        speed_url = conn.get("speedTestUrl", "")
        if speed_url:
            f.write(f'SPEED_TEST_URL="{speed_url}"\n')

        speed_url_domestic = conn.get("speedTestUrlDomestic", "")
        if speed_url_domestic:
            f.write(f'SPEED_TEST_URL_DOMESTIC="{speed_url_domestic}"\n')

        # Backup proxy config
        if conn.get("backupEnabled") == "1":
            f.write(f'BACKUP_ENABLED="1"\n')
            f.write(f'BACKUP_PROXY_TYPE="{conn.get("backupProxyType", "socks5")}"\n')
            f.write(f'BACKUP_PROXY_SERVER="{conn.get("backupProxyServer", "")}"\n')
            f.write(f'BACKUP_PROXY_PORT="{conn.get("backupProxyPort", "1080")}"\n')
            if conn.get("backupAuthEnabled") == "1":
                f.write(f'BACKUP_AUTH_ENABLED="1"\n')
                f.write(f'BACKUP_AUTH_USER="{conn.get("backupAuthUser", "")}"\n')
                f.write(f'BACKUP_AUTH_PASS="{conn.get("backupAuthPass", "")}"\n')
            f.write(f'FAILOVER_THRESHOLD="{conn.get("failoverThreshold", "3")}"\n')
            f.write(f'FAILBACK_ENABLED="{conn.get("failbackEnabled", "1")}"\n')


def run_healthcheck(conn):
    """Run a quick health check after starting a connection.

    Tests actual proxy connectivity by sending traffic through the proxy.
    The target URL is read from the .conf file by healthcheck.sh (written
    by save_healthcheck_config), so we don't pass it as an argument.
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
    """Check if a connection's config has changed vs. running state."""
    checks = [
        ("proxyType", "PROXY_TYPE"),
        ("proxyServer", "PROXY_ADDR"),
        ("proxyPort", "PROXY_PORT"),
        ("proxyInterface", "PROXY_IFACE"),
    ]
    for desired_key, running_key in checks:
        if str(desired.get(desired_key, "")) != str(running_config.get(running_key, "")):
            return True

    # Also check backup proxy changes
    backup_checks = [
        ("backupEnabled", "BACKUP_ENABLED"),
        ("backupProxyType", "BACKUP_PROXY_TYPE"),
        ("backupProxyServer", "BACKUP_PROXY_SERVER"),
        ("backupProxyPort", "BACKUP_PROXY_PORT"),
    ]
    for desired_key, running_key in backup_checks:
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

    # Execute: stop removed/changed connections
    for name in sorted(to_stop | to_restart):
        run_teardown(name)

    # Execute: start new/changed connections, then verify connectivity
    started = []
    for name in sorted(to_start | to_restart):
        if run_setup(desired[name]) == 0:
            started.append(name)
            # Save health check config to .conf so healthcheck.sh (called by
            # the Test button or cron) uses the same target/settings.
            save_healthcheck_config(desired[name])

    # Give tun2socks time to complete the SOCKS handshake before probing.
    # setup.sh exits once the TUN interface is up, but the proxy connection
    # needs another moment to become usable.
    if started:
        time.sleep(2)

    for name in started:
        if desired[name].get("healthCheckEnabled", "1") == "1":
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
