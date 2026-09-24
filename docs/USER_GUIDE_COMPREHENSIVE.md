# Comprehensive User Guide: OS Proxy Gateway

**Version:** 1.2.0
**Last Updated:** 2026-09-24
**Target Audience:** OPNsense administrators

---

## Table of Contents

1. [Introduction](#introduction)
2. [How It Works](#how-it-works)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Configuration Guide](#configuration-guide)
6. [Firewall Rule Examples](#firewall-rule-examples)
7. [Use Case Scenarios](#use-case-scenarios)
8. [Troubleshooting](#troubleshooting)
9. [API Reference](#api-reference)

---

## Introduction

### What is OS Proxy Gateway?

OS Proxy Gateway is an OPNsense plugin that converts remote SOCKS5, HTTP CONNECT and Shadowsocks proxy servers into standard OPNsense gateway interfaces. This enables you to route network traffic through proxies using native firewall rules, without requiring any client-side configuration.

### Key Benefits

✅ **Zero Client Configuration**
- No proxy settings needed on devices
- Works with all applications (even those that don't support proxies)
- Transparent to end users

✅ **Native OPNsense Integration**
- Proxies appear as standard gateways
- Use familiar firewall rules
- Gateway groups for failover/load balancing
- Full monitoring and health checks

✅ **Flexible Traffic Routing**
- Route specific devices through different proxies
- Per-subnet routing
- Destination-based routing
- Time-based routing (with schedules)

✅ **Comprehensive Monitoring**
- Real-time connection status with traffic stats and uptime
- Periodic health checks with history (green/red dot indicators)
- Speed testing (on-demand and scheduled)
- Detailed logging

✅ **Automatic Failover**
- Backup proxy per connection with automatic switch on failure
- Auto-failback when primary proxy recovers
- Gateway force-down when no backup available
- Configurable failure threshold (fixed 5-minute failback cooldown)

### Use Cases

1. **Privacy-Separated Browsing**
   - Different household members use different proxy connections
   - IoT devices routed through inspection proxy

2. **Geo-Unlocking**
   - Route streaming device through regional proxy
   - Keep work traffic direct

3. **Security Segmentation**
   - Untrusted devices through audit proxy
   - Guest network through filtering proxy

4. **Redundancy**
   - Automatic failover between multiple proxy providers
   - Load balancing across multiple proxies

---

## How It Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      OPNsense Firewall                          │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│  │ Client A │  │ Client B │  │ Client C │                     │
│  │ 192.168  │  │ 192.168  │  │ 192.168  │                     │
│  │  .1.100  │  │  .1.101  │  │  .1.102  │                     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                     │
│       │              │              │                            │
│       │              │              │                            │
│  ┌────▼──────────────▼──────────────▼─────┐                    │
│  │         Firewall Rules Engine           │                    │
│  │  ┌──────────────────────────────────┐  │                    │
│  │  │ Client A → Gateway: PROXYGW_US   │  │                    │
│  │  │ Client B → Gateway: PROXYGW_EU   │  │                    │
│  │  │ Client C → Gateway: Default WAN  │  │                    │
│  │  └──────────────────────────────────┘  │                    │
│  └────┬──────────────┬──────────────┬─────┘                    │
│       │              │              │                            │
│       │              │              └─────────────┐              │
│       │              │                            │              │
│  ┌────▼────┐    ┌────▼────┐                ┌─────▼────┐         │
│  │ pgw_us  │    │ pgw_eu  │                │ WAN      │         │
│  │ TUN Dev │    │ TUN Dev │                │ em0      │         │
│  │172.31.1 │    │172.31.2 │                │ (direct) │         │
│  └────┬────┘    └────┬────┘                └─────┬────┘         │
│       │              │                            │              │
│  ┌────▼────┐    ┌────▼────┐                     │              │
│  │tun2socks│    │tun2socks│                     │              │
│  │process  │    │process  │                     │              │
│  └────┬────┘    └────┬────┘                     │              │
│       │              │                            │              │
└───────┼──────────────┼────────────────────────────┼──────────────┘
        │              │                            │
        │  WAN         │  WAN                      │  WAN
        │              │                            │
        ▼              ▼                            ▼
   ┌─────────┐    ┌─────────┐              ┌──────────────┐
   │US Proxy │    │EU Proxy │              │   Internet   │
   │Server   │    │Server   │              │   (Direct)   │
   │SOCKS5   │    │HTTP     │              │              │
   │1.2.3.4  │    │5.6.7.8  │              │              │
   │:1080    │    │:8080    │              │              │
   └─────────┘    └─────────┘              └──────────────┘
```

### Component Flow

```
 User Request
      │
      ▼
 Firewall Rule Match
      │
      ├─ Match: PROXYGW_US ──────┐
      │                           │
      ├─ Match: PROXYGW_EU ──────┤
      │                           │
      └─ No Match: Default WAN   │
                                  │
                                  ▼
                          TUN Interface (pgw_xxx)
                                  │
                                  ▼
                          tun2socks Process
                                  │
                                  ▼
                          Proxy Server
                                  │
                                  ▼
                          Internet Destination
```

### Traffic Path Detail

1. **Client Sends Request:** Device sends traffic to destination
2. **Routing Decision:** OPNsense checks firewall rules for gateway
3. **Gateway Matched:** Traffic directed to proxy gateway (pgw_xxx)
4. **TUN Interface:** Packet enters tunnel interface
5. **tun2socks Processing:** Userland process captures packet
6. **Proxy Protocol:** tun2socks encapsulates in SOCKS5/HTTP CONNECT/Shadowsocks
7. **Proxy Connection:** Traffic sent to proxy server
8. **Proxy Forwarding:** Proxy forwards to final destination
9. **Return Path:** Response follows same path in reverse

---

## Installation

### Prerequisites

Before installing, ensure you have:

✅ **System Requirements:**
- OPNsense 24.7 or later
- FreeBSD 14.x (bundled with OPNsense)
- At least 256 MB free RAM
- 10 MB free disk space

✅ **Network Requirements:**
- At least 2 network interfaces (WAN + LAN)
- One or more proxy servers (SOCKS5, HTTP CONNECT or Shadowsocks)
- Internet connectivity on WAN

✅ **Access Requirements:**
- Root/administrative access to OPNsense
- SSH access (for installation from source)
- Web UI access

### Installation

```bash
# SSH to your OPNsense box as root
ssh root@opnsense.local

# Clone the repository
git clone https://github.com/DaneHou/os-proxygateway.git ~/os-proxygateway
cd ~/os-proxygateway

# Install the plugin (downloads tun2socks, installs files, restarts services)
make install
```

`make install` downloads the tun2socks release for your architecture and
verifies it against a pinned SHA256 checksum; if the checksum does not match,
the install stops and nothing is installed.

Hard-refresh your browser (Ctrl+Shift+R) after install. The plugin appears
under **Services > Proxy Gateway**.

### Updating

```bash
cd ~/os-proxygateway
git pull
make install-plugin && make activate
```

### Post-Installation Verification

```bash
# Check if service is registered
pluginctl -s | grep proxygateway

# Verify tun2socks binary
/usr/local/bin/tun2socks --version
```

### Directory Structure

After installation, the following structure is created:

```
/usr/local/
├── bin/
│   └── tun2socks                           # TUN to SOCKS/HTTP binary
├── etc/
│   ├── newsyslog.conf.d/
│   │   └── proxygateway.conf               # Log rotation config
│   └── rc.d/
│       └── opnsense-proxygateway           # Service script
├── opnsense/
│   ├── mvc/
│   │   └── app/
│   │       ├── controllers/
│   │       │   └── OPNsense/ProxyGateway/  # API & UI controllers
│   │       ├── models/
│   │       │   └── OPNsense/ProxyGateway/  # Data models
│   │       └── views/
│   │           └── OPNsense/ProxyGateway/  # UI templates
│   ├── scripts/
│   │   └── OPNsense/ProxyGateway/          # Backend scripts
│   └── service/
│       └── conf/actions.d/
│           └── actions_proxygateway.conf    # configd actions

/var/run/proxygateway/                       # Runtime files
/var/log/proxygateway/                       # Log files
```

---

## Quick Start

### 5-Minute Setup

This guide will get you routing traffic through a proxy in 5 minutes.

**Prerequisites:**
- OPNsense installed and configured
- Access to a SOCKS5, HTTP CONNECT or Shadowsocks proxy server

#### Step 1: Create Proxy Connection

1. Navigate to **Services > Proxy Gateway > Connections**
2. In the general settings at the top of the page, check **Enable Proxy Gateway**
   (off by default) and click **Save**
3. Click **+** to add a connection
4. Fill in:
   - **Name:** `myproxy`
   - **Enabled:** checked
   - **Type:** SOCKS5
   - **Server:** `proxy.example.com`
   - **Port:** `1080`
   - (If auth needed: enable **Authentication**, fill username/password)
   - Leave **Outbound NAT** checked (default)
5. Click **Save**, then **Apply**

#### Step 2: Check the Interface and Gateway

Nothing needs to be assigned or created by hand. On Apply the plugin:

- assigns the `pgw_myproxy` interface in config.xml (visible under
  **Interfaces > Assignments**) and configures its tunnel address,
- creates the gateway `PROXYGW_MYPROXY` (visible under **System > Gateways**),
- registers outbound NAT on `pgw_myproxy` for private (RFC1918) source
  networks: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.

You only need a manual outbound NAT rule (**Firewall > NAT > Outbound**, Hybrid
mode, interface `pgw_myproxy`, translation: interface address) if you uncheck
**Outbound NAT** or route clients whose source addresses are not RFC1918.

#### Step 3: Create Firewall Rule

1. Navigate to **Firewall > Rules > LAN**
2. Add a rule **above** the default allow rule:
   - **Action:** Pass
   - **Source:** `192.168.1.100` (your test device)
   - **Destination:** any
   - **Gateway:** `PROXYGW_MYPROXY`
3. Click **Save**, then **Apply Changes**

#### Step 4: Test

1. On device 192.168.1.100, visit https://ifconfig.me
   - Should show the proxy server's IP address
2. Check **Services > Proxy Gateway > Diagnostics** — status should be **UP**

---

## Configuration Guide

### Connection Settings

Connections are edited in **Services > Proxy Gateway > Connections** (click
**+** or the edit icon). The dialog is split into the sections below. After
saving, click **Apply** to start, restart or stop connections.

#### General

**Enabled** (Checkbox, default: checked)
- ✓ Checked: Connection active (tunnel, interface and gateway are created)
- ✗ Unchecked: Connection stopped; configuration is kept, but the `pgw_<name>`
  interface assignment and `PROXYGW_<NAME>` gateway are removed

**Name** (Required)
- 1-16 characters
- Letters, digits and underscore only
- Example: `us_proxy`, `corp_proxy`, `backup_1`
- Used in interface name `pgw_<name>` and gateway name `PROXYGW_<NAME>`
  (upper-cased)

**Description** (Optional)
- Up to 64 characters: letters, digits, spaces, `-`, `_`, `.`
- Used as the interface description when the interface is auto-assigned
- Example: "US West Coast Proxy for Streaming"

#### Proxy Server

**Proxy Server Interface** (Dropdown, default: WAN)
- The OPNsense interface through which the proxy server is reachable
- Example: for a Tailscale SOCKS5 proxy on a host in LAN2, select LAN2
- Used for the anti-routing-loop rules that keep tun2socks' own connection to
  the proxy off the tunnel

**Type** (Dropdown - Required, default: SOCKS5)
- `SOCKS5`: Standard SOCKS5 proxy (supports TCP + UDP)
- `HTTP CONNECT`: HTTP proxy using CONNECT method (TCP only)
- `Shadowsocks`: Shadowsocks server (encrypted, optional obfs)

> **Note:** SOCKS5 and HTTP CONNECT are unencrypted between OPNsense and the
> proxy — credentials and destination hostnames are visible on that path.
> tun2socks has no TLS transport to the proxy; use Shadowsocks, or run the
> tunnel over a VPN, if that path is untrusted.

**Server** (Required)
- Hostname or IP address
- Examples:
  - `proxy.example.com`
  - `192.168.100.50`
  - `[2001:db8::1]` (IPv6, in brackets)

**Port** (Required, default: 1080)
- 1-65535
- Common ports:
  - SOCKS5: 1080
  - HTTP: 8080, 3128
  - Shadowsocks: as configured on the server (e.g. 8388)

**Authentication** (Checkbox)
- ✓ Required for proxies needing authentication (SOCKS5 / HTTP CONNECT)
- ✗ Anonymous/open proxies
- Not used for Shadowsocks — use the Shadowsocks Password instead

**Username** (Required if Authentication is enabled)
- 1-64 characters
- Allowed: alphanumeric, `@`, `.`, `_`, `-`
- Example: `user@company.com`, `proxy_user`

**Password** (Required if Authentication is enabled)
- 1-128 characters, any printable ASCII (including `@ : / ? # %` and spaces)
- Special characters are URL-encoded automatically; the password is never
  passed on a command line, so it does not appear in process listings (`ps`)
- ⚠️ **Security Note:** Stored in plaintext in config.xml (like other OPNsense
  credentials)
- Recommendation: Use strong, unique passwords

#### Shadowsocks Settings

Shown only when **Type** is Shadowsocks.

**Encryption Method** (Dropdown, default: AES-256-GCM)
- AEAD ciphers only: `AES-128-GCM`, `AES-256-GCM`, `ChaCha20-IETF-Poly1305`,
  `XChaCha20-IETF-Poly1305`
- Must match the server

**Shadowsocks Password**
- The Shadowsocks shared secret (not proxy authentication)
- Up to 128 printable ASCII characters; handled the same way as the proxy
  password (URL-encoded, never in process listings)

**Obfuscation** (Dropdown, default: None)
- Optional simple-obfs plugin: `HTTP (obfs-http)` or `TLS (obfs-tls)`
- Must match the server

**Obfuscation Host** (Shown when Obfuscation is set)
- Hostname sent as the HTTP Host header (obfs-http) or TLS SNI (obfs-tls)
- Example: `www.example.com`

#### Tunnel Settings

**Tunnel Address** (Optional)
- Auto-assigned from 172.31.0.0/16 if left empty
- Manual example: `172.31.10.1`
- Format: IPv4 address only
- Note: Address is for local tunnel endpoint (/32 point-to-point)

**MTU** (Optional)
- Default: 1500
- Range: 1280-9000
- Lower if proxy is over VPN or has small MTU
- Recommended: 1500 (standard), 1420 (over VPN)

**Outbound NAT** (Checkbox, default: checked)
- ✓ Automatically registers outbound NAT on the `pgw_<name>` interface for
  private source networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
- ✗ No automatic NAT — add your own rule under **Firewall > NAT > Outbound**
- Needed whenever LAN/VPN traffic is policy-routed through this gateway; also
  add a manual rule for non-RFC1918 source networks

#### Health Check

Health checks are run by the watchdog every 60 seconds (the interval is fixed)
while **Auto-reconnect (Watchdog)** is enabled in the global settings. Each
probe fetches the target URL through the proxy; the result and latency are
recorded in the health history shown on the Diagnostics page, and drive
failover and gateway force-down.

**Enable Health Check** (Checkbox, default: checked)
- ✓ Periodic connectivity probes through the proxy
- ✗ No health monitoring — no failover and no automatic force-down for this
  connection
- Required for the backup proxy / failover

**Target URL** (Optional)
- HTTP or HTTPS URL to probe for connectivity
- Default: `http://1.1.1.1/` (Cloudflare; IP-based, so no DNS is needed)
- Custom example: `http://example.com/health`
- A probe fails only if no HTTP response comes back through the proxy
- ⚠️ **Privacy Note:** Default target leaks usage patterns to Cloudflare

#### Gateway

**Gateway Priority** (1-255)
- Default: 255
- Lower number = higher priority
- Used when multiple gateways available
- Example: Primary=50, Backup=100

The gateway `PROXYGW_<NAME>` is created with dpinger monitoring disabled
(SOCKS5 cannot carry ICMP), so OPNsense does not mark it offline by itself. It
goes down only when the watchdog forces it down (see **Auto Force-Down
Gateway**).

#### Speed Test

**Test URL** (Optional)
- Direct-download URL used for speed tests on this connection
- Must return a binary file, not an HTML page
- Examples: `http://speedtest.tele2.net/10MB.zip`,
  `https://proof.ovh.net/files/10Mb.dat`
- Default: Tele2 10 MB download
- Each test downloads the file through the proxy and uses bandwidth

#### Backup Proxy (Failover)

**Enable Backup Proxy** (Checkbox)
- ✓ Enable backup proxy for automatic failover (requires Health Check)
- ✗ No backup (gateway will be forced down on failure if Auto Force-Down
  Gateway is enabled)

**Backup Type** (Dropdown)
- Same options as primary proxy type (SOCKS5, HTTP CONNECT, Shadowsocks)

**Backup Server** (Required if Backup Enabled)
- Hostname or IP of the backup proxy server

**Backup Port** (Required if Backup Enabled, default: 1080)
- Port of the backup proxy server (1-65535)

**Backup Authentication** (Checkbox)
- Enable if backup proxy requires authentication

**Backup Username / Backup Password**
- Credentials for the backup proxy (same rules as primary)

**Backup SS Method / Backup SS Password** (Shown when Backup Type is Shadowsocks)
- Encryption method and shared secret for a Shadowsocks backup server (same
  options as the primary)

**Failover Threshold** (Integer)
- Number of consecutive health check failures before switching to backup
- Default: 3, Range: 1-10
- With 60-second checks, the default threshold means about 3 minutes

**Auto Failback** (Checkbox)
- ✓ Automatically switch back to primary when it recovers (default)
- ✗ Stay on backup until manual intervention
- The primary is probed directly (not through the tunnel); failback requires
  2 consecutive successful probes and happens no sooner than 5 minutes after
  the last switch

### Global Settings

The global settings are shown at the top of **Services > Proxy Gateway >
Connections**.

**Enable Proxy Gateway** (Checkbox, default: off)
- Master switch for entire plugin
- Unchecking stops all connections

**Start connections on boot** (Checkbox, default: on)
- Start all enabled connections when the system boots
- When off, connections start only when you click **Apply**

**Auto-reconnect (Watchdog)** (Checkbox, default: on)
- Runs every 60 seconds: restarts any enabled connection whose tun2socks
  process has died, and runs the periodic health checks that drive failover,
  failback and force-down
- When off, none of these automatic actions happen

**Log Level** (Dropdown)
- `Debug`: Very verbose (development only)
- `Info`: Normal verbosity
- `Warning`: Only warnings and errors (default)
- `Error`: Only errors
- Recommended: `Warning` for production

**Enable Speed Test** (Checkbox, default: off)
- Periodically measures download throughput through each connection; results
  appear on the Diagnostics page
- Each test downloads a file through the proxy and consumes bandwidth

**Test Interval** (Dropdown, default: 15 minutes)
- 5, 15, 30 or 60 minutes

**Auto Force-Down Gateway** (Checkbox, default: on)
- ✓ Sets the gateway to `force_down` when the health check fails
  *Failover Threshold* times in a row and there is no working backup; clears
  it automatically once the connection is healthy again
- ✗ Gateway stays up regardless of health status
- With a backup proxy configured, failover to the backup is tried first

---

## Firewall Rule Examples

### Understanding Gateway Selection

When creating firewall rules, you specify which gateway to use. The plugin registers each proxy as a gateway with name `PROXYGW_<NAME>`.

```
Connection Name: myproxy
Gateway Name:    PROXYGW_MYPROXY
```

### Example 1: Single Device Through Proxy

**Scenario:** Route only one specific device (Smart TV) through US proxy.

**Network Topology:**
```
LAN: 192.168.1.0/24
Smart TV: 192.168.1.100
US Proxy: PROXYGW_US
```

**Firewall Rule:**
```
Action:      Pass
Interface:   LAN
Protocol:    any
Source:      Single host: 192.168.1.100
Destination: any
Gateway:     PROXYGW_US
Description: Smart TV through US proxy
```

**Visual Flow:**
```
Smart TV             OPNsense Firewall          US Proxy
192.168.1.100        pgw_us (tun)              1.2.3.4:1080
     │                      │                        │
     ├─ HTTP Request ──────▶│                        │
     │                      ├─ Match Rule ──────────▶│
     │                      │  (src=.100,            │
     │                      │   gw=PROXYGW_US)       │
     │                      │                        │
     │                      │◀─ SOCKS5 tunnel ──────▶│
     │                      │                        │
     │                      │                   ┌────▼────┐
     │                      │                   │Internet │
     │◀─ Response ──────────│◀─ Via proxy ──────│         │
     │                      │                   └─────────┘
```

### Example 2: Entire Subnet Through Proxy

**Scenario:** Route guest VLAN through filtering proxy.

**Network Topology:**
```
Guest VLAN: 192.168.30.0/24 (VLAN ID: 30)
Corporate Proxy: PROXYGW_CORP
```

**Firewall Rule:**
```
Action:      Pass
Interface:   OPT1 (Guest_VLAN30)
Protocol:    any
Source:      OPT1 net (192.168.30.0/24)
Destination: any
Gateway:     PROXYGW_CORP
Description: Guest network through corporate proxy
```

**Visual Flow:**
```
┌────────────────────────────────────────────────────────┐
│ Guest VLAN 30 (192.168.30.0/24)                       │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Guest 1  │  │ Guest 2  │  │ Guest 3  │           │
│  │  .30.10  │  │  .30.11  │  │  .30.12  │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       └──────────────┴──────────────┘                 │
│                      │                                 │
└──────────────────────┼─────────────────────────────────┘
                       │
            All traffic routed via
           PROXYGW_CORP (filtering)
                       │
                       ▼
              Corporate Proxy Server
              (filters malware, ads)
                       │
                       ▼
                   Internet
```

### Example 3: Destination-Based Routing

**Scenario:** Route traffic to specific destinations through proxy, rest direct.

**Network Topology:**
```
LAN: 192.168.1.0/24
Streaming services: via US proxy
Everything else: direct WAN
```

**Firewall Rules (Order Matters!):**

**Rule 1 (Top):**
```
Action:      Pass
Interface:   LAN
Protocol:    any
Source:      LAN net
Destination: Alias: StreamingServers
Gateway:     PROXYGW_US
Description: Streaming through US proxy
```

**Rule 2 (Below Rule 1):**
```
Action:      Pass
Interface:   LAN
Protocol:    any
Source:      LAN net
Destination: any
Gateway:     default
Description: Everything else direct
```

**Creating Alias (Firewall → Aliases):**
```
Name:    StreamingServers
Type:    Host(s)
Content:
  netflix.com
  hulu.com
  23.246.0.0/18  (Netflix CDN)
  198.45.48.0/20 (Hulu CDN)
```

**Visual Flow:**
```
LAN Device Request
       │
       ├─ netflix.com? ────▶ Match Rule 1 ──▶ PROXYGW_US ──▶ Proxy
       │
       ├─ google.com?  ────▶ Match Rule 2 ──▶ Default WAN ──▶ Direct
       │
       └─ youtube.com? ────▶ Match Rule 2 ──▶ Default WAN ──▶ Direct
```

### Example 4: Built-in Backup Proxy Failover (v0.4.0)

**Scenario:** Primary proxy with automatic failover to backup — no gateway group needed.

**Configuration:**

1. **Create Connection with Backup:**
   ```
   Services → Proxy Gateway → Connections → Edit

   Primary Proxy:
     Type: SOCKS5
     Server: primary-proxy.example.com
     Port: 1080

   Health Check:
     Enable Health Check: ✓

   Backup Proxy:
     Enable Backup Proxy: ✓
     Backup Type: SOCKS5
     Backup Server: backup-proxy.example.com
     Backup Port: 1080
     Failover Threshold: 3
     Auto Failback: ✓
   ```

2. **Apply Changes**

**Behavior:**
```
Normal:    Primary healthy → traffic via primary proxy
Failover:  3 consecutive health failures (checked every 60s) → automatic switch to backup (~2-3s downtime)
Failback:  Primary recovers for 2 probes + 5min cooldown → automatic switch back
```

The watchdog (global **Auto-reconnect (Watchdog)** setting) monitors both
proxies. No manual gateway group setup required.

### Example 4b: Gateway Group Failover (Alternative)

For failover between **separate connections** (not primary/backup on the same connection), use OPNsense gateway groups:

**Network Topology:**
```
Primary: PROXYGW_PRIMARY (priority 1)
Backup:  PROXYGW_BACKUP (priority 2)
```

**Step 1: Create Gateway Group**

Navigate to **System → Gateways → Groups**

```
Name:        ProxyFailover
Description: Primary proxy with backup
Gateway:     PROXYGW_PRIMARY (Tier 1)
Gateway:     PROXYGW_BACKUP (Tier 2)
Trigger:     Member Down
```

Proxy gateways have dpinger monitoring disabled, so latency/loss triggers never
fire. A member is "down" only when the watchdog forces it down, so keep **Enable
Health Check** on for both connections and **Auto Force-Down Gateway** on in the
global settings.

**Step 2: Create Firewall Rule**
```
Action:      Pass
Interface:   LAN
Protocol:    any
Source:      LAN net (or specific devices)
Destination: any
Gateway:     ProxyFailover (Group)
Description: High-availability proxy routing
```

**Visual Flow:**
```
                    LAN Device
                         │
                         ▼
              ┌──────────────────────┐
              │  Gateway Group       │
              │  "ProxyFailover"     │
              └──────────┬───────────┘
                         │
              ┌──────────▼──────────┐
              │ Primary forced down?│
              │ (health check)      │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  No:  Use Primary   │
              │  Yes: Use Backup    │
              └──────────┬──────────┘
                         │
           ┌─────────────┴────────────┐
           │                          │
      ┌────▼─────┐              ┌────▼─────┐
      │ Primary  │              │ Backup   │
      │ Proxy    │              │ Proxy    │
      │ (Active) │              │(Standby) │
      └────┬─────┘              └────┬─────┘
           │                          │
           └─────────┬────────────────┘
                     │
                     ▼
                 Internet
```

### Example 5: Load Balancing

**Scenario:** Distribute traffic across multiple proxies.

**Network Topology:**
```
Proxy 1: PROXYGW_US1 (weight 1)
Proxy 2: PROXYGW_US2 (weight 1)
Proxy 3: PROXYGW_US3 (weight 2)
```

**Step 1: Create Gateway Group**
```
Name:        ProxyLoadBalance
Description: Load balance across 3 proxies
Gateway:     PROXYGW_US1 (Tier 1, Weight 1)
Gateway:     PROXYGW_US2 (Tier 1, Weight 1)
Gateway:     PROXYGW_US3 (Tier 1, Weight 2)
Trigger:     Member Down
```

**Step 2: Create Firewall Rule**
```
Action:      Pass
Interface:   LAN
Protocol:    any
Source:      LAN net
Destination: any
Gateway:     ProxyLoadBalance
Description: Distribute traffic across proxies
```

**Traffic Distribution:**
```
           LAN Traffic (100 connections)
                      │
                      ▼
          ┌───────────────────────┐
          │ Gateway Group         │
          │ Round-robin by weight │
          └───────────┬───────────┘
                      │
      ┌───────────────┼───────────────┐
      │               │               │
┌─────▼─────┐   ┌────▼─────┐   ┌────▼─────┐
│US1        │   │US2       │   │US3       │
│25 conns   │   │25 conns  │   │50 conns  │
│(weight 1) │   │(weight 1)│   │(weight 2)│
└─────┬─────┘   └────┬─────┘   └────┬─────┘
      └───────────────┴───────────────┘
                      │
                      ▼
                  Internet
```

### Example 6: Time-Based Routing

**Scenario:** Use proxy during business hours, direct after hours.

**Step 1: Create Schedule**

Navigate to **Firewall → Schedules**
```
Name:        BusinessHours
Description: Mon-Fri 9am-5pm
Days:        Monday, Tuesday, Wednesday, Thursday, Friday
Time:        09:00 - 17:00
```

**Step 2: Create Firewall Rules**

**Rule 1 (Business Hours):**
```
Action:      Pass
Interface:   LAN
Protocol:    any
Source:      LAN net
Destination: any
Gateway:     PROXYGW_CORP
Schedule:    BusinessHours
Description: Corporate proxy during work hours
```

**Rule 2 (After Hours):**
```
Action:      Pass
Interface:   LAN
Protocol:    any
Source:      LAN net
Destination: any
Gateway:     default
Description: Direct connection after hours
```

**Timeline:**
```
Monday 9am        Monday 5pm        Tuesday 9am
    │─────────────────│                  │
    │  BusinessHours  │    After Hours   │ BusinessHours
    │                 │                  │
    ▼                 ▼                  ▼
PROXYGW_CORP      Default WAN      PROXYGW_CORP
 (Filtered)         (Direct)         (Filtered)
```

---

## Use Case Scenarios

### Scenario 1: Privacy-Separated Household

**Requirement:**
- Alice: Privacy-focused, wants all traffic through VPN-based SOCKS5
- Bob: Normal browsing, direct connection
- IoT devices: Through filtering proxy

**Network Design:**
```
┌─────────────────────────────────────────────────┐
│ OPNsense (192.168.1.1)                         │
├─────────────────────────────────────────────────┤
│ Alice VLAN 10: 192.168.10.0/24                 │
│   → PROXYGW_VPN                                 │
├─────────────────────────────────────────────────┤
│ Bob VLAN 20: 192.168.20.0/24                   │
│   → Default WAN (direct)                        │
├─────────────────────────────────────────────────┤
│ IoT VLAN 30: 192.168.30.0/24                   │
│   → PROXYGW_FILTER                              │
└─────────────────────────────────────────────────┘
```

**Configuration:**

1. **Create Proxy Connections:**
   - Name: `vpn`, Type: SOCKS5, Server: alice-vpn-proxy.example.com:1080
   - Name: `filter`, Type: HTTP, Server: iot-filter-proxy.local:8080

2. **Create Firewall Rules:**
   ```
   Interface: VLAN10 (Alice)
   Source: VLAN10 net
   Gateway: PROXYGW_VPN

   Interface: VLAN20 (Bob)
   Source: VLAN20 net
   Gateway: default

   Interface: VLAN30 (IoT)
   Source: VLAN30 net
   Gateway: PROXYGW_FILTER
   ```

**Result:**
- Alice's traffic fully private (no ISP visibility)
- Bob's traffic normal speed (no proxy overhead)
- IoT devices filtered for malware/ads

### Scenario 2: Geographic Content Access

**Requirement:**
- Smart TV: Access US Netflix
- Gaming Console: Minimize latency (direct)
- General devices: Direct

**Network Design:**
```
LAN: 192.168.1.0/24
├─ Smart TV (.100)     → PROXYGW_US (US proxy)
├─ Gaming Console (.101) → Default WAN
└─ Other devices       → Default WAN
```

**Configuration:**

1. **Create Proxy Connection:**
   ```
   Name: us
   Type: SOCKS5
   Server: us-proxy.example.com
   Port: 1080
   Auth: enabled (username/password from service)
   ```

2. **Create Firewall Rule:**
   ```
   Action: Pass
   Interface: LAN
   Source: 192.168.1.100 (Smart TV)
   Gateway: PROXYGW_US
   ```

3. **Configure DNS (Optional):**
   - Set the Smart TV to use a public resolver (e.g. 8.8.8.8), so its DNS
     queries are matched by the rule above and resolved via the US proxy
   - The plugin has no DNS setting; if the TV uses OPNsense (Unbound) as its
     resolver, lookups leave through the firewall's own WAN route

**Testing:**
```bash
# On Smart TV (or via SSH if available)
curl ifconfig.me
# Should show US IP address

# Access Netflix
# Should show US content library
```

### Scenario 3: Corporate Remote Office

**Requirement:**
- All office traffic through corporate proxy
- Automatic failover to backup proxy
- No direct Internet if both proxies fail

**Network Design:**
```
Office LAN: 10.0.10.0/24
├─ Primary Proxy: corporate-proxy1.company.com
├─ Backup Proxy: corporate-proxy2.company.com
└─ Both down: traffic dropped (firewall rules)
```

**Configuration:**

1. **Create Proxy Connections:**
   ```
   Connection 1:
   Name: corp_primary
   Type: HTTP
   Server: corporate-proxy1.company.com
   Port: 8080
   Auth: corporate credentials

   Connection 2:
   Name: corp_backup
   Type: HTTP
   Server: corporate-proxy2.company.com
   Port: 8080
   Auth: corporate credentials
   ```
   Keep **Enable Health Check** on for both, and **Auto Force-Down Gateway**
   on in the global settings.

   (Alternatively, use one connection with a **Backup Proxy** — see Example 4.)

2. **Create Gateway Group:**
   ```
   Name: CorporateProxies
   Tier 1: PROXYGW_CORP_PRIMARY
   Tier 2: PROXYGW_CORP_BACKUP
   Trigger: Member Down
   ```

3. **Create Firewall Rules:**
   ```
   Rule 1:
   Action: Pass
   Interface: LAN
   Source: LAN net (10.0.10.0/24)
   Destination: any
   Gateway: CorporateProxies (group)

   Rule 2 (below Rule 1):
   Action: Block
   Interface: LAN
   Source: LAN net (10.0.10.0/24)
   Destination: any
   ```

4. **Prevent fallback to WAN:**
   - **Firewall > Settings > Advanced:** enable *Skip rules when gateway is
     down*, so Rule 1 is skipped (and Rule 2 blocks) when every gateway in the
     group is down, instead of passing traffic via the default route
   - **System > Settings > General:** leave *Allow default gateway switching*
     disabled

**Behavior:**
```
Normal: Primary UP → All traffic via Primary
Failover: Primary DOWN → All traffic via Backup
Emergency: Both forced DOWN → Rule 1 skipped, Rule 2 → Traffic DROPPED
```

### Scenario 4: Developer Test Environment

**Requirement:**
- Test applications through different regional proxies
- Easily switch between proxies
- No modification to application code

**Network Design:**
```
Developer Workstation: 192.168.1.50
Available Proxies:
  - PROXYGW_US
  - PROXYGW_EU
  - PROXYGW_ASIA
  - Default WAN
```

**Configuration Method 1: Multiple Rules (Toggle)**

Create 4 rules, enable only one at a time:

```
Rule 1 (Disabled by default):
Source: 192.168.1.50
Gateway: PROXYGW_US
Description: [DEV] Test via US proxy

Rule 2 (Disabled):
Source: 192.168.1.50
Gateway: PROXYGW_EU
Description: [DEV] Test via EU proxy

Rule 3 (Disabled):
Source: 192.168.1.50
Gateway: PROXYGW_ASIA
Description: [DEV] Test via Asia proxy

Rule 4 (Enabled):
Source: 192.168.1.50
Gateway: default
Description: [DEV] Test direct
```

**Usage:**
1. Disable all rules except desired one
2. Apply changes
3. Test application
4. Check: `curl ifconfig.me` to verify exit IP

**Configuration Method 2: Gateway Group (Quick Switch)**

Create gateway groups for quick switching via GUI dropdown in test scripts.

---

## Troubleshooting

### Connection Won't Start

**Symptom:** Connection shows "Down" or "Not Running" in diagnostics.

**Diagnostic Steps:**

1. **Check System Logs:**
   ```bash
   # Services → Proxy Gateway → Diagnostics → Logs
   # Look for ERROR lines
   ```

2. **Check tun2socks Binary:**
   ```bash
   ls -la /usr/local/bin/tun2socks
   /usr/local/bin/tun2socks --version
   ```

3. **Check Proxy Server Connectivity:**
   ```bash
   # From OPNsense shell:
   nc -zv proxy.example.com 1080
   # Should show: Connection to proxy.example.com 1080 port [tcp/socks] succeeded!
   ```

4. **Check Configuration File:**
   ```bash
   cat /var/run/proxygateway/<name>.conf
   # Verify PROXY_ADDR, PROXY_PORT are correct
   ```

5. **Check Interface:**
   ```bash
   ifconfig pgw_<name>
   # Should show UP status
   ```

**Common Causes:**

| Issue | Cause | Solution |
|-------|-------|----------|
| tun2socks not found | Installation incomplete | Reinstall plugin |
| Proxy unreachable | Network/firewall issue | Check WAN connectivity, firewall rules |
| Authentication failed | Wrong credentials | Verify username/password |
| Permission denied | File permissions | Check /var/run/proxygateway permissions |
| Interface already exists | Duplicate name | Choose different connection name |

### Traffic Not Routing Through Proxy

**Symptom:** Traffic still goes direct even with firewall rule.

**Diagnostic Steps:**

1. **Verify Firewall Rule Order:**
   - Firewall → Rules → [Interface]
   - Ensure proxy rule is ABOVE any default allow rules
   - Rules are processed top-to-bottom, first match wins

2. **Check Rule Match:**
   ```bash
   # Firewall → Log Files → Live View
   # Filter by source IP
   # Verify rule description matches your proxy rule
   ```

3. **Verify Gateway Status:**
   ```bash
   # System → Gateways → Status
   # PROXYGW_<name> should show "Online"
   ```

4. **Test Proxy Directly:**
   ```bash
   # From client device:
   curl --proxy socks5://proxy.example.com:1080 http://ifconfig.me
   # Should show proxy's IP
   ```

5. **Check Client Routing:**
   ```bash
   # On client (if accessible):
   traceroute -n 8.8.8.8
   # First hop should be OPNsense (192.168.1.1)
   ```

**Common Causes:**

| Issue | Cause | Solution |
|-------|-------|----------|
| Wrong gateway selected | Rule uses different gateway | Edit rule, select correct PROXYGW_X |
| Gateway offline | Proxy connection down | Check connection status |
| Rule disabled | Checkbox unchecked | Enable rule |
| NAT missing/conflict | Outbound NAT unchecked, non-RFC1918 source, or manual override | Check the connection's **Outbound NAT** box and Firewall → NAT → Outbound |
| Client-side proxy | Device has proxy configured | Remove client proxy settings |

### Slow Performance / High Latency

**Symptom:** Web pages load slowly, high ping times.

**Diagnostic Steps:**

1. **Measure Baseline Latency:**
   ```bash
   # Services → Proxy Gateway → Diagnostics
   # Check latency_ms for connection
   # Normal: <50ms, Acceptable: <200ms, Slow: >200ms
   ```

2. **Test Without Proxy:**
   - Temporarily disable firewall rule
   - Test same destination directly
   - Compare speed

3. **Check MTU:**
   - Large MTU can cause fragmentation
   - Try reducing MTU to 1420 or 1280
   - Edit connection → Tunnel Settings → MTU

4. **Check Proxy Server Load:**
   - Some proxies rate-limit
   - Try different proxy server
   - Check proxy provider status page

5. **Monitor CPU Usage:**
   ```bash
   top
   # Check tun2socks CPU usage
   # Normal: <10%, High: >30%
   ```

**Optimization Tips:**

```
Reduce MTU: 1500 → 1420 (if over VPN)
Use SOCKS5 instead of HTTP (lower overhead)
Disable scheduled speed tests (they consume proxy bandwidth)
```

### DNS Leaks

**Symptom:** DNS queries go direct instead of through proxy.

The plugin has no DNS setting of its own: DNS is routed like any other traffic.
A query goes through the proxy only if the client sends it to an external
resolver **and** a firewall rule with the proxy gateway matches it.

**Diagnostic Steps:**

1. **Test for DNS Leak:**
   ```bash
   # From client device:
   # Visit: https://dnsleaktest.com
   # Should show the resolver you chose, seen from the proxy's location
   # Should NOT show ISP DNS
   ```

2. **Check Client DNS:**
   ```bash
   # On client device:
   # Windows: ipconfig /all
   # Linux: cat /etc/resolv.conf
   # macOS: scutil --dns
   ```
   If the client uses OPNsense (e.g. 192.168.1.1) as its DNS server, Unbound
   resolves the query itself and sends it out through the firewall's default
   route (WAN), not through the proxy.

3. **Check Firewall DNS Rules:**
   ```bash
   # Firewall → Rules → [Interface]
   # Port 53 traffic to the external resolver must match a rule
   # with Gateway = PROXYGW_<NAME>
   ```

**Fix DNS Leaks:**

**Option 1: Use an External Resolver on the Client**
```
Client (or DHCP server option) DNS: a public resolver, e.g. 1.1.1.1
The proxy-gateway rule for that client then carries its DNS queries too
```

**Option 2: Force DNS Through the Proxy (Firewall Rules)**
```
Rule A (above the proxy rule):
  Action: Pass
  Protocol: TCP/UDP
  Source: <client or subnet>
  Destination: <chosen resolver IP>
  Destination Port: 53 (DNS)
  Gateway: PROXYGW_<NAME>

Rule B (below Rule A):
  Action: Reject
  Protocol: TCP/UDP
  Source: <client or subnet>
  Destination Port: 53 (DNS)
  Description: Block any other DNS
```

> **Note:** HTTP CONNECT proxies carry TCP only, so UDP DNS through an HTTP
> gateway fails. Use a SOCKS5 or Shadowsocks connection for UDP DNS, or have
> clients use DNS over TCP/HTTPS.

### Traffic Leaks to WAN When the Proxy Is Down

**Symptom:** Traffic falls back to WAN when proxy fails.

There is no "kill switch" checkbox in the plugin. Blocking traffic when a proxy
is down is done with the gateway force-down plus standard OPNsense settings.

**How it works:**

1. The watchdog runs a health check every 60 seconds (requires **Enable Health
   Check** on the connection and **Auto-reconnect (Watchdog)** globally)
2. After *Failover Threshold* consecutive failures with no working backup, it
   sets the gateway `PROXYGW_<NAME>` to force-down (requires **Auto Force-Down
   Gateway**), and clears it again once the proxy is healthy
3. What OPNsense does with a rule whose gateway is down depends on the firewall
   settings below

**Configuration:**

1. **Firewall > Settings > Advanced:** enable *Skip rules when gateway is
   down*. Without this, a rule whose gateway is down is still loaded without
   the gateway, so its traffic goes out via the default route (WAN).
2. Add a **Block** rule for the same source directly below the proxy-gateway
   rule, so traffic that is no longer matched by the skipped rule is dropped
   instead of hitting the default LAN allow rule.
3. **System > Settings > General:** leave *Allow default gateway switching*
   disabled.

**Diagnostic Steps:**

1. **Check Gateway Status:**
   ```
   System → Gateways → Status
   PROXYGW_<name> should show as down (force down) after the threshold is reached
   ```

2. **Check the Watchdog Log:**
   ```bash
   tail -f /var/log/proxygateway/watchdog.log
   # Look for "gateway forced down" / "clearing gateway force_down"
   ```

3. **Test:**
   - Stop proxy server
   - Wait for *Failover Threshold* × 60 seconds
   - Try accessing internet from client
   - Should FAIL (no connection)

**Common Issues:**

| Issue | Cause | Solution |
|-------|-------|----------|
| Traffic still flows | Default allow rule matches next | Add a block rule below the proxy rule |
| Traffic goes out WAN | Rule loaded without gateway | Enable *Skip rules when gateway is down* |
| Gateway stays UP | Health check, watchdog or Auto Force-Down disabled | Enable all three |
| Gateway stays UP | Backup proxy is working | Expected: traffic uses the backup |
| Failover to WAN | WAN is a member of the gateway group | Remove WAN from the group |

### Connection Drops Frequently

**Symptom:** Connection state changes UP → DOWN → UP repeatedly.

**Diagnostic Steps:**

1. **Check Health Check Logs:**
   ```bash
   # Services → Proxy Gateway → Diagnostics → Logs
   # Filter by connection name
   # Look for "health check failed" messages
   ```

2. **Adjust Health Check:**
   ```
   Raise Failover Threshold (e.g. 3 → 5) to tolerate brief outages
   Change Target URL: Try a different URL
   Disable temporarily: Test if stability improves
   ```
   The check interval itself is fixed at 60 seconds.

3. **Check Proxy Stability:**
   ```bash
   # From OPNsense shell:
   for i in $(seq 1 10); do
     nc -zv proxy.example.com 1080 && echo "OK" || echo "FAIL"
     sleep 2
   done
   # Should show consistent OK results
   ```

4. **Monitor tun2socks Process:**
   ```bash
   ps aux | grep tun2socks
   # Check if process keeps restarting
   # PID changes = restarts
   ```

**Solutions:**

```
Raise the Failover Threshold (less aggressive)
Switch to more stable proxy provider
Configure a backup proxy (or a gateway group)
Check proxy server capacity/rate limits
Verify proxy server isn't blocking health check requests
```

### Tailscale SOCKS5 Proxy Issues

**Symptom:** Tailscale SOCKS5 proxy connects but has no internet access (only local network).

**Background:**

Tailscale provides a SOCKS5 proxy feature that can be exposed on your local network. When using Tailscale as a SOCKS5 proxy server with this plugin, you may encounter issues where:
- The connection shows as "UP" in diagnostics
- Local network access works
- Internet/external access fails
- Tailscale logs show: `netstack: decrementing connsInFlightByClient because the packet was not handled`

**Root Cause:**

This issue occurs when UDP relay (required for DNS and other UDP protocols) isn't properly configured. While tun2socks supports UDP relay for SOCKS5 proxies, some SOCKS5 implementations like Tailscale require specific UDP timeout settings to maintain the UDP association.

**Solution:**

The plugin automatically adds UDP timeout configuration (300s) for all SOCKS5 connections. If you're experiencing this issue:

1. **Verify Proxy Configuration:**
   ```
   Services → Proxy Gateway → Connections → [Your Tailscale Connection]

   Type: SOCKS5 (not HTTP CONNECT)
   Server: 192.168.20.10 (your Tailscale proxy IP)
   Port: 1055 (or your configured port)
   Proxy Server Interface: the interface where that host lives (e.g. LAN2)
   ```

2. **Check Client DNS:**
   ```
   Clients should query an external resolver (e.g. 1.1.1.1) that is matched
   by the proxy-gateway rule, so DNS goes through the SOCKS5 UDP relay.
   See "DNS Leaks" above.
   ```

3. **Verify Tailscale Proxy is Accessible:**
   ```bash
   # From OPNsense shell:
   nc -zv 192.168.20.10 1055
   # Should show: Connection succeeded
   ```

4. **Check tun2socks Logs for UDP:**
   ```bash
   # View connection logs:
   tail -f /var/log/proxygateway/<connection_name>.log

   # With Log Level = Debug, look for:
   # Using UDP timeout (300s) for SOCKS5 proxy
   ```

5. **Test DNS Resolution:**
   ```bash
   # From a client device routed through the proxy:
   nslookup google.com

   # Should resolve successfully
   ```

**Tailscale-Specific Configuration Tips:**

```
Connection Settings:
  Name: tailscale_proxy
  Proxy Server Interface: interface of the Tailscale machine (e.g. LAN2)
  Type: SOCKS5 (required)
  Server: 192.168.x.x (Tailscale machine's LAN IP)
  Port: 1055 (or your configured port)
  Authentication: Not required (Tailscale handles auth)

Tunnel Settings:
  MTU: 1420 (recommended for Tailscale)
  Outbound NAT: checked

Health Check:
  Enable Health Check: Yes (runs every 60 seconds)
  Target URL: http://1.1.1.1/ (or leave empty for default)
```

**Firewall Considerations:**

If you're running Tailscale on a machine in your LAN (e.g., LAN2 at 192.168.20.10) and want devices on another LAN (e.g., LAN3) to use it:

1. **Allow Access to Tailscale Proxy:**
   ```
   Firewall → Rules → LAN3

   Rule 1:
     Action: Pass
     Protocol: TCP/UDP
     Source: LAN3 net
     Destination: 192.168.20.10 (Tailscale machine)
     Destination Port: 1055
     Description: Allow access to Tailscale SOCKS5 proxy
   ```

2. **Route Through Proxy Gateway:**
   ```
   Rule 2:
     Action: Pass
     Protocol: any
     Source: LAN3 net (or specific IPs)
     Destination: any
     Gateway: PROXYGW_TAILSCALE_PROXY
     Description: Route LAN3 through Tailscale
   ```

**Common Issues and Solutions:**

| Issue | Cause | Solution |
|-------|-------|----------|
| "Packet not handled" in Tailscale logs | UDP relay not working | Verify proxy type is SOCKS5, check plugin version ≥1.0.1 |
| DNS fails, but can ping IPs | DNS not going through tunnel | Point clients at an external resolver routed via the proxy gateway (see "DNS Leaks") |
| Connection shows UP but no traffic | Firewall blocking proxy access | Add rule allowing access to Tailscale IP:port |
| Local network works, internet doesn't | Tailscale routing not configured | Check Tailscale exit node configuration |
| High latency | Tailscale relay path inefficient | Use `tailscale netcheck` to optimize route |

**Verifying the Fix:**

After configuration, verify everything works:

```bash
# 1. Check connection status
# Services → Proxy Gateway → Diagnostics
# Connection should show: UP

# 2. From client device, test DNS:
nslookup google.com
# Should resolve

# 3. Test internet connectivity:
curl http://ifconfig.me
# Should show Tailscale exit node's IP

# 4. Check for errors in Tailscale logs:
# Tailscale machine:
sudo tailscale status
sudo journalctl -u tailscale -f
# Should not see "packet not handled" errors
```

**Additional Resources:**

- Tailscale SOCKS5 proxy documentation: https://tailscale.com/kb/1112/userspace-networking
- Tailscale subnet routing: https://tailscale.com/kb/1019/subnets
- tun2socks UDP relay: https://github.com/xjasonlyu/tun2socks

---

## API Reference

### Connection Management

```
GET  /api/proxygateway/connection/searchItem
GET  /api/proxygateway/connection/getItem/{uuid}
POST /api/proxygateway/connection/addItem
POST /api/proxygateway/connection/setItem/{uuid}
POST /api/proxygateway/connection/delItem/{uuid}
POST /api/proxygateway/connection/toggleItem/{uuid}
```

### Service Control

```
POST /api/proxygateway/service/reconfigure
POST /api/proxygateway/service/start
POST /api/proxygateway/service/stop
POST /api/proxygateway/service/restart
GET  /api/proxygateway/service/status
```

### Diagnostics

```
GET  /api/proxygateway/diagnostics/getStatus
POST /api/proxygateway/diagnostics/testConnection
GET  /api/proxygateway/diagnostics/getLogs
POST /api/proxygateway/diagnostics/clearLogs
GET  /api/proxygateway/diagnostics/getHealthHistory?name=<connection_name>
GET  /api/proxygateway/diagnostics/getSpeedTestHistory?name=<connection_name>
POST /api/proxygateway/diagnostics/runSpeedTest
```
