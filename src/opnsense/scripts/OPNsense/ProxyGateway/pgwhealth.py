"""
pgwhealth.py — Health probe for a Proxy Gateway connection.

Healthy means an HTTP(S) request reaches the probe target. Where possible the
request is sent through the tunnel itself (``curl --interface pgw_NAME``), so
the whole path a client uses is tested: kernel -> tun -> tun2socks -> proxy.

A request bound to the tunnel address only enters the tunnel when pf routes
it there. OPNsense does that with its "force gateway" rule
(``pass out route-to (pgw_X peer) from (pgw_X)``), but automatic outbound NAT
also covers the tunnel network on WAN, and NAT is applied before the filter:
the packet is rewritten to the WAN address, the route-to rule no longer
matches and the "tunnel" probe silently leaves through WAN. predict_tun_path()
reads the live pf ruleset and says whether a tunnel probe would really use the
tunnel. If not, the probe goes to the proxy directly (curl --proxy) and the
result is labelled mode=proxy, so a WAN request is never mistaken for a
working tunnel.
"""

import ipaddress
import json
import os
import re
import subprocess
import time
import urllib.parse

import pgwconf

RUNDIR = "/var/run/proxygateway"
LOGDIR = "/var/log/proxygateway"
CURL = "/usr/local/bin/curl"
PFCTL = "/sbin/pfctl"
IFCONFIG = "/sbin/ifconfig"

# Lightweight page that answers quickly from most networks. The previous
# default (http://1.1.1.1/) intermittently returned empty replies (curl exit
# 52) through a China exit, which counted as failures.
DEFAULT_TARGET = "https://www.baidu.com/"
DEFAULT_TIMEOUT = 10

NAME_RE = re.compile(r"[A-Za-z0-9_]{1,16}")

TUN_OK = "ok"
TUN_NAT_LEAK = "nat_leak"
TUN_NO_ROUTE_TO = "no_route_to"
TUN_UNKNOWN = "unknown"

_NAT_RE = re.compile(r"^(no\s+)?nat\b(.*)$")
_PROTO_RE = re.compile(r"\bproto\s+(\{[^}]*\}|\S+)")


def valid_name(name):
    return bool(name) and NAME_RE.fullmatch(name) is not None


# --------------------------------------------------------------------------
# Tunnel path prediction from pf rules
# --------------------------------------------------------------------------

def _split_from_to(match):
    """Return (source, destination) tokens of a pf rule's match part."""
    m = re.search(r"\bfrom\s+(.*?)\s+to\s+(.*)$", match)
    if not m:
        return "any", "any"
    src = m.group(1).strip()
    dst = m.group(2).strip()
    # strip trailing qualifiers from the destination (flags, tags, ...)
    dst = dst.split()[0] if dst and not dst.startswith(("!", "{")) else dst
    return src, dst


def _source_covers(src, iface, tun_local):
    """True / False / None (cannot tell) whether a pf source covers tun_local."""
    src = src.strip()
    if src.startswith("!") or src.startswith("{") or src.startswith("<"):
        return None
    if src == "any" or src == "all":
        return True
    m = re.fullmatch(r"\(([^:)]+)(?::(network|0|broadcast|peer))?\)", src)
    if m:
        name, mod = m.group(1), m.group(2)
        if name == iface and mod in (None, "network", "0"):
            return True
        # another interface's address/network: not the tunnel address
        return False
    try:
        net = ipaddress.ip_network(src, strict=False)
    except ValueError:
        return None
    try:
        return ipaddress.ip_address(tun_local) in net
    except ValueError:
        return None


def _proto_includes_tcp(match):
    m = _PROTO_RE.search(match)
    if not m:
        return True
    protos = m.group(1).strip("{} ").replace(",", " ").split()
    return "tcp" in protos


def predict_tun_path(iface, tun_local, nat_rules, filter_rules):
    """Would a TCP request bound to ``tun_local`` really leave via ``iface``?

    ``nat_rules`` / ``filter_rules`` are the texts of ``pfctl -sn`` and
    ``pfctl -sr``. Returns one of:

    - ``ok``           the force-gateway route-to rule exists and no NAT rule
                       on another interface rewrites the tunnel address first
    - ``nat_leak``     the first applicable NAT rule on another interface
                       (pf NAT is first-match; "no nat" counts) translates
                       the tunnel address, so the route-to rule never matches
    - ``no_route_to``  there is no ``pass out route-to (iface ...) from
                       (iface)`` rule, so the request follows the default route
    - ``unknown``      a rule could not be evaluated (table, list, negation)
                       or the rules could not be read
    """
    if not iface or not tun_local or not filter_rules:
        return TUN_UNKNOWN

    esc = re.escape(iface)
    route_re = re.compile(r"route-to\s+\(\s*" + esc + r"\s+\S+?\s*\)")
    from_re = re.compile(r"\bfrom\s+\(" + esc + r"\)")
    has_route_to = any(
        line.lstrip().startswith("pass") and " out " in f" {line} "
        and route_re.search(line) and from_re.search(line)
        for line in filter_rules.splitlines()
    )
    if not has_route_to:
        return TUN_NO_ROUTE_TO

    for raw in (nat_rules or "").splitlines():
        line = raw.strip()
        m = _NAT_RE.match(line)
        if not m:
            continue
        is_no_nat = bool(m.group(1))
        match = m.group(2).split(" -> ")[0]
        if re.search(r"\binet6\b", match):
            continue
        on = re.search(r"\bon\s+(!\s*)?(\S+)", match)
        if on:
            if on.group(1):
                return TUN_UNKNOWN
            if on.group(2) == iface:
                continue
        if not _proto_includes_tcp(match):
            continue
        if re.search(r"\bport\b", match):
            continue
        src, dst = _split_from_to(match)
        if not (dst in ("any", "all") or dst.startswith("!")):
            # rule only for specific destinations; does not cover a probe
            # to an arbitrary internet host
            continue
        covers = _source_covers(src, iface, tun_local)
        if covers is None:
            return TUN_UNKNOWN
        if covers:
            return TUN_OK if is_no_nat else TUN_NAT_LEAK
    return TUN_OK


def read_pf_rules(runner=subprocess.run):
    """Return (nat_text, filter_text); empty strings when pfctl fails."""
    out = []
    for flag in ("-sn", "-sr"):
        try:
            res = runner([PFCTL, flag], capture_output=True, text=True, timeout=10)
            out.append(res.stdout if res.returncode == 0 else "")
        except (OSError, subprocess.TimeoutExpired):
            out.append("")
    return out[0], out[1]


# --------------------------------------------------------------------------
# curl probes
# --------------------------------------------------------------------------

def curl_cfg_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def mask_url(url):
    """Hide userinfo (credentials) in a proxy URL for logs."""
    return re.sub(r"://[^@/]*@", "://***@", url or "")


def curl_probe(target, timeout, proxy_url="", interface="", runner=subprocess.run):
    """Fetch ``target`` once. Returns dict(http_code, curl_exit, curl_err, latency_ms).

    The proxy URL (may contain credentials) is passed in a curl config on
    stdin, never on the command line.
    """
    cmd = [CURL, "-K", "-", "-s", "-o", "/dev/null", "-w", "%{http_code}",
           "--connect-timeout", str(timeout), "--max-time", str(timeout)]
    if interface:
        cmd += ["--interface", interface]
    cmd += ["--", target]
    cfg = ""
    if proxy_url:
        cfg = 'proxy = "%s"\n' % curl_cfg_escape(proxy_url)
    start = time.monotonic()
    try:
        res = runner(cmd, input=cfg, capture_output=True, text=True, timeout=timeout + 5)
        code = (res.stdout or "").strip() or "000"
        rc = res.returncode
        err = (res.stderr or "").strip().splitlines()[:1]
        err = err[0] if err else ""
    except subprocess.TimeoutExpired:
        code, rc, err = "000", 28, "timeout"
    except OSError as e:
        code, rc, err = "000", 127, str(e)
    latency = int((time.monotonic() - start) * 1000)
    return {"http_code": code, "curl_exit": rc, "curl_err": mask_url(err),
            "latency_ms": latency}


def is_http_ok(code):
    """Any HTTP response means the request got through; 000 means it did not."""
    return bool(code) and code != "000"


def proxy_curl_url(proxy_type, proxy_url):
    """curl proxy URL for a tun2socks proxy URL, or '' if curl cannot speak it."""
    if not proxy_url or proxy_type in ("ss", "ssh"):
        return ""
    if proxy_type in ("http", "https"):
        return proxy_url
    # socks5: let the proxy resolve names (socks5h), like the clients do
    if proxy_url.startswith("socks5://"):
        return "socks5h" + proxy_url[len("socks5"):]
    return proxy_url


def build_proxy_url(proxy_type, server, port, user="", password=""):
    """curl proxy URL for proxy settings from desired.json ('' for ss)."""
    if proxy_type in ("socks5", "socks5tls"):
        scheme = "socks5h"
    elif proxy_type in ("http", "https"):
        scheme = "http"
    else:
        return ""
    if not server:
        return ""
    userinfo = ""
    if user and password:
        userinfo = (urllib.parse.quote(user, safe="") + ":"
                    + urllib.parse.quote(password, safe="") + "@")
    return f"{scheme}://{userinfo}{server}:{port}"


# --------------------------------------------------------------------------
# Full health check of a running connection
# --------------------------------------------------------------------------

def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _iface_exists(iface, runner):
    try:
        return runner([IFCONFIG, iface], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def check(name, target="", timeout=DEFAULT_TIMEOUT, rundir=RUNDIR, runner=subprocess.run,
          pid_alive=_pid_alive, pf_reader=None):
    """Probe one connection. Returns a result dict; does not write anything.

    Keys: ok, status, reason, mode, tun_path, http_code, curl_exit, curl_err,
    latency_ms, target, via, message.
    """
    conf_file = os.path.join(rundir, f"{name}.conf")
    result = {"ok": False, "status": "down", "reason": "", "mode": "", "tun_path": TUN_UNKNOWN,
              "http_code": "", "curl_exit": "", "curl_err": "", "latency_ms": -1,
              "target": "", "via": ""}
    if not os.path.isfile(conf_file):
        result.update(status="error", reason="no_config", message="Connection config not found")
        return result
    conf = pgwconf.read_conf(conf_file)
    iface = conf.get("IFACE") or f"pgw_{name}"
    target = target or conf.get("HEALTH_TARGET") or DEFAULT_TARGET
    if not target.startswith(("http://", "https://")):
        result.update(status="error", reason="bad_target",
                      message="Health check target must be an http(s) URL")
        return result
    result["target"] = target

    pid_file = os.path.join(rundir, f"{name}.pid")
    if not os.path.isfile(pid_file):
        result.update(reason="no_pidfile", message="No PID file found — process not tracked")
        return result
    with open(pid_file) as f:
        pid = f.read().strip()
    if not pid_alive(pid):
        result.update(reason="process_dead", message=f"tun2socks process (PID: {pid}) is dead")
        return result
    if not _iface_exists(iface, runner):
        result.update(reason="no_interface", message=f"Interface {iface} does not exist")
        return result

    nat_text, filter_text = (pf_reader or (lambda: read_pf_rules(runner)))()
    tun_path = predict_tun_path(iface, conf.get("TUN_LOCAL", ""), nat_text, filter_text)
    result["tun_path"] = tun_path

    proxy_type = conf.get("PROXY_TYPE", "")
    curl_proxy = proxy_curl_url(proxy_type, conf.get("PROXY_URL", ""))

    if tun_path == TUN_OK or not curl_proxy:
        # Through the tunnel. For Shadowsocks curl cannot talk to the proxy,
        # so this is the only probe available even when tun_path is not ok
        # (tun_path then tells the reader the result is not trustworthy).
        result["mode"] = "tun"
        result["via"] = f"interface:{iface}"
        probe = curl_probe(target, timeout, interface=iface, runner=runner)
    else:
        result["mode"] = "proxy"
        result["via"] = mask_url(curl_proxy)
        probe = curl_probe(target, timeout, proxy_url=curl_proxy, runner=runner)

    result.update(probe)
    if is_http_ok(probe["http_code"]):
        result.update(ok=True, status="up", reason="")
    else:
        result.update(reason="probe_failed" if result["mode"] == "tun" else "proxy_unreachable")
    return result


def probe_detail(result):
    return f"via={result['via']} target={result['target']} http={result['http_code']}"


def status_lines(result, now):
    """Key/value lines of the <name>.status file."""
    lines = [("status", result["status"])]
    if result["status"] == "error":
        return lines
    if result["mode"]:
        lines.append(("probe", probe_detail(result)))
    if result["reason"]:
        lines.append(("reason", result["reason"]))
    if result["mode"]:
        if result["ok"]:
            lines.append(("latency_ms", str(result["latency_ms"])))
        else:
            lines.append(("curl_exit", str(result["curl_exit"])))
            lines.append(("curl_err", str(result["curl_err"]).replace("\n", " ")))
        lines.append(("mode", result["mode"]))
        lines.append(("tun_path", result["tun_path"]))
    lines.append(("timestamp", str(int(now))))
    return lines


def history_line(name, result, now):
    """JSON line appended to <name>_health.log (only for completed probes)."""
    entry = {"timestamp": int(now), "name": name, "status": "up" if result["ok"] else "down",
             "latency_ms": result["latency_ms"], "http_code": result["http_code"]}
    if not result["ok"]:
        try:
            entry["curl_exit"] = int(result["curl_exit"])
        except (TypeError, ValueError):
            entry["curl_exit"] = -1
    entry["mode"] = result["mode"]
    return json.dumps(entry, separators=(",", ":"))


def log_message(result):
    """(level, text) for the connection log."""
    if result["status"] == "error" or not result["mode"]:
        return "ERROR", result.get("message", result["reason"])
    tun_note = "" if result["tun_path"] == TUN_OK else f" tun_path={result['tun_path']}"
    if result["ok"]:
        return "INFO ", (f"Healthy — HTTP {result['http_code']}, {result['latency_ms']}ms "
                         f"(mode={result['mode']}{tun_note} {probe_detail(result)})")
    what = "Tunnel probe failed" if result["mode"] == "tun" else "Proxy unreachable"
    return "WARN ", (f"{what} — mode={result['mode']}{tun_note} {probe_detail(result)} "
                     f"curl_exit={result['curl_exit']} {result['curl_err']}").rstrip()


def format_log_line(level, name, text, now):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    return f"{ts} [{level}] [{'healthcheck':<10}] [{name:<16}] {text}"


def record(name, result, now, rundir=RUNDIR, logdir=LOGDIR):
    """Write the .status file, the connection log line and the history line.

    Returns the connection log line (also printed by the CLI).
    """
    os.makedirs(logdir, exist_ok=True)
    status_file = os.path.join(rundir, f"{name}.status")
    tmp = f"{status_file}.tmp"
    with open(tmp, "w") as f:
        for key, val in status_lines(result, now):
            f.write(f"{key}={val}\n")
    os.replace(tmp, status_file)

    level, text = log_message(result)
    line = format_log_line(level, name, text, now)
    with open(os.path.join(logdir, f"{name}.log"), "a") as f:
        f.write(line + "\n")
    if result["mode"]:
        with open(os.path.join(logdir, f"{name}_health.log"), "a") as f:
            f.write(history_line(name, result, now) + "\n")
    return line
