#!/usr/local/bin/python3

"""
status.py — Output JSON status of all proxy gateway connections.
Called by configd: configctl proxygateway status
"""

import json
import os
import subprocess
import sys

RUNDIR = "/var/run/proxygateway"


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
        }
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
