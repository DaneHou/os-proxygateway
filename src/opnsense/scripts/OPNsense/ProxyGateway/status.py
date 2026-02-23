#!/usr/local/bin/python3

"""
status.py — Output JSON status of all proxy gateway connections.
Called by configd: configctl proxygateway status
"""

import glob
import json
import os
import sys

RUNDIR = "/var/run/proxygateway"


def get_status():
    """Collect status of all connections."""
    connections = []

    for conf_path in sorted(glob.glob(os.path.join(RUNDIR, "*.conf"))):
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

        # Check interface
        iface = config.get("IFACE", f"pgw_{name}")
        iface_exists = os.path.exists(f"/dev/{iface}") or \
            os.system(f"ifconfig {iface} >/dev/null 2>&1") == 0

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
            "status": "up" if process_alive and iface_exists else "down",
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
