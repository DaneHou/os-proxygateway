#!/usr/local/bin/python3

"""
status.py — Output JSON status of all proxy gateway connections.
Called by configd: configctl proxygateway status
"""

import json
import os
import subprocess
import sys
import time

RUNDIR = "/var/run/proxygateway"


def get_traffic_stats(iface):
    """Get traffic statistics for an interface using netstat."""
    stats = {
        "traffic_in": "0",
        "traffic_out": "0",
        "packets_in": "0",
        "packets_out": "0",
    }

    # Try JSON output first (FreeBSD --libxo json)
    try:
        result = subprocess.run(
            ["/usr/bin/netstat", "-I", iface, "-b", "--libxo", "json"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            # Navigate the libxo JSON structure
            iface_list = data.get("statistics", {}).get("interface", [])
            for entry in iface_list:
                if entry.get("name") == iface:
                    stats["traffic_in"] = str(entry.get("received-bytes", 0))
                    stats["traffic_out"] = str(entry.get("sent-bytes", 0))
                    stats["packets_in"] = str(entry.get("received-packets", 0))
                    stats["packets_out"] = str(entry.get("sent-packets", 0))
                    return stats
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError,
            KeyError, ValueError):
        pass

    # Fallback: parse text output of netstat -I <iface> -b
    try:
        result = subprocess.run(
            ["/usr/bin/netstat", "-I", iface, "-b"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                # Header line tells us column positions; data is on subsequent lines
                # Typical columns: Name Mtu Network Address Ipkts Ierrs Ibytes
                #                   Opkts Oerrs Obytes Coll
                header = lines[0].split()
                for line in lines[1:]:
                    fields = line.split()
                    if len(fields) >= len(header) and fields[0] == iface:
                        try:
                            ipkts_idx = header.index("Ipkts")
                            ibytes_idx = header.index("Ibytes")
                            opkts_idx = header.index("Opkts")
                            obytes_idx = header.index("Obytes")
                            stats["packets_in"] = fields[ipkts_idx]
                            stats["traffic_in"] = fields[ibytes_idx]
                            stats["packets_out"] = fields[opkts_idx]
                            stats["traffic_out"] = fields[obytes_idx]
                        except (ValueError, IndexError):
                            pass
                        break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return stats


def get_status():
    """Collect status of all connections."""
    connections = []

    # Use os.scandir() instead of glob.glob() for better performance
    if not os.path.isdir(RUNDIR):
        return {"connections": connections}

    # Single ifconfig -l call to get all interfaces (avoids N subprocess forks)
    try:
        result = subprocess.run(["/sbin/ifconfig", "-l"],
                                capture_output=True, text=True, timeout=2)
        all_ifaces = set(result.stdout.strip().split())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        all_ifaces = set()

    conf_files = []
    with os.scandir(RUNDIR) as entries:
        for entry in entries:
            if entry.is_file() and entry.name.endswith(".conf"):
                conf_files.append(entry.path)

    for conf_path in sorted(conf_files):
        name = os.path.basename(conf_path).replace(".conf", "")

        # Read connection config
        config = {}
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    config[key] = val.strip('"')

        # Check if process is alive
        pid_file = os.path.join(RUNDIR, f"{name}.pid")
        pid = None
        process_alive = False
        if os.path.exists(pid_file):
            with open(pid_file) as f:
                pid = f.read().strip()
            try:
                os.kill(int(pid), 0)
                process_alive = True
            except (OSError, ValueError):
                process_alive = False

        # Read health status
        status_file = os.path.join(RUNDIR, f"{name}.status")
        health = {}
        if os.path.exists(status_file):
            with open(status_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, val = line.split("=", 1)
                        health[key] = val

        # Check interface via pre-fetched interface list (no subprocess per connection)
        iface = config.get("IFACE", f"pgw_{name}")
        iface_exists = iface in all_ifaces

        # Determine status using both process state and health check results.
        # Process/interface down = definitely down.
        # Process alive but health check failed = degraded (proxy unreachable).
        # Process alive, no health data yet = up (just started, not checked yet).
        if not process_alive or not iface_exists:
            status = "down"
        elif health.get("status") == "down":
            status = "degraded"
        else:
            status = "up"

        # Get traffic statistics for the interface
        traffic = get_traffic_stats(iface) if iface_exists else {
            "traffic_in": "0", "traffic_out": "0",
            "packets_in": "0", "packets_out": "0",
        }

        # Compute uptime from STARTED_AT
        started_at = config.get("STARTED_AT", "")
        uptime_seconds = 0
        if started_at:
            try:
                uptime_seconds = int(time.time()) - int(started_at)
                if uptime_seconds < 0:
                    uptime_seconds = 0
            except (ValueError, TypeError):
                uptime_seconds = 0

        conn_status = {
            "name": name,
            "interface": iface,
            "proxy_type": config.get("PROXY_TYPE", ""),
            "proxy_addr": config.get("PROXY_ADDR", ""),
            "proxy_port": config.get("PROXY_PORT", ""),
            "tun_local": config.get("TUN_LOCAL", ""),
            "tun_peer": config.get("TUN_PEER", ""),
            "pid": pid,
            "process_alive": process_alive,
            "interface_exists": iface_exists,
            "status": status,
            "health": health,
            "traffic_in": traffic["traffic_in"],
            "traffic_out": traffic["traffic_out"],
            "packets_in": traffic["packets_in"],
            "packets_out": traffic["packets_out"],
            "started_at": started_at,
            "uptime_seconds": uptime_seconds,
        }

        # Read failover state
        failover_file = os.path.join(RUNDIR, f"{name}.failover")
        failover = {}
        if os.path.exists(failover_file):
            try:
                with open(failover_file) as f:
                    failover = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        conn_status["active_proxy"] = failover.get("active_proxy", "primary")
        conn_status["consecutive_failures"] = failover.get("consecutive_failures", 0)
        conn_status["switch_count"] = failover.get("switch_count", 0)
        conn_status["backup_enabled"] = config.get("BACKUP_ENABLED", "0") == "1"
        conn_status["gateway_forced_down"] = False  # TODO: could read from config.xml but expensive

        connections.append(conn_status)

    return {"connections": connections}


def main():
    # Optional: filter by name
    name_filter = sys.argv[1] if len(sys.argv) > 1 else None

    result = get_status()

    if name_filter:
        result["connections"] = [
            c for c in result["connections"] if c["name"] == name_filter
        ]

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
