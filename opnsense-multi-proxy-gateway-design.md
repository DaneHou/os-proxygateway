# OPNsense Multi-Proxy Gateway Plugin — Design Document

**Author:** Dane  
**Date:** 2026-02-23  
**Status:** Draft / Planning  
**Codename:** `os-proxygateway`

---

## 1. Executive Summary

Design a plugin for OPNsense that allows users to configure multiple upstream proxy connections (SOCKS5 and/or HTTP/HTTPS proxies), expose each as a distinct local gateway interface, and route specific devices or subnets through any of those gateways using standard OPNsense firewall rules. This turns OPNsense into a transparent multi-proxy router — no client-side configuration needed.

---

## 2. Problem Statement

Many network scenarios require routing different devices or VLANs through different upstream proxies:

- Privacy-separated browsing for different household members or IoT segments
- Geo-unlocking: route a streaming device through a regional proxy while keeping work traffic direct
- Security segmentation: route untrusted devices through an inspection proxy
- Redundancy: failover between multiple proxy uplinks

Currently, OPNsense supports VPN gateways (OpenVPN, WireGuard) natively, but has **no built-in mechanism** to use a remote SOCKS5 or HTTP proxy as a transparent gateway for routed traffic. Users are forced into per-device proxy configuration, which is fragile and doesn't cover all traffic (DNS, non-HTTP protocols, etc.).

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      OPNsense Firewall                      │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ proxyGW1 │  │ proxyGW2 │  │ proxyGW3 │   ← tun ifaces  │
│  │ tun4001  │  │ tun4002  │  │ tun4003  │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       │              │              │                        │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐                  │
│  │redsocks  │  │redsocks  │  │redsocks  │   ← userland     │
│  │instance 1│  │instance 2│  │instance 3│     proxy clients │
│  └────┬─────┘  └────┴─────┘  └────┬─────┘                  │
│       │              │              │                        │
│       ▼              ▼              ▼                        │
│   SOCKS5 ────►  HTTP ─────►  SOCKS5 ────►  Remote servers  │
│   server A      proxy B      server C                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │               OPNsense Routing Table                 │    │
│  │  192.168.10.0/24  → proxyGW1 (tun4001)              │    │
│  │  192.168.20.50    → proxyGW2 (tun4002)              │    │
│  │  VLAN 30          → proxyGW3 (tun4003)              │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Core Concept

Each configured proxy connection produces:

1. **A `tun` interface** — a local point-to-point tunnel device
2. **A `redsocks` (or `tun2socks`) instance** — captures routed packets and forwards them through the upstream proxy
3. **An OPNsense gateway** — registered in the gateway table so it can be used in firewall rules and policy routing

---

## 4. Key Components

### 4.1 Packet Redirection Engine

Two viable approaches for transparent proxying:

| Approach | Mechanism | Pros | Cons |
|---|---|---|---|
| **`tun2socks`** (recommended) | Creates a real tun device; all routed IP traffic enters the tun and exits via SOCKS5/HTTP proxy | True gateway; works with all protocols; clean routing table integration | Requires `tun2socks` binary (Go, single static binary) |
| **`redsocks` + pf** | Uses pf `rdr` rules to redirect routed traffic to a local redsocks listener that forwards to upstream proxy | Mature, well-tested on FreeBSD | TCP-only (UDP needs separate handling); pf rules can get complex with many instances |

**Recommendation:** Use **`tun2socks` v2** (Go-based, `xjasonlyu/tun2socks`) as the primary engine. It provides a real tun device, handles TCP+UDP, supports both SOCKS5 and HTTP proxies, and produces a clean gateway that integrates naturally with OPNsense.

Fallback: `redsocks` for environments where tun2socks isn't viable.

### 4.2 Proxy Protocol Support

| Protocol | Supported By | Notes |
|---|---|---|
| SOCKS5 | tun2socks, redsocks | Full TCP+UDP support; authentication supported |
| SOCKS5 + TLS | tun2socks | Encrypted tunnel to SOCKS server |
| HTTP CONNECT | tun2socks, redsocks | TCP only; most HTTP proxies support CONNECT |
| HTTPS (CONNECT over TLS) | tun2socks | Encrypted tunnel to HTTP proxy |

### 4.3 DNS Handling

Each proxy gateway needs independent DNS resolution to prevent leaks:

- **Option A (default):** Route DNS through the proxy tunnel itself (tun2socks handles this natively for UDP)
- **Option B:** Configure a specific remote DNS server per gateway, resolved through the tunnel
- **Option C:** Local DNS-over-HTTPS/TLS forwarder per gateway (e.g., `dnscrypt-proxy` instance)

### 4.4 Health Checking

Each proxy connection gets a health monitor:

- Periodic connectivity test through the tunnel (e.g., HTTP GET to a known endpoint)
- Gateway marked DOWN in OPNsense if probe fails → automatic failover if gateway groups are configured
- Configurable interval, timeout, and probe target

---

## 5. OPNsense Plugin Structure

Following OPNsense plugin conventions (`os-proxygateway`):

```
os-proxygateway/
├── Makefile                          # FreeBSD port Makefile
├── pkg-descr                         # Package description
├── src/
│   ├── etc/
│   │   └── inc/
│   │       └── plugins.inc.d/
│   │           └── proxygateway.inc  # Registration hook
│   ├── opnsense/
│   │   ├── mvc/
│   │   │   └── app/
│   │   │       ├── controllers/
│   │   │       │   └── OPNsense/ProxyGateway/
│   │   │       │       ├── Api/
│   │   │       │       │   ├── ConnectionController.php
│   │   │       │       │   ├── ServiceController.php
│   │   │       │       │   └── DiagnosticsController.php
│   │   │       │       └── IndexController.php
│   │   │       ├── models/
│   │   │       │   └── OPNsense/ProxyGateway/
│   │   │       │       ├── ProxyGateway.php
│   │   │       │       └── ProxyGateway.xml        # Data model
│   │   │       └── views/
│   │   │           └── OPNsense/ProxyGateway/
│   │   │               └── index.volt               # UI template
│   │   ├── scripts/
│   │   │   └── OPNsense/ProxyGateway/
│   │   │       ├── setup.sh                         # Create tun + start tun2socks
│   │   │       ├── teardown.sh                      # Stop instance + destroy tun
│   │   │       ├── healthcheck.sh                   # Probe connectivity
│   │   │       └── gateway_register.py              # Register/deregister gateways
│   │   └── service/
│   │       └── conf/actions.d/
│   │           └── actions_proxygateway.conf         # configd actions
│   └── usr/
│       └── local/
│           ├── bin/
│           │   └── tun2socks                         # Static binary (amd64/aarch64)
│           └── etc/
│               └── rc.d/
│                   └── proxygateway                  # rc.d service script
├── pkg/
│   └── +POST_INSTALL                                # Post-install setup
└── README.md
```

---

## 6. Data Model (`ProxyGateway.xml`)

```xml
<model>
  <mount>//OPNsense/ProxyGateway</mount>
  <description>Multi-Proxy Gateway Configuration</description>

  <items>
    <!-- Global settings -->
    <general>
      <enabled type="BooleanField">
        <default>0</default>
        <Required>Y</Required>
      </enabled>
      <logLevel type="OptionField">
        <default>warning</default>
        <OptionValues>
          <debug>Debug</debug>
          <info>Info</info>
          <warning>Warning</warning>
          <error>Error</error>
        </OptionValues>
      </logLevel>
    </general>

    <!-- Proxy connections (multiple) -->
    <connections>
      <connection type="ArrayField">
        <enabled type="BooleanField"><default>1</default></enabled>

        <name type="TextField">
          <Required>Y</Required>
          <Mask>/^[a-zA-Z0-9_-]{1,16}$/</Mask>
          <!-- Used as interface suffix: proxyGW_<name> -->
        </name>

        <description type="TextField"/>

        <!-- Upstream proxy settings -->
        <proxyType type="OptionField">
          <default>socks5</default>
          <OptionValues>
            <socks5>SOCKS5</socks5>
            <socks5tls>SOCKS5 + TLS</socks5tls>
            <http>HTTP CONNECT</http>
            <https>HTTPS CONNECT</https>
          </OptionValues>
        </proxyType>

        <proxyServer type="NetworkField">
          <Required>Y</Required>
        </proxyServer>

        <proxyPort type="PortField">
          <Required>Y</Required>
          <default>1080</default>
        </proxyPort>

        <authEnabled type="BooleanField"><default>0</default></authEnabled>
        <authUser type="TextField"/>
        <authPass type="TextField"/>

        <!-- Local tunnel settings -->
        <tunAddress type="NetworkField">
          <default>172.31.x.1</default>
          <!-- Auto-assigned from 172.31.0.0/16 pool -->
        </tunAddress>

        <tunMTU type="IntegerField">
          <default>1500</default>
          <MinimumValue>1280</MinimumValue>
          <MaximumValue>9000</MaximumValue>
        </tunMTU>

        <!-- DNS settings -->
        <dnsMode type="OptionField">
          <default>tunnel</default>
          <OptionValues>
            <tunnel>Route through tunnel</tunnel>
            <custom>Custom DNS server</custom>
          </OptionValues>
        </dnsMode>

        <dnsServer type="NetworkField"/>

        <!-- Health check -->
        <healthCheckEnabled type="BooleanField"><default>1</default></healthCheckEnabled>
        <healthCheckInterval type="IntegerField"><default>30</default></healthCheckInterval>
        <healthCheckTarget type="UrlField">
          <default>http://cp.cloudflare.com</default>
        </healthCheckTarget>

        <!-- Gateway settings -->
        <gatewayPriority type="IntegerField">
          <default>255</default>
          <MinimumValue>1</MinimumValue>
          <MaximumValue>255</MaximumValue>
        </gatewayPriority>
      </connection>
    </connections>
  </items>
</model>
```

---

## 7. Instance Lifecycle

### 7.1 Start a proxy gateway instance

```bash
#!/bin/sh
# setup.sh — called by configd for each connection

NAME=$1           # e.g., "uswest"
PROXY_TYPE=$2     # socks5 | http | ...
PROXY_ADDR=$3     # 1.2.3.4:1080
TUN_ADDR=$4       # 172.31.1.1
TUN_PEER=$5       # 172.31.1.2

IFACE="tun_pgw_${NAME}"

# 1. Create tun device
ifconfig ${IFACE} create
ifconfig ${IFACE} inet ${TUN_ADDR} ${TUN_PEER} mtu 1500 up

# 2. Start tun2socks
/usr/local/bin/tun2socks \
    -device "${IFACE}" \
    -proxy "${PROXY_TYPE}://${PROXY_ADDR}" \
    -loglevel warning \
    &

PID=$!
echo ${PID} > /var/run/proxygateway_${NAME}.pid

# 3. Add route for tunnel peer
route add ${TUN_PEER}/32 -interface ${IFACE}

# 4. Register as OPNsense gateway
# (via gateway_register.py — plugs into dpinger / routing table)
python3 /usr/local/opnsense/scripts/OPNsense/ProxyGateway/gateway_register.py \
    --name "PROXYGW_${NAME}" \
    --interface "${IFACE}" \
    --gateway "${TUN_PEER}" \
    --monitor "${HEALTH_TARGET}" \
    --priority "${GW_PRIORITY}"
```

### 7.2 Stop a proxy gateway instance

```bash
#!/bin/sh
# teardown.sh

NAME=$1
IFACE="tun_pgw_${NAME}"

# 1. Deregister gateway
python3 .../gateway_register.py --remove --name "PROXYGW_${NAME}"

# 2. Kill tun2socks
kill $(cat /var/run/proxygateway_${NAME}.pid)

# 3. Destroy interface
ifconfig ${IFACE} destroy
```

---

## 8. Routing & Policy-Based Forwarding

Once gateways are registered, standard OPNsense mechanisms apply:

### 8.1 Per-device routing (Firewall → Rules)

```
Source: 192.168.1.100 (smart TV)
Destination: any
Gateway: PROXYGW_uswest        ← select from gateway dropdown
```

### 8.2 Per-subnet routing

```
Source: 192.168.30.0/24 (VLAN 30 — guest network)
Destination: any
Gateway: PROXYGW_euproxy
```

### 8.3 Gateway groups (failover / load-balance)

```
Gateway Group: PROXY_FAILOVER
  Tier 1: PROXYGW_primary
  Tier 2: PROXYGW_backup
  Trigger: Packet Loss + High Latency
```

### 8.4 Source NAT

Each proxy tunnel interface needs outbound NAT to function. Auto-created rule:

```
Interface: tun_pgw_<name>
Source: LAN subnets
Translation: Interface Address
```

> **Note:** Because tun2socks handles the actual proxy negotiation in userland, the NAT here is local-only. The remote proxy server sees traffic originating from its own client connection, not from the OPNsense WAN IP.

---

## 9. UI Design

### 9.1 Dashboard Widget

```
╔══════════════════════════════════════════════╗
║  Proxy Gateways                              ║
╠══════════════════════════════════════════════╣
║  ● US-West (SOCKS5)      ▲ 12ms   ONLINE   ║
║  ● EU-Proxy (HTTP)       ▲ 45ms   ONLINE   ║
║  ○ JP-Backup (SOCKS5)    —        OFFLINE   ║
╚══════════════════════════════════════════════╝
```

### 9.2 Connection Configuration Page

Under **Services → Proxy Gateway → Connections**:

- Table listing all proxy connections with status indicators
- Add/Edit dialog with tabbed sections:
  - **General:** Name, description, enabled
  - **Proxy Server:** Type, address, port, credentials
  - **Tunnel:** Local address (auto or manual), MTU
  - **DNS:** Mode selection, custom server
  - **Health Check:** Enable, interval, target URL
  - **Gateway:** Priority, gateway group membership

### 9.3 Diagnostics Page

Under **Services → Proxy Gateway → Diagnostics**:

- Per-connection: latency graph, uptime %, bytes transferred
- Log viewer (filtered by instance)
- "Test Connection" button per proxy

---

## 10. Security Considerations

### 10.1 Credential Storage

Proxy authentication credentials are stored in OPNsense's config.xml (encrypted at rest if full-disk encryption is enabled). Passwords are base64-encoded in the model and injected into tun2socks at runtime via environment variables — never written to disk in plaintext config files.

### 10.2 Traffic Isolation

Each tunnel interface is a separate device. Firewall rules prevent cross-tunnel traffic by default. A compromised proxy cannot reach other tunnel segments unless explicitly permitted.

### 10.3 DNS Leak Prevention

When a device is routed through a proxy gateway:

- pf rules block DNS (port 53) traffic that doesn't go through the assigned tunnel
- Auto-generated "kill switch" rules ensure that if the tunnel goes down, traffic is dropped rather than leaked to WAN

### 10.4 Kill Switch (Fail-Close)

Optional per-connection setting: if the proxy tunnel is DOWN, **drop** all traffic from assigned sources rather than falling back to WAN. Implemented via gateway-dependent firewall rules.

---

## 11. Implementation Phases

### Phase 1 — Core Engine (MVP)

- [ ] Package `tun2socks` static binary for FreeBSD (amd64)
- [ ] `rc.d` service script for managing instances
- [ ] Shell scripts: `setup.sh`, `teardown.sh`, `healthcheck.sh`
- [ ] Single proxy connection → single gateway (CLI only)
- [ ] Basic pf NAT rules
- [ ] Manual gateway registration via `pluginctl`

**Deliverable:** Working transparent SOCKS5/HTTP proxy gateway via CLI.

### Phase 2 — OPNsense Integration

- [ ] MVC model (`ProxyGateway.xml`)
- [ ] API controllers (CRUD for connections, start/stop service)
- [ ] `configd` action definitions
- [ ] Auto-gateway registration (integrated with dpinger)
- [ ] Auto-NAT rule generation
- [ ] DNS leak prevention rules

**Deliverable:** Manage proxy gateways from OPNsense API.

### Phase 3 — UI & Polish

- [ ] Volt template for connection management
- [ ] Dashboard widget with live status
- [ ] Diagnostics page (logs, latency, throughput)
- [ ] "Test Connection" functionality
- [ ] Kill-switch toggle per connection
- [ ] Gateway group support in UI

**Deliverable:** Full GUI experience matching native OPNsense VPN plugins.

### Phase 4 — Advanced Features

- [ ] Proxy chaining (proxy → proxy → internet)
- [ ] Load balancing across multiple proxies for the same gateway
- [ ] PAC (Proxy Auto-Config) file generator for hybrid setups
- [ ] ARM64 binary for OPNsense on ARM devices
- [ ] Bandwidth monitoring per tunnel
- [ ] Integration with OPNsense's Unbound for per-tunnel DNS forwarding

---

## 12. Dependencies

| Dependency | Version | Purpose | License |
|---|---|---|---|
| `tun2socks` | v2.x (Go) | Core tunneling engine | GPL-3.0 |
| `dpinger` | (bundled) | Gateway health monitoring | BSD |
| OPNsense | 24.x+ | Base platform | BSD-2 |
| FreeBSD | 14.x+ | OS (tun device support) | BSD |

### Build Requirements

- Go 1.21+ (cross-compile tun2socks for FreeBSD)
- OPNsense plugin build tools (`opnsense/plugins` repo structure)

---

## 13. Comparable / Prior Art

| Solution | Approach | Limitation |
|---|---|---|
| OpenVPN client on OPNsense | VPN tunnel as gateway | Requires VPN server, not proxy |
| WireGuard on OPNsense | VPN tunnel as gateway | Requires WireGuard server |
| pfSense + redsocks | pf redirect to redsocks | TCP only, no tun interface, manual setup |
| Proxychains (per-app) | LD_PRELOAD hooking | Per-application, not network-wide |
| Clash / sing-box | Tun-based proxy client | Linux-focused, no OPNsense integration |

This plugin fills the gap: **proxy-as-gateway with native OPNsense integration**.

---

## 14. Open Questions

1. **tun2socks FreeBSD support:** The Go-based tun2socks v2 supports FreeBSD, but needs validation on OPNsense's specific kernel configuration. Alternative: use `badvpn-tun2socks` (C-based, older but proven on BSD).

2. **UDP over HTTP proxy:** HTTP CONNECT proxies only support TCP. For full UDP transparency through HTTP proxies, we'd need a supplementary UDP relay or accept TCP-only forwarding.

3. **Gateway registration method:** OPNsense uses `dpinger` for gateway monitoring. Need to verify if dynamically adding gateways at runtime (without a full config reload) is supported, or if we need to trigger `configctl interface routes reconfigure`.

4. **Performance:** tun2socks adds userland overhead. Benchmark needed to determine max throughput per instance on typical OPNsense hardware (e.g., Protectli VP2420, Qotom mini-PC).

5. **Plugin naming:** `os-proxygateway` vs `os-tun2proxy` vs `os-proxygw` — should align with OPNsense naming conventions.

---

## 15. Quick-Start (Phase 1 Target)

After Phase 1 is complete, a user would:

```bash
# Install plugin
pkg install os-proxygateway

# Add a proxy connection
configctl proxygateway connection add \
    --name uswest \
    --type socks5 \
    --server 203.0.113.50 \
    --port 1080

# Start the gateway
configctl proxygateway start uswest

# Verify gateway exists
netstat -rn | grep tun_pgw_uswest

# Route a device through it (via OPNsense GUI)
# Firewall → Rules → LAN → Add:
#   Source: 192.168.1.100
#   Gateway: PROXYGW_uswest
```

---

*This design leverages OPNsense's existing gateway/routing infrastructure to treat proxy connections as first-class network gateways — the same way VPN tunnels work today, but for SOCKS5 and HTTP proxies.*
