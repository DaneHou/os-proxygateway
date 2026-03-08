#!/usr/local/bin/python3

"""
watchdog.py — Monitor enabled connections and restart crashed tun2socks processes.

Designed to be called periodically via cron (every 60s by default).
Reads /var/run/proxygateway/desired.json for enabled connections,
checks if their tun2socks process is alive, and restarts dead ones.
"""

import glob
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
DESIRED_CONFIG = os.path.join(RUNDIR, "desired.json")

FAILOVER_COOLDOWN = 300  # 5 minutes cooldown after switch
FAILBACK_PROBE_REQUIRED = 2  # consecutive OK probes before failback

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


def load_failover_state(name):
    """Load failover state from JSON file."""
    state_file = os.path.join(RUNDIR, f"{name}.failover")
    default = {
        "active_proxy": "primary",
        "consecutive_failures": 0,
        "switched_at": None,
        "switch_count": 0,
        "primary_probe_ok_count": 0,
    }
    if not os.path.isfile(state_file):
        return default
    try:
        with open(state_file) as f:
            state = json.load(f)
        # Ensure all keys exist
        for k, v in default.items():
            state.setdefault(k, v)
        return state
    except (json.JSONDecodeError, IOError):
        return default


def save_failover_state(name, state):
    """Save failover state to JSON file."""
    state_file = os.path.join(RUNDIR, f"{name}.failover")
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def probe_proxy_directly(conn, proxy_type, server, port, auth_user="", auth_pass=""):
    """Probe a proxy server directly (not through TUN) using curl --proxy."""
    # Build proxy URL
    if proxy_type in ("socks5", "socks5tls"):
        scheme = "socks5h"
    else:
        scheme = "http"

    if auth_user and auth_pass:
        proxy_url = f"{scheme}://{auth_user}:{auth_pass}@{server}:{port}"
    else:
        proxy_url = f"{scheme}://{server}:{port}"

    target = conn.get("healthCheckTarget", "") or "http://1.1.1.1/"

    try:
        result = subprocess.run(
            ["/usr/local/bin/curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--proxy", proxy_url,
             "--connect-timeout", "10", "--max-time", "10",
             target],
            capture_output=True, text=True, timeout=15
        )
        http_code = result.stdout.strip()
        return http_code != "000" and http_code != ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def switch_proxy(name, conn, to_backup):
    """Switch a connection between primary and backup proxy.

    Tears down the current tun2socks and restarts with different proxy params.
    The TUN interface/IP/gateway stay the same — only upstream proxy changes.
    """
    log.info("Switching %s to %s proxy", name, "backup" if to_backup else "primary")

    # Teardown current connection
    result = subprocess.run(
        ["/bin/sh", TEARDOWN_SCRIPT, name, "--defer-routes"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        log.error("Teardown failed for %s during switch: %s", name, result.stderr.strip())
        return False

    # Build setup command with the target proxy's params
    if to_backup:
        proxy_type = conn.get("backupProxyType", "socks5")
        proxy_server = conn.get("backupProxyServer", "")
        proxy_port = conn.get("backupProxyPort", "1080")
        auth_enabled = conn.get("backupAuthEnabled", "0")
        auth_user = conn.get("backupAuthUser", "")
        auth_pass = conn.get("backupAuthPass", "")
    else:
        proxy_type = conn.get("proxyType", "socks5")
        proxy_server = conn.get("proxyServer", "")
        proxy_port = conn.get("proxyPort", "1080")
        auth_enabled = conn.get("authEnabled", "0")
        auth_user = conn.get("authUser", "")
        auth_pass = conn.get("authPass", "")

    cmd = [
        "/bin/sh", SETUP_SCRIPT,
        name, proxy_type, proxy_server, proxy_port,
        "--defer-routes",
    ]

    env = os.environ.copy()
    if auth_enabled == "1" and auth_user:
        cmd.extend(["--auth-user", auth_user])
        cmd.append("--auth-pass-env")
        env["PROXY_AUTH_PASS"] = auth_pass

    if conn.get("tunAddress"):
        cmd.extend(["--tun-addr", conn["tunAddress"]])
    if conn.get("tunMTU"):
        cmd.extend(["--tun-mtu", conn["tunMTU"]])
    if conn.get("proxyInterface"):
        cmd.extend(["--proxy-iface", conn["proxyInterface"]])
    if conn.get("logLevel"):
        cmd.extend(["--loglevel", conn["logLevel"]])

    # Shadowsocks settings for the active proxy type
    if proxy_type == "ss":
        if to_backup:
            ss_method = conn.get("backupSsMethod", "aes-256-gcm")
            ss_password = conn.get("backupSsPassword", "")
        else:
            ss_method = conn.get("ssMethod", "aes-256-gcm")
            ss_password = conn.get("ssPassword", "")
        if ss_method:
            cmd.extend(["--ss-method", ss_method])
        if ss_password:
            cmd.append("--ss-password-env")
            env["SS_AUTH_PASS"] = ss_password
        if not to_backup:
            if conn.get("ssObfs"):
                cmd.extend(["--ss-obfs", conn["ssObfs"]])
            if conn.get("ssObfsHost"):
                cmd.extend(["--ss-obfs-host", conn["ssObfsHost"]])

    # SSH key file
    if proxy_type == "ssh":
        key_file = conn.get("backupSshKeyFile", "") if to_backup else conn.get("sshKeyFile", "")
        if key_file:
            cmd.extend(["--ssh-key", key_file])

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    if result.returncode != 0:
        log.error("Setup failed for %s during switch: %s", name, result.stderr.strip())
        return False

    # Save health check config to .conf
    conf_file = os.path.join(RUNDIR, f"{name}.conf")
    if os.path.isfile(conf_file):
        with open(conf_file, "a") as f:
            target = conn.get("healthCheckTarget", "")
            if target:
                f.write(f'HEALTH_TARGET="{target}"\n')

    # Reconfigure routes
    subprocess.run(
        ["/usr/local/sbin/configctl", "interface", "routes", "reconfigure"],
        capture_output=True, timeout=30
    )

    log.info("Switched %s to %s proxy successfully", name, "backup" if to_backup else "primary")
    return True


def force_down_gateway(name, down):
    """Set or clear force_down on a proxy gateway via configd."""
    action = "down" if down else "up"
    try:
        result = subprocess.run(
            ["/usr/local/sbin/configctl", "proxygateway", "forcedown", name, action],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            log.info("Gateway force_%s for %s: OK", action, name)
        else:
            log.error("Gateway force_%s for %s failed: %s", action, name, result.stderr.strip())
    except subprocess.TimeoutExpired:
        log.error("Gateway force_%s for %s timed out", action, name)


def check_failover(name, conn, health_ok):
    """Check and manage failover state for a connection.

    Called after each health check with the result.
    Handles: consecutive failure counting, switching to backup,
    probing primary for failback, force-down gateway.
    """
    state = load_failover_state(name)
    backup_enabled = conn.get("backupEnabled") == "1" and conn.get("backupProxyServer")
    auto_force_down = conn.get("autoForceDown", "1") == "1"
    threshold = int(conn.get("failoverThreshold", "3"))
    failback = conn.get("failbackEnabled", "1") == "1"
    now = int(time.time())

    # Check for reconfigure lock — skip failover during reconfigure
    if os.path.isfile(os.path.join(RUNDIR, "reconfigure.lock")):
        log.debug("Reconfigure in progress, skipping failover check for %s", name)
        return

    if state["active_proxy"] == "primary":
        if not health_ok:
            state["consecutive_failures"] += 1
            log.warning("%s: primary health check failed (%d/%d)",
                       name, state["consecutive_failures"], threshold)

            if state["consecutive_failures"] >= threshold:
                if backup_enabled:
                    # Switch to backup
                    if switch_proxy(name, conn, to_backup=True):
                        state["active_proxy"] = "backup"
                        state["consecutive_failures"] = 0
                        state["switched_at"] = now
                        state["switch_count"] += 1
                        state["primary_probe_ok_count"] = 0
                        log.info("%s: switched to backup proxy (switch #%d)",
                                name, state["switch_count"])
                    else:
                        log.error("%s: failed to switch to backup", name)
                        if auto_force_down:
                            force_down_gateway(name, True)
                elif auto_force_down:
                    # No backup — force down the gateway
                    force_down_gateway(name, True)
                    log.info("%s: no backup configured, gateway forced down", name)
        else:
            if state["consecutive_failures"] > 0:
                log.info("%s: primary recovered after %d failures",
                        name, state["consecutive_failures"])
            state["consecutive_failures"] = 0
            # If gateway was forced down, bring it back up
            # (check force_down state file)

    elif state["active_proxy"] == "backup":
        if not health_ok:
            state["consecutive_failures"] += 1
            log.warning("%s: backup health check failed (%d/%d)",
                       name, state["consecutive_failures"], threshold)

            if state["consecutive_failures"] >= threshold:
                # Backup also failing — try switching back to primary as last resort
                log.warning("%s: backup also failing, attempting primary as last resort", name)
                if switch_proxy(name, conn, to_backup=False):
                    state["active_proxy"] = "primary"
                    state["consecutive_failures"] = 0
                    state["switched_at"] = now
                    state["switch_count"] += 1
                    state["primary_probe_ok_count"] = 0
                else:
                    if auto_force_down:
                        force_down_gateway(name, True)
        else:
            state["consecutive_failures"] = 0

            # Probe primary for failback
            if failback:
                # Cooldown check
                switched_at = state.get("switched_at") or 0
                if now - switched_at < FAILOVER_COOLDOWN:
                    log.debug("%s: in cooldown period, skipping primary probe", name)
                else:
                    # Probe primary directly (not through TUN)
                    primary_ok = probe_proxy_directly(
                        conn,
                        conn.get("proxyType", "socks5"),
                        conn.get("proxyServer", ""),
                        conn.get("proxyPort", "1080"),
                        conn.get("authUser", "") if conn.get("authEnabled") == "1" else "",
                        conn.get("authPass", "") if conn.get("authEnabled") == "1" else "",
                    )

                    if primary_ok:
                        state["primary_probe_ok_count"] += 1
                        log.info("%s: primary probe OK (%d/%d)",
                                name, state["primary_probe_ok_count"], FAILBACK_PROBE_REQUIRED)

                        if state["primary_probe_ok_count"] >= FAILBACK_PROBE_REQUIRED:
                            # Switch back to primary
                            if switch_proxy(name, conn, to_backup=False):
                                state["active_proxy"] = "primary"
                                state["consecutive_failures"] = 0
                                state["switched_at"] = now
                                state["switch_count"] += 1
                                state["primary_probe_ok_count"] = 0
                                log.info("%s: failed back to primary proxy", name)
                            else:
                                log.error("%s: failback to primary failed", name)
                    else:
                        state["primary_probe_ok_count"] = 0

    save_failover_state(name, state)


def run_healthcheck(name):
    """Run health check after restart. Returns True if healthy."""
    cmd = ["/bin/sh", HEALTHCHECK_SCRIPT, name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            log.info("Health check passed for %s: %s", name, result.stdout.strip())
            return True
        else:
            log.warning("Health check failed for %s: %s", name, result.stdout.strip())
            return False
    except subprocess.TimeoutExpired:
        log.warning("Health check timed out for %s", name)
        return False


def main():
    setup_logging()

    enabled = get_enabled_connections()
    if not enabled:
        return

    restarted = []
    alive_to_check = []
    for name, conn in enabled.items():
        if not check_connection(name):
            log.warning("Connection %s is dead, attempting restart", name)
            if restart_connection(conn):
                restarted.append(name)
        elif conn.get("healthCheckEnabled", "1") == "1":
            alive_to_check.append(name)

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

    # Periodic health checks for alive connections
    for name in alive_to_check:
        health_ok = run_healthcheck(name)
        conn = enabled[name]
        # Check failover state if backup is configured or auto-force-down is enabled
        if conn.get("backupEnabled") == "1" or conn.get("autoForceDown", "1") == "1":
            check_failover(name, conn, health_ok)

    if restarted:
        log.info("Watchdog restarted %d connection(s): %s",
                 len(restarted), ", ".join(restarted))


if __name__ == "__main__":
    main()
