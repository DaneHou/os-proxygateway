#!/usr/local/bin/python3

"""
plugin_health.py — configctl proxygateway healthcheck

Read-only health summary in the plugin health contract of os-netbaseline:
{"checks": [{"name", "ok": true|false|null, "severity", "detail"[, "fix"]}]}.
A failing check may carry "fix": {"action": "proxygateway <action> <conn>",
"title": ...} — a safe, idempotent configd action that does not change
config.xml (here: "restartconn NAME" for a dead tun2socks / missing
interface).

Per enabled connection:
  * tun2socks process alive (pid file)
  * TUN interface pgw_NAME exists and is UP/RUNNING
  * last connectivity probe of the watchdog (<name>.status; this script sends
    no traffic itself) — a probe that did not traverse the tunnel is reported
    as unverified, not as success — the failover state (<name>.failover) and
    the watchdog's tunnel repair state (<name>.repair)
  * the OPNsense gateway on pgw_NAME (gateway_health.php: core gateway list +
    dpinger status)

Never prints proxy servers, users or passwords. Finishes in a few seconds.
The per-connection connectivity probe (which does send traffic through the
proxy) is the separate action "configctl proxygateway probe NAME".
"""

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import pgwhealth

CONFIG_XML = "/conf/config.xml"
RUNDIR = "/var/run/proxygateway"
IFCONFIG = "/sbin/ifconfig"
GATEWAY_HEALTH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway_health.php")
PROBE_STALE_S = 15 * 60          # the watchdog probes every minute
REPAIR_WINDOW_S = 3600
REPAIR_MAX_PER_HOUR = 3          # keep in sync with pgwrepair.REPAIR_MAX_PER_HOUR


def restart_fix(name):
    return {"action": f"proxygateway restartconn {name}",
            "title": f"Restart the {name} tunnel (tun2socks)"}


def _yes(v):
    return str(v or "").strip() == "1"


def read_connections(config_xml=CONFIG_XML):
    """-> (plugin enabled, [{'name', 'health'}] of enabled connections) from config.xml (whitelisted fields)."""
    root = ET.parse(config_xml).getroot()
    base = root.find("OPNsense/ProxyGateway")
    if base is None:
        return False, []
    conns = []
    for el in base.findall("connections/connection"):
        name = (el.findtext("name") or "").strip()
        if _yes(el.findtext("enabled")) and pgwhealth.valid_name(name):
            conns.append({"name": name, "health": (el.findtext("healthCheckEnabled") or "1").strip() == "1"})
    return _yes(base.findtext("general/enabled")), conns


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _pid_alive(rundir, name):
    pid = _read(os.path.join(rundir, f"{name}.pid"))
    if pid is None:
        return None
    try:
        os.kill(int(pid.strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def _kv(text):
    out = {}
    for line in (text or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def iface_flags(iface, runner=subprocess.run):
    """-> set of interface flags ('UP', 'RUNNING', ...) or None when the interface does not exist."""
    try:
        res = runner([IFCONFIG, iface], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    first = (res.stdout or "").split("\n", 1)[0]
    if "<" not in first or ">" not in first:
        return set()
    return set(first[first.index("<") + 1:first.index(">")].split(","))


def gateways(runner=subprocess.run):
    """-> list of gateway dicts (gateway_health.php), None when unavailable."""
    try:
        res = runner(["/usr/local/bin/php", GATEWAY_HEALTH], capture_output=True, text=True, timeout=8)
        data = json.loads(res.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    gws = data.get("gateways") if isinstance(data, dict) else None
    return gws if isinstance(gws, list) else None


def connection_checks(name, health_enabled, rundir, flags, gws, now):
    iface = f"pgw_{name}"
    checks = []

    alive = _pid_alive(rundir, name)
    c = {
        "name": f"{name}: tun2socks",
        "ok": bool(alive),
        "detail": "running" if alive else ("not running (stale pid file)" if alive is False else "not started (no pid file)"),
    }
    if not alive:
        c["fix"] = restart_fix(name)
    checks.append(c)

    if flags is None:
        ok, detail = False, f"{iface} does not exist"
    elif "UP" in flags and "RUNNING" in flags:
        ok, detail = True, f"{iface} up"
    else:
        ok, detail = False, f"{iface} exists but is not up/running"
    c = {"name": f"{name}: interface", "ok": ok, "detail": detail}
    if not ok:
        c["fix"] = restart_fix(name)
    checks.append(c)

    status = _kv(_read(os.path.join(rundir, f"{name}.status")))
    if not health_enabled:
        checks.append({"name": f"{name}: connectivity", "ok": None, "severity": "info",
                       "detail": "health check disabled for this connection"})
    elif not status:
        checks.append({"name": f"{name}: connectivity", "ok": None, "severity": "info",
                       "detail": "no watchdog probe yet"})
    else:
        try:
            age = int(now - int(status.get("timestamp", "0")))
        except ValueError:
            age = None
        st = status.get("status", "")
        mode = status.get("mode", "")
        tun_path = status.get("tun_path", "")
        if "verified" in status:
            verified = status["verified"] == "1"
        else:   # status file of an older version
            verified = mode != "proxy" and tun_path in ("", "ok")
        if st == "up" and not verified:
            ok, sev = False, "low"
            detail = ("last watchdog probe did not traverse the tunnel (mode {}, tunnel path {}{}): "
                      "proxy reachable, tunnel unverified").format(
                mode or "?", tun_path or "?",
                f", {status['pin_error']}" if status.get("pin_error") else "")
        elif st == "up":
            ok, sev = True, "medium"
            detail = "last watchdog probe ok ({} ms{}{})".format(
                status.get("latency_ms", "?"), f", mode {mode}" if mode else "",
                ", pinned through the tunnel (outbound NAT covers the tunnel address)"
                if status.get("pinned") else "")
        else:
            ok, sev = False, "medium"
            detail = "last watchdog probe {}{}".format(st or "failed",
                                                      f" ({status['reason']})" if status.get("reason") else "")
        if age is not None and age > PROBE_STALE_S:
            ok, sev = False, ("low" if st == "up" else "medium")
            detail += f"; result is {age // 60} min old (watchdog not running?)"
        checks.append({"name": f"{name}: connectivity", "ok": ok, "severity": sev, "detail": detail})

    fo_text = _read(os.path.join(rundir, f"{name}.failover"))
    if fo_text:
        try:
            fo = json.loads(fo_text)
        except ValueError:
            fo = {}
        if fo.get("forced_down"):
            checks.append({"name": f"{name}: failover", "ok": False, "severity": "medium",
                           "detail": "gateway forced down by the watchdog (proxy unhealthy)"})
        elif fo.get("active_proxy") == "backup":
            checks.append({"name": f"{name}: failover", "ok": False, "severity": "info",
                           "detail": "running on the backup proxy"})

    rp_text = _read(os.path.join(rundir, f"{name}.repair"))
    if rp_text:
        try:
            rp = json.loads(rp_text)
        except ValueError:
            rp = {}
        rp = rp if isinstance(rp, dict) else {}
        restarts = [t for t in rp.get("restarts") or [] if isinstance(t, (int, float)) and now - t < REPAIR_WINDOW_S]
        last_at = rp.get("last_at") if isinstance(rp.get("last_at"), (int, float)) else 0
        recent = now - last_at < REPAIR_WINDOW_S
        action = str(rp.get("last_action", ""))[:40]
        if len(restarts) >= REPAIR_MAX_PER_HOUR and rp.get("tunnel_failures"):
            checks.append({"name": f"{name}: auto-repair", "ok": False, "severity": "medium",
                           "detail": f"{len(restarts)} restarts in the last hour and the tunnel still fails; "
                                     "watchdog repair capped"})
        elif recent and rp.get("last_result") == "failed":
            checks.append({"name": f"{name}: auto-repair", "ok": False, "severity": "medium",
                           "detail": f"last watchdog repair ({action}) failed"})
        elif recent and rp.get("last_result") == "upstream_down":
            checks.append({"name": f"{name}: auto-repair", "ok": False, "severity": "medium",
                           "detail": "proxy does not answer and cannot be restarted on this router"})
        elif restarts:
            checks.append({"name": f"{name}: auto-repair", "ok": True, "severity": "info",
                           "detail": f"watchdog restarted the chain {len(restarts)}x in the last hour "
                                     f"(last: {action})"})

    if gws is None:
        checks.append({"name": f"{name}: gateway", "ok": None, "severity": "low",
                       "detail": "gateway status unavailable"})
    else:
        gw = next((g for g in gws if g.get("device") == iface and not g.get("disabled")), None)
        if gw is None:
            checks.append({"name": f"{name}: gateway", "ok": False, "severity": "low",
                           "detail": f"no enabled OPNsense gateway on {iface} (interface not assigned?)"})
        else:
            st = str(gw.get("status") or "none")
            gname = str(gw.get("name", ""))[:40]
            if gw.get("force_down") or st == "force_down":
                ok, detail = False, f"{gname} is forced down"
            elif st == "none":
                ok = True
                detail = f"{gname} online" + (" (monitoring disabled)" if gw.get("monitor_disable") else "")
            else:
                ok, detail = False, f"{gname} status {st}"
            checks.append({"name": f"{name}: gateway", "ok": ok, "severity": "medium", "detail": detail})

    for c in checks:
        c.setdefault("severity", "medium")
    return checks


def build(config_xml=CONFIG_XML, rundir=RUNDIR, runner=subprocess.run, now=None):
    now = time.time() if now is None else now
    try:
        enabled, conns = read_connections(config_xml)
    except (OSError, ET.ParseError):
        return {"checks": [{"name": "configuration", "ok": None, "severity": "low",
                            "detail": "config.xml not readable"}]}
    if not enabled:
        return {"checks": []}
    if not conns:
        return {"checks": [{"name": "connections", "ok": None, "severity": "info",
                            "detail": "no enabled connections"}]}
    gws = gateways(runner)
    checks = []
    for c in conns:
        checks += connection_checks(c["name"], c["health"], rundir, iface_flags(f"pgw_{c['name']}", runner),
                                    gws, now)
    return {"checks": checks}


def main():
    print(json.dumps(build()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
