#!/usr/local/bin/python3

"""
watchdog.py — Monitor enabled connections and restart crashed tun2socks processes.

Designed to be called periodically via cron (every 60s by default).
Reads /var/run/proxygateway/desired.json for enabled connections,
checks if their tun2socks process is alive, and restarts dead ones.
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
HEALTHCHECK_SCRIPT = os.path.join(SCRIPT_DIR, "healthcheck.sh")
DESIRED_CONFIG = os.path.join(RUNDIR, "desired.json")

LOG_FORMAT = "%(asctime)s [%(levelname)-5s] [%(name)-10s] %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"


def setup_logging():
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    formatter.converter = lambda *args: time.gmtime()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)


log = logging.getLogger("watchdog")


def is_process_alive(pid):
    """Check if a process with the given PID is running."""
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def get_enabled_connections():
    """Read desired.json and return dict of enabled connections by name."""
    if not os.path.isfile(DESIRED_CONFIG):
        return {}

    with open(DESIRED_CONFIG) as f:
        config = json.load(f)

    enabled = {}
    for conn in config.get("connections", []):
        if conn.get("enabled", "0") == "1":
            enabled[conn["name"]] = conn
    return enabled


def check_connection(name):
    """Check if a connection's tun2socks process is alive.

    Returns True if healthy, False if needs restart.
    """
    pid_file = os.path.join(RUNDIR, f"{name}.pid")

    if not os.path.isfile(pid_file):
        return False

    with open(pid_file) as f:
        pid = f.read().strip()

    return is_process_alive(pid)


def restart_connection(conn):
    """Restart a single dead connection via setup.sh."""
    name = conn["name"]
    log.info("Restarting dead connection: %s", name)

    # Clean up stale files before restart
    for ext in (".pid", ".conf", ".tundev", ".status"):
        stale = os.path.join(RUNDIR, f"{name}{ext}")
        if os.path.isfile(stale):
            os.remove(stale)

    # Destroy stale interface if it exists
    iface = f"pgw_{name}"
    subprocess.run(
        ["/sbin/ifconfig", iface, "destroy"],
        capture_output=True, timeout=5
    )

    cmd = [
        "/bin/sh", SETUP_SCRIPT,
        name,
        conn.get("proxyType", "socks5"),
        conn.get("proxyServer", ""),
        conn.get("proxyPort", "1080"),
    ]

    env = os.environ.copy()

    if conn.get("authEnabled") == "1" and conn.get("authUser"):
        cmd.extend(["--auth-user", conn["authUser"]])
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

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log.error("Failed to restart %s: %s", name, result.stderr.strip())
        return False

    log.info("Restarted %s successfully", name)

    # Save health check config (same as reconfigure.py does)
    conf_file = os.path.join(RUNDIR, f"{name}.conf")
    target = conn.get("healthCheckTarget", "")
    if os.path.isfile(conf_file) and target:
        with open(conf_file, "a") as f:
            f.write(f'HEALTH_TARGET="{target}"\n')

    return True


def run_healthcheck(name):
    """Run health check after restart."""
    cmd = ["/bin/sh", HEALTHCHECK_SCRIPT, name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            log.info("Health check passed for %s: %s", name, result.stdout.strip())
        else:
            log.warning("Health check failed for %s: %s", name, result.stdout.strip())
    except subprocess.TimeoutExpired:
        log.warning("Health check timed out for %s", name)


def main():
    setup_logging()

    enabled = get_enabled_connections()
    if not enabled:
        return

    restarted = []
    for name, conn in enabled.items():
        if not check_connection(name):
            log.warning("Connection %s is dead, attempting restart", name)
            if restart_connection(conn):
                restarted.append(name)

    # Wait for SOCKS handshake before health checks
    if restarted:
        time.sleep(2)
        for name in restarted:
            conn = enabled[name]
            if conn.get("healthCheckEnabled", "1") == "1":
                run_healthcheck(name)

        # Reconfigure routes after restarts
        subprocess.run(
            ["/usr/local/sbin/configctl", "interface", "routes", "reconfigure"],
            capture_output=True, timeout=30
        )

    if restarted:
        log.info("Watchdog restarted %d connection(s): %s",
                 len(restarted), ", ".join(restarted))


if __name__ == "__main__":
    main()
