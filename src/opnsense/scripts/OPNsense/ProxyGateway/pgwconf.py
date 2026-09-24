"""
pgwconf.py — Shared helpers for reading/writing runtime .conf files.

The .conf files in /var/run/proxygateway hold user-controlled values
(passwords, URLs) and are also read by shell scripts, so every value is
written shell single-quoted. Shell readers use conf_get from lib/common.sh;
nothing ever sources these files.
"""

import hashlib
import json
import os
import shlex
import tempfile

RUNDIR = "/var/run/proxygateway"
EXTRA_MARKER = "# --- EXTRA_CONFIG ---"

# desired.json keys that can be applied without restarting tun2socks.
# Everything else (proxy, credentials, tunnel, backup) requires a restart.
HOT_KEYS = {
    "uuid", "enabled", "healthCheckEnabled", "healthCheckTarget",
    "speedTestUrl", "gatewayPriority", "failoverThreshold",
    "failbackEnabled", "autoForceDown",
}


def parse_value(raw):
    """Decode one KEY=value right-hand side.

    Handles the current single-quoted format as well as the legacy
    double-quoted format written by older versions.
    """
    try:
        parts = shlex.split(raw, posix=True)
    except ValueError:
        return raw.strip('"')
    return " ".join(parts)


def read_conf(path):
    """Parse a .conf file into a dict. Later assignments win."""
    config = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            config[key] = parse_value(val)
    return config


def config_hash(conn):
    """Fingerprint of every setting that requires a restart when changed.

    Includes credentials, so a password change is picked up; only the hash
    is stored, never the values themselves.
    """
    relevant = {k: v for k, v in conn.items() if k not in HOT_KEYS}
    blob = json.dumps(relevant, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def conf_line(key, value):
    # Same quoting as pgw_shquote in lib/common.sh (' -> '\'') so the shell
    # reader conf_get can decode it; shlex.quote uses a different escape.
    quoted = "'" + str(value).replace("'", "'\\''") + "'"
    return f"{key}={quoted}\n"


def write_extra_config(conn):
    """Rewrite the hot-updatable section of a connection's .conf file.

    Health check, speed test and backup settings live after EXTRA_MARKER and
    can change without restarting tun2socks. The core section written by
    setup.sh is preserved. The file is replaced atomically with mode 0600
    because it contains credentials.
    """
    name = conn["name"]
    conf_file = os.path.join(RUNDIR, f"{name}.conf")
    if not os.path.isfile(conf_file):
        return

    with open(conf_file) as f:
        lines = f.readlines()

    core_lines = []
    for line in lines:
        if line.strip() == EXTRA_MARKER:
            break
        # Drop stray HEALTH_TARGET lines older watchdog versions appended
        # to the core section; they are rewritten below.
        if line.startswith("HEALTH_TARGET="):
            continue
        core_lines.append(line)

    extra = [f"{EXTRA_MARKER}\n", conf_line("CONFIG_HASH", config_hash(conn))]

    target = conn.get("healthCheckTarget", "")
    if target:
        extra.append(conf_line("HEALTH_TARGET", target))

    speed_url = conn.get("speedTestUrl", "")
    if speed_url:
        extra.append(conf_line("SPEED_TEST_URL", speed_url))

    if conn.get("backupEnabled") == "1":
        extra.append(conf_line("BACKUP_ENABLED", "1"))
        extra.append(conf_line("BACKUP_PROXY_TYPE", conn.get("backupProxyType", "socks5")))
        extra.append(conf_line("BACKUP_PROXY_SERVER", conn.get("backupProxyServer", "")))
        extra.append(conf_line("BACKUP_PROXY_PORT", conn.get("backupProxyPort", "1080")))
        extra.append(conf_line("FAILOVER_THRESHOLD", conn.get("failoverThreshold", "3")))
        extra.append(conf_line("FAILBACK_ENABLED", conn.get("failbackEnabled", "1")))
        # Backup credentials are not written here: watchdog.py reads them
        # from desired.json, and nothing consumes them from the .conf.

    fd, tmp = tempfile.mkstemp(dir=RUNDIR, prefix=f".{name}.conf.")
    try:
        with os.fdopen(fd, "w") as f:
            f.writelines(core_lines)
            f.writelines(extra)
        os.chmod(tmp, 0o600)
        os.replace(tmp, conf_file)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def clear_failover_state(name):
    """Forget failover state so a freshly (re)started connection is on primary."""
    try:
        os.remove(os.path.join(RUNDIR, f"{name}.failover"))
    except FileNotFoundError:
        pass
