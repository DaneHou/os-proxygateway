"""
pgwrepair.py — Helpers for the watchdog's tunnel repair and gateway handling.

* Gateway resolution: the OPNsense gateway(s) of a connection are the ones
  bound to its device pgw_NAME (any name, e.g. a user-made FRP_GW on the
  assigned interface) plus the plugin's own PROXYGW_<NAME>. Only PROXYGW_
  gateways are owned by the plugin.
* Repair state (<name>.repair, JSON): consecutive failed tunnel probes,
  timestamps of recent restarts, backoff deadline, last action/result.
* Upstream description: when the proxy itself does not answer (SOCKS step),
  say what is (or is not) listening there. The proxy is not Proxy Gateway's
  (e.g. shadowsocks-rust sslocal on :1080 belongs to its own package), so the
  watchdog reports it and never restarts it.
* event(): log a watchdog step to the watchdog log *and* syslog. Syslog
  priority is at least NOTICE because OPNsense's catch-all system log
  (/var/log/system/) only keeps notice..emerg for programs without their own
  log filter.
"""

import json
import logging
import os
import socket
import subprocess

try:
    import syslog
except ImportError:  # pragma: no cover - not on FreeBSD/Linux
    syslog = None

RUNDIR = "/var/run/proxygateway"
GATEWAY_HEALTH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway_health.php")
SOCKSTAT = "/usr/bin/sockstat"
PS = "/bin/ps"

REPAIR_MAX_PER_HOUR = 3          # cap: restarts per connection per rolling hour
REPAIR_WINDOW = 3600
REPAIR_BACKOFF_BASE = 120        # wait after the k-th restart in the window: 120 * 2^(k-1) s

log = logging.getLogger("watchdog")

_SYSLOG_PRIO = {}
if syslog is not None:
    _SYSLOG_PRIO = {logging.DEBUG: syslog.LOG_NOTICE, logging.INFO: syslog.LOG_NOTICE,
                    logging.WARNING: syslog.LOG_WARNING, logging.ERROR: syslog.LOG_ERR}


def event(level, msg, *args, to_syslog=True):
    """Log to the watchdog log and (unless dry-run callers disable it) syslog."""
    log.log(level, msg, *args)
    if not to_syslog or syslog is None:
        return
    text = msg % args if args else msg
    try:
        syslog.openlog("proxygateway", syslog.LOG_PID, syslog.LOG_DAEMON)
        syslog.syslog(_SYSLOG_PRIO.get(level, syslog.LOG_NOTICE), "watchdog: " + text)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Gateways
# --------------------------------------------------------------------------

def load_gateways(runner=subprocess.run):
    """Gateway list from gateway_health.php (core list + dpinger), None when unavailable."""
    try:
        res = runner(["/usr/local/bin/php", GATEWAY_HEALTH], capture_output=True, text=True, timeout=8)
        data = json.loads(res.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    gws = data.get("gateways") if isinstance(data, dict) else None
    return gws if isinstance(gws, list) else None


def owned_gateway_name(name):
    return "PROXYGW_" + name.upper()


def resolve_gateways(name, gws):
    """Enabled gateways of connection ``name``: [{'name', 'owned', 'force_down', 'status'}].

    Matches by device (pgw_NAME) and by the plugin's PROXYGW_<NAME> name.
    """
    device = f"pgw_{name}"
    own = owned_gateway_name(name)
    out = []
    for gw in gws or []:
        gname = str(gw.get("name", ""))
        if gw.get("disabled") or not gname:
            continue
        if gw.get("device") == device or gname == own:
            out.append({"name": gname, "owned": gname == own,
                        "force_down": bool(gw.get("force_down")), "status": str(gw.get("status") or "none")})
    return out


# --------------------------------------------------------------------------
# Repair state
# --------------------------------------------------------------------------

def default_state():
    return {"tunnel_failures": 0, "restarts": [], "next_allowed": 0,
            "last_action": "", "last_result": "", "last_at": None, "last_reason": ""}


def state_path(name, rundir=RUNDIR):
    return os.path.join(rundir, f"{name}.repair")


def load_state(name, rundir=RUNDIR):
    state = default_state()
    try:
        with open(state_path(name, rundir)) as f:
            data = json.load(f)
        if isinstance(data, dict):
            state.update(data)
    except (OSError, ValueError):
        pass
    if not isinstance(state.get("restarts"), list):
        state["restarts"] = []
    return state


def save_state(name, state, rundir=RUNDIR):
    path = state_path(name, rundir)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def recent_restarts(state, now):
    return [t for t in state.get("restarts", []) if isinstance(t, (int, float)) and now - t < REPAIR_WINDOW]


def may_restart(state, now):
    """(allowed, reason). Enforces the hourly cap and the backoff deadline."""
    recent = recent_restarts(state, now)
    if len(recent) >= REPAIR_MAX_PER_HOUR:
        retry = int(min(recent) + REPAIR_WINDOW - now)
        return False, f"cap reached ({REPAIR_MAX_PER_HOUR} restarts in the last hour, next in {retry}s)"
    if now < (state.get("next_allowed") or 0):
        return False, f"backoff ({int(state['next_allowed'] - now)}s left)"
    return True, ""


def note_restart(state, now, action, ok, reason=""):
    """Record a restart attempt (counts toward the cap) and set the backoff."""
    recent = recent_restarts(state, now) + [now]
    state["restarts"] = recent
    state["next_allowed"] = now + REPAIR_BACKOFF_BASE * (2 ** (len(recent) - 1))
    state["last_action"] = action
    state["last_result"] = "ok" if ok else "failed"
    state["last_at"] = now
    state["last_reason"] = reason
    state["tunnel_failures"] = 0


# --------------------------------------------------------------------------
# Local proxy service
# --------------------------------------------------------------------------

def is_local_address(addr):
    """True when ``addr`` is an address of this host (bindable)."""
    if not addr:
        return False
    if addr in ("localhost",) or addr.startswith("127."):
        return True
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((addr, 0))
        return True
    except (OSError, ValueError):
        return False


def listener_pid(addr, port, runner=subprocess.run):
    """(pid, command) of the process listening on addr:port (tcp4), or (None, '')."""
    try:
        res = runner([SOCKSTAT, "-4", "-l", "-P", "tcp", "-p", str(port)],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    for line in (res.stdout or "").splitlines():
        cols = line.split()
        if len(cols) < 6 or not cols[2].isdigit():
            continue
        host, _, lport = cols[5].rpartition(":")
        if lport == str(port) and host in ("*", addr):
            return int(cols[2]), cols[1]
    return None, ""


def process_binary(pid, runner=subprocess.run):
    try:
        res = runner([PS, "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    parts = (res.stdout or "").split()
    return parts[0] if parts else ""


def upstream_detail(addr, port, runner=subprocess.run, is_local=is_local_address):
    """What sits behind a proxy address that does not answer, for the log and healthcheck."""
    if not is_local(addr):
        return f"proxy {addr or '?'}:{port} is not on this router"
    pid, comm = listener_pid(addr, port, runner)
    if pid is None:
        return f"nothing listens on port {port} of this router"
    binary = process_binary(pid, runner)
    base = os.path.basename(binary) if binary else comm
    return f"{base or comm} (pid {pid}) listens on port {port} but does not answer"
