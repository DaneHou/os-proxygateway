# Comprehensive User Guide: OS Proxy Gateway

**Version:** 1.0.0-rc1
**Last Updated:** 2026-02-23
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
9. [Advanced Topics](#advanced-topics)
10. [API Reference](#api-reference)
11. [Security Considerations](#security-considerations)

---

## Introduction

### What is OS Proxy Gateway?

OS Proxy Gateway is an OPNsense plugin that converts remote SOCKS5 and HTTP/HTTPS proxy servers into standard OPNsense gateway interfaces. This enables you to route network traffic through proxies using native firewall rules, without requiring any client-side configuration.

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
- Real-time connection status
- Latency tracking
- Detailed logging
- Health check monitoring

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
6. **Proxy Protocol:** tun2socks encapsulates in SOCKS5/HTTP
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
- One or more proxy servers (SOCKS5 or HTTP)
- Internet connectivity on WAN

✅ **Access Requirements:**
- Root/administrative access to OPNsense
- SSH access (for installation from source)
- Web UI access

### Installation Methods

#### Method 1: From OPNsense Package Repository (Recommended)

⚠️ **Note:** Not yet available in official repository. This will be the method after acceptance.

```bash
# Update package repository
pkg update

# Install plugin
pkg install os-proxygateway

# Verify installation
pkg info os-proxygateway
```

#### Method 2: From Source (Current Method)

```bash
# SSH to your OPNsense box as root
ssh root@opnsense.local

# Clone the repository
cd /usr/local
git clone https://github.com/DaneBA/os-proxygateway.git

# Navigate to repository
cd os-proxygateway

# Install the plugin
make install

# Restart web interface to load new menu items
configctl webgui restart
```

### Post-Installation Verification

```bash
# Check if service is registered
service opnsense-proxygateway status

# Check if menu items appear
# Navigate to: Services → Proxy Gateway (in web UI)

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
- Access to a SOCKS5 or HTTP proxy server

#### Step 1: Create Proxy Connection

1. Navigate to **Services → Proxy Gateway → Connections**

2. Click **Add Connection** (+ button)

3. Fill in the **General** tab:
   ```
   Name:        myproxy
   Description: My first proxy connection
   Enabled:     ✓ (checked)
   ```

4. Fill in the **Proxy Server** tab:
   ```
   Type:        SOCKS5
   Server:      proxy.example.com
   Port:        1080

   (If authentication required:)
   Auth Enabled: ✓
   Username:     your_username
   Password:     your_password
   ```

5. Leave other tabs at defaults

6. Click **Save**

7. Click **Apply Changes** button (top right)

#### Step 2: Create Firewall Rule

1. Navigate to **Firewall → Rules → LAN**

2. Click **Add Rule** (+ button)

3. Configure the rule:
   ```
   Action:         Pass
   Interface:      LAN
   Protocol:       any
   Source:         192.168.1.100 (your test device IP)
   Destination:    any
   Gateway:        PROXYGW_MYPROXY
   Description:    Route test device through proxy
   ```

4. Click **Save**

5. Click **Apply Changes**

#### Step 3: Test

1. On device 192.168.1.100, visit: https://ifconfig.me
   - Should show the proxy server's IP address

2. Check connection status:
   - Navigate to **Services → Proxy Gateway → Diagnostics**
   - Verify "myproxy" shows status: **UP**

✅ **Success!** Traffic from your device now routes through the proxy.

---

## Configuration Guide

### Connection Settings

#### General Tab

**Name** (Required)
- 1-16 characters
- Alphanumeric, underscore, hyphen only
- Example: `us_proxy`, `corporate-proxy`, `backup_1`
- Used in interface name: `pgw_<name>`

**Description** (Optional)
- Free-form text
- Helps identify connection purpose
- Example: "US West Coast Proxy for Streaming"

**Enabled** (Checkbox)
- ✓ Checked: Connection active
- ✗ Unchecked: Connection disabled but configuration saved

#### Proxy Server Tab

**Type** (Dropdown - Required)
- `SOCKS5`: Standard SOCKS5 proxy (supports TCP + UDP)
- `SOCKS5 + TLS`: SOCKS5 with TLS encryption
- `HTTP CONNECT`: HTTP proxy using CONNECT method (TCP only)
- `HTTPS CONNECT`: HTTP proxy with TLS (TCP only)

**Server** (Required)
- Hostname or IP address
- Examples:
  - `proxy.example.com`
  - `192.168.100.50`
  - `[2001:db8::1]` (IPv6 - for future support)

**Port** (Required)
- 1-65535
- Common ports:
  - SOCKS5: 1080
  - HTTP: 8080, 3128
  - SSH tunnel: 1080, 8080 (your choice)

**Auth Enabled** (Checkbox)
- ✓ Required for proxies needing authentication
- ✗ Anonymous/open proxies

**Username** (Required if Auth Enabled)
- 1-64 characters
- Allowed: alphanumeric, `@`, `.`, `_`, `-`
- Example: `user@company.com`, `proxy_user`

**Password** (Required if Auth Enabled)
- 1-128 characters
- Printable ASCII characters
- ⚠️ **Security Note:** Currently stored in plaintext in config.xml
- Recommendation: Use strong, unique passwords

#### Tunnel Settings Tab

**Tunnel Address** (Optional)
- Auto-assigned from 172.31.0.0/16 if left empty
- Manual example: `172.31.10.1`
- Format: IPv4 address only
- Note: Address is for local tunnel endpoint

**MTU** (Optional)
- Default: 1500
- Range: 1280-9000
- Lower if proxy is over VPN or has small MTU
- Recommended: 1500 (standard), 1420 (over VPN)

#### DNS Settings Tab

**DNS Mode** (Dropdown)
- `Route through tunnel`: DNS queries go through proxy (recommended)
- `Custom DNS server`: Use specific DNS server

**DNS Server** (Required if Custom mode)
- IPv4 address of DNS server
- Example: `8.8.8.8`, `1.1.1.1`
- Used for all DNS queries from routed clients

#### Health Check Tab

**Enabled** (Checkbox)
- ✓ Periodic connectivity checks
- ✗ No health monitoring (gateway always shown as UP)

**Interval** (Seconds)
- Range: 5-3600
- Default: 30
- Recommended: 30 for production, 60 for low-priority

**Target** (Optional)
- URL to probe for connectivity
- Default: `http://1.1.1.1/` (Cloudflare)
- Custom example: `http://your-server.com/health`
- ⚠️ **Privacy Note:** Default target leaks usage patterns to Cloudflare

#### Gateway Settings Tab

**Priority** (1-255)
- Default: 255
- Lower number = higher priority
- Used when multiple gateways available
- Example: Primary=50, Backup=100

**Kill Switch** (Checkbox)
- ✓ Drop traffic if proxy fails (prevents leaks)
- ✗ Fall back to default WAN if proxy fails

### Global Settings

Navigate to **Services → Proxy Gateway → Settings**

**Plugin Enabled** (Checkbox)
- Master switch for entire plugin
- Unchecking stops all connections

**Log Level** (Dropdown)
- `Debug`: Very verbose (development only)
- `Info`: Normal verbosity
- `Warning`: Only warnings and errors
- `Error`: Only errors
- Recommended: `Warning` for production

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

### Example 4: Gateway Group Failover

**Scenario:** Primary proxy with automatic failover to backup.

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
Trigger:     Packet Loss + High Latency
```

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
              │   Health Check      │
              │   Primary: UP?      │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Yes: Use Primary   │
              │  No: Use Backup     │
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
Trigger:     Packet Loss + High Latency
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
   - Name: `vpn`, Type: SOCKS5, Server: alice-vpn-proxy.com:1080
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
   Type: SOCKS5 + TLS
   Server: us-proxy.streamingservice.com
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
   - Set Smart TV to use DNS: 8.8.8.8
   - Or use DNS mode: custom with US DNS server

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
- Kill switch (no direct Internet if both proxies fail)

**Network Design:**
```
Office LAN: 10.0.10.0/24
├─ Primary Proxy: corporate-proxy1.company.com
├─ Backup Proxy: corporate-proxy2.company.com
└─ Kill Switch: Drop if both fail
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
   Kill Switch: enabled

   Connection 2:
   Name: corp_backup
   Type: HTTP
   Server: corporate-proxy2.company.com
   Port: 8080
   Auth: corporate credentials
   Kill Switch: enabled
   ```

2. **Create Gateway Group:**
   ```
   Name: CorporateProxies
   Tier 1: PROXYGW_CORP_PRIMARY
   Tier 2: PROXYGW_CORP_BACKUP
   Trigger: Packet Loss + High Latency
   ```

3. **Create Firewall Rule:**
   ```
   Interface: LAN
   Source: LAN net (10.0.10.0/24)
   Destination: any
   Gateway: CorporateProxies (group)
   ```

**Behavior:**
```
Normal: Primary UP → All traffic via Primary
Failover: Primary DOWN → All traffic via Backup
Emergency: Both DOWN + Kill Switch → Traffic DROPPED
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
| NAT conflict | Outbound NAT override | Check Firewall → NAT → Outbound |
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
Increase health check interval: 30s → 60s
Disable health checks (if stable proxy)
Use SOCKS5 instead of HTTP (lower overhead)
Use TLS proxies only when necessary
```

### DNS Leaks

**Symptom:** DNS queries go direct instead of through proxy.

**Diagnostic Steps:**

1. **Test for DNS Leak:**
   ```bash
   # From client device:
   # Visit: https://dnsleaktest.com
   # Should show proxy provider's DNS or configured custom DNS
   # Should NOT show ISP DNS
   ```

2. **Check DNS Mode:**
   - Services → Proxy Gateway → Connections → [Connection] → DNS Settings
   - Verify: "Route through tunnel" is selected

3. **Check Firewall DNS Rules:**
   ```bash
   # Firewall → Rules → [Interface]
   # Should have DNS (port 53) routed through proxy
   # Or DNS traffic blocked to force through tunnel
   ```

4. **Check Client DNS:**
   ```bash
   # On client device:
   # Windows: ipconfig /all
   # Linux: cat /etc/resolv.conf
   # macOS: scutil --dns
   # DNS server should be gateway (192.168.1.1) or tunnel DNS
   ```

**Fix DNS Leaks:**

**Option 1: Route DNS Through Tunnel**
```
Connection → DNS Settings → Mode: Route through tunnel
This sends all DNS via proxy
```

**Option 2: Custom DNS Server**
```
Connection → DNS Settings → Mode: Custom
DNS Server: 8.8.8.8 (or proxy provider's DNS)
```

**Option 3: Force DNS Through Tunnel (Firewall Rule)**
```
Create rule ABOVE proxy rule:
  Action: Reject
  Protocol: TCP/UDP
  Destination Port: 53 (DNS)
  Description: Block direct DNS (force through proxy)
```

### Kill Switch Not Working

**Symptom:** Traffic falls back to WAN when proxy fails.

**Diagnostic Steps:**

1. **Verify Kill Switch Enabled:**
   ```
   Services → Proxy Gateway → Connections → [Connection]
   → Gateway Settings → Kill Switch: ✓
   ```

2. **Check Gateway Status:**
   ```
   System → Gateways → Status
   PROXYGW_<name> should show "Offline" when proxy down
   ```

3. **Test Failover:**
   - Stop proxy server
   - Try accessing internet from client
   - Should FAIL (no connection)

4. **Check Firewall State:**
   ```bash
   # Diagnostics → States → States
   # Look for states using PROXYGW_X gateway
   # When proxy down, states should be killed
   ```

**Common Issues:**

| Issue | Cause | Solution |
|-------|-------|----------|
| Traffic still flows | Multiple routes | Remove default allow rule |
| Gateway stays UP | Health check disabled | Enable health checks |
| Failover to WAN | Gateway group | Remove from gateway group or adjust tiers |

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
   Increase interval: 30s → 60s (less frequent checks)
   Change target: Try different URL
   Disable temporarily: Test if stability improves
   ```

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
Adjust health check interval (less aggressive)
Switch to more stable proxy provider
Use gateway group with backup proxy
Check proxy server capacity/rate limits
Verify proxy server isn't blocking health check requests
```

---

(Continuing in next message due to length...)
