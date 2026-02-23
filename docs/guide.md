# os-proxygateway User Guide

## Overview

os-proxygateway is an OPNsense plugin that converts remote SOCKS5 and HTTP/HTTPS
proxy servers into standard OPNsense gateway interfaces. This lets you route traffic
from specific devices, VLANs, or subnets through any proxy using standard OPNsense
firewall rules — without configuring anything on the client devices themselves.

### How It Works

```
┌──────────────┐     ┌──────────────────────────────────┐     ┌──────────────┐
│  LAN Device  │────▶│          OPNsense                │────▶│ Proxy Server │
│ (10.0.1.50)  │     │                                  │     │ (external)   │
│              │     │  Firewall Rule:                   │     │              │
│ No proxy     │     │  src 10.0.1.50 → gw PROXYGW_vpn │     │ SOCKS5/HTTP  │
│ config needed│     │                                  │     │              │
└──────────────┘     │  pgw_vpn (tun) ──▶ tun2socks ───┼────▶│              │
                     └──────────────────────────────────┘     └──────────────┘
```

1. You configure a proxy connection (e.g., a SOCKS5 server).
2. The plugin creates a tunnel interface (`pgw_<name>`) and runs `tun2socks` to
   bridge it to the proxy.
3. OPNsense registers this tunnel as a gateway (`PROXYGW_<NAME>`).
4. You create firewall rules to route traffic from specific sources through that gateway.
5. Traffic from those sources goes through the tunnel and out via the proxy.
   The client device has no idea it's being proxied.

---

## Installation

### Quick Install (on the OPNsense box)

```sh
# Clone the repository
git clone https://github.com/DaneBA/os-proxygateway.git
cd os-proxygateway

# Install everything (plugin + tun2socks binary)
make install
```

This will:
- Install all plugin files to the correct OPNsense directories
- Download the `tun2socks` binary (v2.6.0)
- Create log and runtime directories
- Restart configd and the web GUI
- Configure log rotation

### Manual Install (plugin only)

```sh
make install-plugin
make activate
```

Then install `tun2socks` separately:

```sh
fetch -o /tmp/tun2socks.zip \
  https://github.com/xjasonlyu/tun2socks/releases/download/v2.6.0/tun2socks-freebsd-amd64.zip
unzip -o /tmp/tun2socks.zip -d /tmp/
mv /tmp/tun2socks-freebsd-amd64 /usr/local/bin/tun2socks
chmod +x /usr/local/bin/tun2socks
```

### Uninstall

```sh
make uninstall
```

---

## Configuration

### Step 1: Enable the Plugin

1. Go to **Services → Proxy Gateway → Connections**
2. Check **Enable Proxy Gateway**
3. Set the **Log Level** (default: warning)
4. Click **Apply**

### Step 2: Add a Proxy Connection

1. Click the **+** button to add a new connection.
2. Fill in the fields:

| Field | Description | Example |
|-------|-------------|---------|
| **Enabled** | Activate this connection | ✓ |
| **Name** | Alphanumeric identifier (max 16 chars) | `vpn1` |
| **Description** | Friendly name | `US East Proxy` |
| **Proxy Server Interface** | OPNsense interface the proxy is reachable through (default: `wan`). Set to the LAN interface name if the proxy is on a local network (e.g., `opt1` for a Tailscale proxy on LAN2). Find the name under **Interfaces → Assignments** | `wan` |
| **Proxy Type** | Protocol | SOCKS5 / HTTP / HTTPS |
| **Proxy Server** | IP or hostname of the proxy | `203.0.113.10` |
| **Proxy Port** | Port number | `1080` |
| **Authentication** | Enable if proxy needs user/pass | |
| **Tunnel Address** | Local tunnel IP (auto-assigned if blank) | `172.31.42.1` |
| **Tunnel MTU** | MTU size (default 1500) | `1500` |
| **DNS Mode** | `tunnel` routes DNS through proxy; `custom` uses a specific server | `tunnel` |
| **Health Check** | Enable periodic connectivity probes | ✓ |
| **Gateway Priority** | Lower = preferred in Gateway Groups | `255` |
| **Kill Switch** | Drop traffic if tunnel goes down | |

3. Click **Save**, then **Apply**.

### Step 3: Verify the Connection

Go to **Services → Proxy Gateway → Diagnostics** to see:
- Connection status (Online/Offline)
- Tunnel addresses
- Latency
- tun2socks PID
- Live logs

Click **Test** next to a connection to run an on-demand health check.

---

## Routing Traffic

The core use case: force traffic from specific devices or networks through a proxy
gateway. This is all done through standard OPNsense firewall rules.

### Route a Specific Device (Same LAN)

**Scenario**: You have a device at `10.0.1.50` on your LAN and want all its traffic
to go through proxy connection `vpn1`.

1. Go to **Firewall → Rules → LAN**
2. Add a new rule:

| Setting | Value |
|---------|-------|
| Action | Pass |
| Interface | LAN |
| Direction | in |
| Source | Single host: `10.0.1.50` |
| Destination | any |
| Gateway | `PROXYGW_VPN1` |

3. Save and Apply.

All traffic from `10.0.1.50` now routes through the `vpn1` proxy. The device itself
needs no configuration changes.

### Route a Subnet (Same LAN)

**Scenario**: Route an entire subnet `10.0.1.0/24` through the proxy.

Same as above, but set **Source** to `10.0.1.0/24` (network).

### Route a VLAN (Different LAN Segment)

**Scenario**: You have a VLAN (e.g., VLAN 30 - IoT devices on `10.0.30.0/24`) and
want all its traffic proxied.

1. Ensure the VLAN interface is configured in OPNsense
   (**Interfaces → Assignments → VLANs**)
2. Go to **Firewall → Rules → [VLAN30 interface]**
3. Add a rule:

| Setting | Value |
|---------|-------|
| Action | Pass |
| Interface | VLAN30 (or whatever you named it) |
| Source | VLAN30 net |
| Destination | any |
| Gateway | `PROXYGW_VPN1` |

4. Save and Apply.

### Route Multiple Devices Through Different Proxies

**Scenario**: Device A goes through proxy1, Device B goes through proxy2.

Create two proxy connections (`proxy1`, `proxy2`), then create two firewall rules
on your LAN interface:

**Rule 1** (higher priority — place first):
- Source: Device A IP → Gateway: `PROXYGW_PROXY1`

**Rule 2**:
- Source: Device B IP → Gateway: `PROXYGW_PROXY2`

Firewall rules are evaluated top-to-bottom. The first matching rule wins.

### Route Traffic from a Different Subnet/LAN

**Scenario**: You have two LANs — LAN1 (`10.0.1.0/24`) and LAN2 (`10.0.2.0/24`).
OPNsense routes between them. You want LAN2 traffic to go through the proxy.

1. Ensure both LAN interfaces are configured in OPNsense.
2. Go to **Firewall → Rules → LAN2**
3. Add a rule:

| Setting | Value |
|---------|-------|
| Action | Pass |
| Interface | LAN2 |
| Source | LAN2 net |
| Destination | any |
| Gateway | `PROXYGW_VPN1` |

4. Save and Apply.

**Important**: OPNsense must be the default gateway for devices on LAN2 for this
to work. If devices on LAN2 use a different gateway, OPNsense never sees their traffic.

### Route an Isolated IoT LAN Through a LAN-side Proxy (e.g., Tailscale SOCKS5)

**Scenario**: You have two LAN segments — LAN2 (`10.0.2.0/24`, your main network) and
LAN3 (`10.0.3.0/24`, IoT devices). A firewall rule blocks LAN3 from directly accessing
LAN2. You are running a Tailscale SOCKS5 proxy on a device in LAN2 (e.g., at
`10.0.2.10:1055`) and want a specific IoT device (e.g., `10.0.3.50`) to reach the
Tailscale network through that proxy — without opening LAN3 → LAN2 directly.

Because the proxy server is on LAN2 (not on the internet via WAN), you must tell the
plugin which OPNsense interface is used to reach the proxy. This sets the correct
anti-routing-loop firewall rule.

#### Step 1: Find the OPNsense internal interface name for LAN2

Go to **Interfaces → Assignments**. Find the row for your LAN2 interface and note the
name shown in the **Interface** column (e.g., `opt1`, `lan`, `opt2`). This is the
internal name you will use below.

#### Step 2: Add a proxy connection

1. Go to **Services → Proxy Gateway → Connections**
2. Click **+** and fill in:

| Field | Value |
|-------|-------|
| **Enabled** | ✓ |
| **Name** | `tailscale` |
| **Description** | `Tailscale via LAN2` |
| **Proxy Server Interface** | The internal name for LAN2 (e.g., `opt1`) |
| **Proxy Type** | SOCKS5 |
| **Proxy Server** | `10.0.2.10` (IP of the Tailscale SOCKS5 proxy on LAN2) |
| **Proxy Port** | `1055` (or whichever port Tailscale's SOCKS5 proxy uses) |
| **DNS Mode** | `tunnel` (routes DNS through the Tailscale network) |
| **Kill Switch** | ✓ (optional — drops traffic if the tunnel goes down) |

3. Click **Save**, then **Apply**.

#### Step 3: Add a firewall rule on LAN3

1. Go to **Firewall → Rules → [LAN3 interface]**
2. Add a rule **above** any existing LAN3 → LAN2 block rules:

| Setting | Value |
|---------|-------|
| Action | Pass |
| Interface | LAN3 |
| Direction | in |
| Source | Single host: `10.0.3.50` (your IoT device) |
| Destination | any |
| Gateway | `PROXYGW_TAILSCALE` |

3. Save and Apply.

Traffic from `10.0.3.50` now routes through the Tailscale SOCKS5 proxy on LAN2.
The IoT device has no direct access to LAN2 — the only path is through the proxy.

#### Verify the configuration

- Go to **Services → Proxy Gateway → Diagnostics** and confirm the `tailscale`
  connection shows **Online**.
- From the IoT device, check your exit IP (e.g., `curl https://ifconfig.me`) — it
  should match the Tailscale exit node, not your WAN IP.
- Confirm the existing LAN3 → LAN2 block rules are still in place and that direct
  access is still blocked.

**Important**: OPNsense must be the default gateway for the IoT device (LAN3) for this
to work. If the device uses another gateway, OPNsense never sees its traffic.

---

## Blocking Traffic (Kill Switch)

A kill switch ensures that if the proxy tunnel goes down, traffic from the routed
devices is **dropped** rather than leaking through the normal WAN gateway.

### Method 1: Per-Connection Kill Switch (Built-in)

When configuring a connection, enable the **Kill Switch** option. This tells OPNsense
to drop traffic destined for that gateway when the tunnel is detected as down.

### Method 2: Firewall Rule Kill Switch

For more control, create firewall rules manually:

1. **Rule 1** (pass through proxy): Source: device IP → Gateway: `PROXYGW_VPN1`
2. **Rule 2** (block fallback): Source: device IP → Action: **Block**

Place Rule 2 directly below Rule 1. If the gateway is down and Rule 1 can't match,
Rule 2 blocks the traffic instead of falling through to the default route.

### Method 3: Gateway Groups with Failover

Use OPNsense Gateway Groups to define failover behavior:

1. Go to **System → Gateways → Groups**
2. Create a group with `PROXYGW_VPN1` at Tier 1 and `PROXYGW_VPN2` at Tier 2
3. Use the Gateway Group as the gateway in your firewall rule

If `vpn1` goes down, traffic automatically fails over to `vpn2`.

---

## Logs and Diagnostics

### Viewing Logs

Go to **Services → Proxy Gateway → Diagnostics**.

The log viewer shows structured, timestamped logs from all components:

```
2026-02-23T14:30:00Z [INFO ] [setup     ] [vpn1            ] Interface: pgw_vpn1
2026-02-23T14:30:00Z [INFO ] [setup     ] [vpn1            ] Tunnel: 172.31.42.1 <-> 172.31.42.2 (MTU: 1500)
2026-02-23T14:30:01Z [INFO ] [setup     ] [vpn1            ] Gateway peer: 172.31.42.2 | PID: 12345
```

Each log line includes:
- **Timestamp** — UTC ISO 8601 format
- **Level** — DEBUG, INFO, WARN, ERROR
- **Component** — Which script produced the message (setup, teardown, healthcheck, reconfig)
- **Connection** — Which proxy connection the message relates to
- **Message** — The actual log content

### Filtering Logs

Use the dropdown in the log viewer to filter by connection name, or select
"All connections" to see everything merged and sorted by timestamp.

### Clearing Logs

Click the **Clear Logs** button to wipe log files. You can clear logs for a specific
connection or all connections at once. This is useful to eliminate old noise when
troubleshooting.

### Log Levels

Set the log level under **Services → Proxy Gateway → Connections** (General settings):

| Level | What Gets Logged |
|-------|-----------------|
| **debug** | Everything, including internal state changes and subprocess output |
| **info** | Normal operations: setup, teardown, health check results |
| **warning** | Potential issues: forced kills, probe failures, missing files |
| **error** | Failures: process crashes, missing binaries, invalid configs |

### Log Rotation

Logs are automatically rotated by FreeBSD's `newsyslog`. Each log file is rotated
when it reaches 1 MB, with 5 compressed archives kept. No manual maintenance needed.

### Log Files on Disk

| File | Purpose |
|------|---------|
| `/var/log/proxygateway/<name>.log` | Per-connection log (setup, teardown, health checks, tun2socks output) |
| `/var/log/proxygateway/reconfigure.log` | Reconfiguration orchestration log |

---

## Troubleshooting

### Connection shows "Offline" in Diagnostics

1. Check the logs for the specific connection in Diagnostics.
2. Run a manual health check by clicking **Test**.
3. Verify the proxy server is reachable from OPNsense:
   ```sh
   # Test SOCKS5 proxy
   curl -x socks5://proxy_ip:port http://cp.cloudflare.com

   # Test HTTP proxy
   curl -x http://proxy_ip:port http://cp.cloudflare.com
   ```
4. Check if `tun2socks` is running:
   ```sh
   ps aux | grep tun2socks
   ```
5. Check the tunnel interface:
   ```sh
   ifconfig pgw_<name>
   ```

### Traffic isn't being routed through the proxy

1. Verify the firewall rule is correct and references the right gateway.
2. Check that the gateway appears in **System → Gateways → Single**. Look for
   `PROXYGW_<NAME>`.
3. Ensure the device's traffic is actually hitting OPNsense (check with
   **Firewall → Log Files → Live View**).
4. Confirm the connection is "Online" in Diagnostics.

### DNS leaks

If DNS queries bypass the proxy:

1. Set **DNS Mode** to `tunnel` on the connection — this routes DNS through
   the proxy tunnel.
2. Alternatively, set **DNS Mode** to `custom` and specify a DNS server reachable
   only through the proxy.
3. For complete DNS leak prevention, add firewall rules to block port 53 from
   the routed devices to any destination *except* through the proxy gateway.

### tun2socks won't start

1. Verify the binary exists and is executable:
   ```sh
   ls -la /usr/local/bin/tun2socks
   /usr/local/bin/tun2socks --version
   ```
2. Check if the tun device can be created:
   ```sh
   ifconfig tun create name pgw_test
   ifconfig pgw_test destroy
   ```
3. Review the connection log in `/var/log/proxygateway/<name>.log`.

### Applying changes has no effect

1. Restart configd: `service configd restart`
2. Re-apply from the web GUI.
3. Check `/tmp/PHP_errors.log` for PHP errors.

---

## Architecture Reference

### Components

| Component | Role |
|-----------|------|
| `tun2socks` | Creates a TUN device and forwards captured packets through a proxy |
| `setup.sh` | Creates the tunnel interface and starts tun2socks for a connection |
| `teardown.sh` | Stops tun2socks and destroys the tunnel interface |
| `reconfigure.py` | Diffs desired vs. running state and orchestrates setup/teardown |
| `healthcheck.sh` | Probes connectivity through the tunnel |
| `proxygateway.inc` | OPNsense plugin hooks: services, devices, firewall rules, syslog |

### Network Topology

Each connection creates:
- A TUN device: `pgw_<name>` (e.g., `pgw_vpn1`)
- A point-to-point tunnel: local IP ↔ peer IP (from `172.31.0.0/16`)
- A gateway: `PROXYGW_<NAME>` (auto-registered by OPNsense)
- An outbound NAT rule on the tunnel interface
- A WAN rule allowing OPNsense to reach the upstream proxy (prevents routing loops)

### Supported Proxy Types

| Type | Protocol | Authentication |
|------|----------|---------------|
| SOCKS5 | `socks5://` | Username/Password |
| SOCKS5 + TLS | `socks5://` with TLS | Username/Password |
| HTTP CONNECT | `http://` | Username/Password |
| HTTPS CONNECT | `http://` with TLS | Username/Password |

---

## API Reference

All endpoints are under `/api/proxygateway/`.

### Connections

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/connection/searchItem` | List connections |
| GET | `/connection/getItem/{uuid}` | Get connection details |
| POST | `/connection/addItem` | Create connection |
| POST | `/connection/setItem/{uuid}` | Update connection |
| POST | `/connection/delItem/{uuid}` | Delete connection |
| POST | `/connection/toggleItem/{uuid}` | Enable/disable |

### Service

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/service/reconfigure` | Apply configuration changes |
| GET | `/service/status` | Get service status |

### Diagnostics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/diagnostics/getStatus` | Full status of all connections |
| POST | `/diagnostics/testConnection` | Trigger health check |
| GET | `/diagnostics/getLogs?name=&lines=` | Fetch log lines |
| GET | `/diagnostics/getLogConnections` | List connections with logs |
| POST | `/diagnostics/clearLogs` | Clear log files |
