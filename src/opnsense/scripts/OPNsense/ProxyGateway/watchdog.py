#!/usr/local/bin/python3

"""
watchdog.py — Monitor enabled connections and restart crashed tun2socks processes.

Designed to be called periodically via cron (every 60s by default).
Reads /var/run/proxygateway/desired.json for enabled connections,
checks if their tun2socks process is alive, and restarts dead ones.

Failover uses hysteresis: failoverThreshold (N) consecutive failed health
checks before leaving the active proxy, failbackThreshold (M) consecutive
successful primary probes (after a cooldown) before failing back. A backup
is only switched to when its own direct probe succeeds at that moment; a dead
backup is recorded as backup_status=down in the .failover state instead of
being a candidate.

--dry-run runs the health checks and the decision logic but never restarts,
switches, forces a gateway down/up or saves state; it only logs what it
would do.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.parse

import pgwconf
import pgwhealth

RUNDIR = "/var/run/proxygateway"
LOGDIR = "/var/log/proxygateway"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_SCRIPT = os.path.join(SCRIPT_DIR, "setup.sh")
TEARDOWN_SCRIPT = os.path.join(SCRIPT_DIR, "teardown.sh")
DESIRED_CONFIG = os.path.join(RUNDIR, "desired.json")

FAILOVER_COOLDOWN = 300  # 5 minutes cooldown after switch
DEFAULT_FAILOVER_THRESHOLD = 3  # N: consecutive failures before switching
DEFAULT_FAILBACK_THRESHOLD = 3  # M: consecutive OK primary probes before failback
BACKUP_PROBE_INTERVAL = 300  # probe an idle backup at most this often

# Set by --dry-run: decide and log, but change nothing.
DRY_RUN = False

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
    if DRY_RUN:
        log.info("[dry-run] would restart dead connection %s", name)
        return False
    log.info("Restarting dead connection: %s", name)

    # Clean up stale files before restart. setup.sh starts on the primary
    # proxy, so drop any failover state from before the crash as well.
    pgwconf.clear_failover_state(name)
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

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        log.error("Failed to restart %s: %s", name, result.stderr.strip())
        return False

    log.info("Restarted %s successfully", name)

    # Restore health check / backup settings (same as reconfigure.py does)
    pgwconf.write_extra_config(conn)

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
        "forced_down": False,
        "backup_status": "unknown",
        "backup_checked_at": None,
        "backup_reason": "",
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
    """Save failover state to JSON file (atomically, so readers never see
    a half-written file)."""
    if DRY_RUN:
        return
    state_file = os.path.join(RUNDIR, f"{name}.failover")
    tmp = f"{state_file}.tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, state_file)


def probe_proxy_directly(conn, proxy_type, server, port, auth_user="", auth_pass=""):
    """Probe a proxy server directly (not through TUN) using curl --proxy.

    Returns "up", "down" or "unknown" (curl cannot speak Shadowsocks).
    """
    proxy_url = pgwhealth.build_proxy_url(proxy_type, server, port, auth_user, auth_pass)
    if not proxy_url:
        log.debug("No direct probe available for proxy type %s", proxy_type)
        return "unknown"
    target = conn.get("healthCheckTarget", "") or pgwhealth.DEFAULT_TARGET
    probe = pgwhealth.curl_probe(target, pgwhealth.DEFAULT_TIMEOUT, proxy_url=proxy_url)
    return "up" if pgwhealth.is_http_ok(probe["http_code"]) else "down"


def probe_primary(conn):
    auth = conn.get("authEnabled") == "1"
    return probe_proxy_directly(
        conn,
        conn.get("proxyType", "socks5"),
        conn.get("proxyServer", ""),
        conn.get("proxyPort", "1080"),
        conn.get("authUser", "") if auth else "",
        conn.get("authPass", "") if auth else "",
    )


def probe_backup(conn):
    auth = conn.get("backupAuthEnabled") == "1"
    return probe_proxy_directly(
        conn,
        conn.get("backupProxyType", "socks5"),
        conn.get("backupProxyServer", ""),
        conn.get("backupProxyPort", "1080"),
        conn.get("backupAuthUser", "") if auth else "",
        conn.get("backupAuthPass", "") if auth else "",
    )


def update_backup_status(name, conn, state, now, force):
    """Probe the backup (always when force, else at most every
    BACKUP_PROBE_INTERVAL) and record the result in the state.
    Returns the current backup_status."""
    checked = state.get("backup_checked_at") or 0
    if not force and now - checked < BACKUP_PROBE_INTERVAL:
        return state.get("backup_status", "unknown")
    status = probe_backup(conn)
    if status == "unknown":
        reason = "backup proxy type cannot be probed directly"
    elif status == "down":
        reason = "direct probe through the backup proxy failed"
    else:
        reason = ""
    if status != state.get("backup_status"):
        log.info("%s: backup proxy is %s%s", name, status, f" ({reason})" if reason else "")
    state["backup_status"] = status
    state["backup_checked_at"] = now
    state["backup_reason"] = reason
    return status


def switch_proxy(name, conn, to_backup):
    """Switch a connection between primary and backup proxy.

    Tears down the current tun2socks and restarts with different proxy params.
    The TUN interface/IP/gateway stay the same — only upstream proxy changes.
    """
    if DRY_RUN:
        log.info("[dry-run] would switch %s to %s proxy", name, "backup" if to_backup else "primary")
        return True
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

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    if result.returncode != 0:
        log.error("Setup failed for %s during switch: %s", name, result.stderr.strip())
        return False

    # Restore health check / backup settings; setup.sh rewrote the .conf
    pgwconf.write_extra_config(conn)

    # Reconfigure routes
    subprocess.run(
        ["/usr/local/sbin/configctl", "interface", "routes", "reconfigure"],
        capture_output=True, timeout=30
    )

    log.info("Switched %s to %s proxy successfully", name, "backup" if to_backup else "primary")
    return True


def force_down_gateway(name, down):
    """Set or clear force_down on a proxy gateway via configd.

    Returns True on success.
    """
    action = "down" if down else "up"
    if DRY_RUN:
        log.info("[dry-run] would set gateway force_%s for %s", action, name)
        return True
    try:
        result = subprocess.run(
            ["/usr/local/sbin/configctl", "proxygateway", "forcedown", name, action],
            capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        log.error("Gateway force_%s for %s timed out", action, name)
        return False
    # configctl exits 0 even when the script reports an error in its JSON
    try:
        ok = result.returncode == 0 and json.loads(result.stdout).get("status") == "ok"
    except ValueError:
        ok = False
    if ok:
        log.info("Gateway force_%s for %s: OK", action, name)
    else:
        log.error("Gateway force_%s for %s failed: %s", action, name,
                  (result.stdout or result.stderr).strip())
    return ok


def set_forced_down(name, state, down):
    """Force the gateway down/up once and remember it in the failover state,
    so we neither repeat the config.xml write every minute nor forget to
    bring the gateway back when the connection recovers."""
    if state.get("forced_down") == down:
        return
    if force_down_gateway(name, down):
        state["forced_down"] = down


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mark_switched(state, to_backup, now):
    state["active_proxy"] = "backup" if to_backup else "primary"
    state["consecutive_failures"] = 0
    state["switched_at"] = now
    state["switch_count"] += 1
    state["primary_probe_ok_count"] = 0


def check_failover(name, conn, health_ok, now=None):
    """Check and manage failover state for a connection.

    Called after each health check with the result.
    Handles: consecutive failure counting (N), switching to a backup that
    probes healthy, probing primary for failback (M), force-down gateway.
    """
    state = load_failover_state(name)
    backup_enabled = conn.get("backupEnabled") == "1" and bool(conn.get("backupProxyServer"))
    auto_force_down = conn.get("autoForceDown", "1") == "1"
    threshold = _int(conn.get("failoverThreshold"), DEFAULT_FAILOVER_THRESHOLD)
    failback_needed = _int(conn.get("failbackThreshold"), DEFAULT_FAILBACK_THRESHOLD)
    failback = conn.get("failbackEnabled", "1") == "1"
    now = int(time.time()) if now is None else now

    # Mutual exclusion with reconfigure is handled by the lockf(1) lock
    # taken in watchdog.sh / reconfigure.sh.

    # The active proxy works again: undo an earlier force-down
    if health_ok and state.get("forced_down"):
        log.info("%s: healthy again, clearing gateway force_down", name)
        set_forced_down(name, state, False)

    if state["active_proxy"] == "primary":
        if not health_ok:
            state["consecutive_failures"] += 1
            log.warning("%s: primary health check failed (%d/%d)",
                        name, state["consecutive_failures"], threshold)
            # While primary is failing, know whether the backup works now
            backup_status = (update_backup_status(name, conn, state, now, force=True)
                             if backup_enabled else "disabled")

            if state["consecutive_failures"] >= threshold:
                if backup_enabled and backup_status == "up":
                    if switch_proxy(name, conn, to_backup=True):
                        _mark_switched(state, True, now)
                        log.info("%s: switched to backup proxy (switch #%d)",
                                 name, state["switch_count"])
                    else:
                        log.error("%s: failed to switch to backup", name)
                        if auto_force_down:
                            set_forced_down(name, state, True)
                else:
                    if backup_enabled:
                        log.warning("%s: backup proxy is %s, not switching to it",
                                    name, backup_status)
                    if auto_force_down and not state.get("forced_down"):
                        set_forced_down(name, state, True)
                        log.info("%s: no working backup, gateway forced down", name)
        else:
            if state["consecutive_failures"] > 0:
                log.info("%s: primary recovered after %d failures",
                         name, state["consecutive_failures"])
            state["consecutive_failures"] = 0
            if backup_enabled:
                update_backup_status(name, conn, state, now, force=False)

    elif state["active_proxy"] == "backup":
        if not health_ok:
            state["consecutive_failures"] += 1
            log.warning("%s: backup health check failed (%d/%d)",
                        name, state["consecutive_failures"], threshold)

            if state["consecutive_failures"] >= threshold:
                state["backup_status"] = "down"
                state["backup_checked_at"] = now
                state["backup_reason"] = "health check on backup failed"
                # Only go back to primary if primary itself works now
                if probe_primary(conn) == "up":
                    log.warning("%s: backup failing, primary probes OK, switching back", name)
                    if switch_proxy(name, conn, to_backup=False):
                        _mark_switched(state, False, now)
                    elif auto_force_down:
                        set_forced_down(name, state, True)
                else:
                    log.warning("%s: backup failing and primary down too, staying", name)
                    if auto_force_down:
                        set_forced_down(name, state, True)
        else:
            state["consecutive_failures"] = 0
            state["backup_status"] = "up"
            state["backup_checked_at"] = now
            state["backup_reason"] = ""

            # Probe primary for failback
            if failback:
                switched_at = state.get("switched_at") or 0
                if now - switched_at < FAILOVER_COOLDOWN:
                    log.debug("%s: in cooldown period, skipping primary probe", name)
                elif probe_primary(conn) == "up":
                    state["primary_probe_ok_count"] += 1
                    log.info("%s: primary probe OK (%d/%d)",
                             name, state["primary_probe_ok_count"], failback_needed)
                    if state["primary_probe_ok_count"] >= failback_needed:
                        if switch_proxy(name, conn, to_backup=False):
                            _mark_switched(state, False, now)
                            log.info("%s: failed back to primary proxy", name)
                        else:
                            log.error("%s: failback to primary failed", name)
                else:
                    state["primary_probe_ok_count"] = 0

    save_failover_state(name, state)
    return state


def run_healthcheck(name):
    """Run the health check (pgwhealth) for a connection. Returns True if healthy.

    In dry-run mode nothing is written (no .status file, no history line).
    """
    try:
        result = pgwhealth.check(name)
    except Exception as e:  # never let one connection stop the watchdog
        log.warning("Health check error for %s: %s", name, e)
        return False
    now = time.time()
    if DRY_RUN:
        level, text = pgwhealth.log_message(result)
        line = pgwhealth.format_log_line(level, name, text, now)
    else:
        line = pgwhealth.record(name, result, now)
    if result["ok"]:
        log.info("Health check passed for %s: %s", name, line)
        return True
    log.warning("Health check failed for %s: %s", name, line)
    return False


def main(argv=None):
    global DRY_RUN
    parser = argparse.ArgumentParser(description="Proxy Gateway watchdog")
    parser.add_argument("--dry-run", action="store_true",
                        help="check and decide, but change nothing (log only)")
    args = parser.parse_args(argv)
    DRY_RUN = args.dry_run

    setup_logging()
    if DRY_RUN:
        log.info("[dry-run] no restarts, switches, force-down or state writes")

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
        if not DRY_RUN:
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
            state = check_failover(name, conn, health_ok)
            if DRY_RUN:
                log.info("[dry-run] %s: state would be active=%s failures=%d "
                         "primary_ok=%d backup=%s forced_down=%s", name,
                         state["active_proxy"], state["consecutive_failures"],
                         state["primary_probe_ok_count"], state.get("backup_status"),
                         state.get("forced_down"))

    if restarted:
        log.info("Watchdog restarted %d connection(s): %s",
                 len(restarted), ", ".join(restarted))


if __name__ == "__main__":
    main()
