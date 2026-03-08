# Why Proxy Gateway?

## The Problem

You have a SOCKS5 or HTTP proxy server. You want all traffic from a device,
VLAN, or subnet to route through it — transparently, with no per-device
configuration.

On OPNsense, you cannot do this. The firewall operates at Layer 3 (IP routing)
and Layer 4 (TCP/UDP rules). Proxy protocols operate at Layer 5 (session layer).
There is no native bridge between these layers. OPNsense has no built-in concept
of "use this SOCKS5 server as a gateway."

People have been asking for this since at least 2015. The answer has always been
the same:

> "SOCKS proxy is Layer 5 (application), you need a Layer 3 tunnel that uses
> SOCKS protocol to route all traffic. OPNsense does not have such tunnel.
> There are some SOCKS tunnel programs [...] that you might be able to install
> and run, but you won't be able to use OPNsense to manage. Unless you are
> willing to do everything manually, I'd suggest to forget about it."
>
> — [zan, OPNsense Forum](https://forum.opnsense.org/index.php?topic=34058.0), May 2023

This plugin exists so you don't have to forget about it.

## What Proxy Gateway Does

Proxy Gateway converts SOCKS5 and HTTP/HTTPS proxy servers into standard
OPNsense gateway interfaces. Once installed, a proxy connection appears as a
gateway just like your WAN or a VPN tunnel — you can route traffic through it
using regular firewall rules.

```
LAN Device ──> OPNsense Firewall Rule ──> pgw_myproxy (TUN) ──> tun2socks ──> Proxy Server
```

The plugin handles everything automatically:
- Creates a TUN interface (`pgw_<name>`) for each proxy connection
- Runs [tun2socks](https://github.com/xjasonlyu/tun2socks) to bridge L3
  traffic to the L5 proxy protocol
- Registers a gateway (`PROXYGW_<NAME>`) in OPNsense's routing system
- Syncs interface IPs and gateway entries into `config.xml`
- Generates anti-routing-loop firewall rules automatically
- Supports SOCKS5, SOCKS5+TLS, HTTP CONNECT, and HTTPS CONNECT
- Handles both TCP and UDP traffic (SOCKS5)

After setup, routing traffic through a proxy is identical to routing through a
VPN: create a firewall rule, select the gateway, done.

## A Decade of Unmet Demand

This is not a niche request. Users have been asking for proxy-as-gateway on
OPNsense, pfSense, OpenWrt, and DD-WRT for over 10 years. Here is a sample of
the community threads — most of which were never resolved.

### "If I have a SOCKS proxy, is there any way to make this proxy appear as a gateway?"

> "If I have access to a SOCKS proxy, is there any way to make this proxy
> appear as an interface or gateway on my opnsense router, so that I can create
> rules to direct traffic to it?"
>
> — [DavidGA, OPNsense Forum](https://forum.opnsense.org/index.php?topic=34058.0), May 2023

The answer was "forget about it." DavidGA replied "Thanks for your help" and
the thread was closed. Two replies, no solution.

### "I can forward traffic to Squid, but when I forward to a SOCKS5 proxy, nothing happens"

> "Clients like redsocks, ss-redir (shadowsocks), clash, etc. can open a socks5
> transparent proxy. On LEDE and Linux platforms, traffic can be redirected to
> this socks5 transparent proxy port through iptables. [...] However, the port
> forwarding rule set on OPNsense does not take effect. I can forward traffic to
> another HTTP port, or I can forward traffic to Squid's HTTP transparent proxy,
> but when I forward to a socks5 transparent proxy, nothing happens."
>
> — [or2me, OPNsense Forum](https://forum.opnsense.org/index.php?topic=16742.0), April 2020

This thread received **zero replies** over 5+ years. Complete silence. The user
was technically capable — they mentioned redsocks, ss-redir, clash, and iptables
— but hit a wall specific to OPNsense's architecture.

### "I specifically chose OPNsense over pfSense for the Shadowsocks plugin"

> "I would like to redirect all outgoing internet traffic through the
> shadowsocks server. [...] I got ~70 Mbps using OpenVPN while ~250 Mbps using
> shadowsocks client alone. Would it be possible to redirect all traffic to use
> shadowsocks WITHOUT using OpenVPN? Maybe NAT Rules?"
>
> — [heartofrainbow, OPNsense Forum](https://forum.opnsense.org/index.php?topic=10908.0), January 2019

Ten months later, another user arrived:

> "I'm looking for this same thing. Could anyone shed some light on this? I
> specifically chose OPNsense over pfSense for the shadowsocks plugin but can't
> seem to get traffic routed correctly."
>
> — revnelson, November 2019

Even the OPNsense Shadowsocks plugin maintainer (mimugmail, 6,800+ posts)
replied asking: "Is there an official guide for such a setup?" — implying there
wasn't one.

**3.5 years later**, yet another user found the thread:

> "Has anyone been able to solve this problem?"
>
> — ShatalMotal2, August 2022

Nobody had. The thread was never resolved.

### "I would like to route all traffic without the device needing to install anything"

> "I would like to route all outgoing internet traffic (TCP+UDP) from the
> devices connected to the Wi-Fi access point through the shadowsocks server.
> This should happen without the device needing to install anything or the
> device even knowing about this."
>
> — [mattdeox, OPNsense Forum](https://forum.opnsense.org/index.php?topic=35241.0), August 2023

This user had recently switched to OPNsense ("it feels amazing") and assumed
transparent proxy routing would be a built-in capability. Nine days later, they
gave up and fell back to running iptables on a separate Linux machine. Nobody
from the community could help.

### "I've abandoned the attempts to make a selective proxy to VPN on my router"

> "I would prefer my router keeping the connection through VPN and exposing it
> through SOCKS5. I've tried running microsocks bound to VPN IP, but I can't
> get it to route correctly, all the traffic goes to whatever is set as default
> route at the moment."
>
> — [McMonster, Level1Techs Forum](https://forum.level1techs.com/t/openwrt-as-a-socks5-gateway-to-vpn/212040), June 2024

After months of debugging with strace, testing multiple SOCKS5 server
implementations, and wrestling with routing tables, McMonster gave up entirely:

> "Just for completeness I'll mention that I've abandoned the attempts to make a
> selective proxy to VPN on my router. [...] I have many self-hosted apps I want
> to exclusively use the VPN, not all of them natively support running through a
> proxy. So instead I created a separate VM, installed Mullvad CLI and put all
> the apps there."

Two other users confirmed they had done the same — creating dedicated VMs as a
workaround for what should be a firewall feature. The thread accumulated 7 likes,
indicating many readers identified with the problem.

### "Does anyone know of a way to get pfSense to act as a SOCKS5 proxy?"

> "Does anyone know of a way to get PFSENSE to act as a socks5 proxy? I have
> squid installed for HTTP but I have some need for SOCKS5 as well. I don't see
> any packages available at this point."
>
> — [dlewis_nepean, Netgate Forum](https://forum.netgate.com/topic/81228/socks5-proxy), March 2015

> "I'm surprised that there isn't another solution. Squid works perfectly for
> HTTP, but nothing that I can find works for SOCKS."

This thread is from **2015** — over 10 years ago. The eventual workaround was
manually installing the FreeBSD `dante` package, which breaks on pfSense
upgrades and provides no GUI.

### "Going from OpenWrt to OPNsense is a learning process"

> "Going from openwrt to opnsense is a learning process"
>
> — [jojothehumanmonkey, OPNsense Forum](https://forum.opnsense.org/index.php?topic=19130.0), January 2021

A common pattern: users who had working transparent SOCKS5 routing on OpenWrt
(via redsocks, tun2socks, or Clash) migrate to OPNsense and discover the
capability simply doesn't exist. The "learning" isn't about complexity — it's
about missing functionality.

### "Many people interested in shadowsocks in China"

When the OPNsense Shadowsocks plugin was first proposed, the maintainer asked:

> "Is there really a need for this?"
>
> — [mimugmail, GitHub Issue #467](https://github.com/opnsense/plugins/issues/467), January 2018

The reply:

> "Many people interested in shadowsocks in China. If we could config
> shadowsocks like OpenWrt, we'll be very thankful for what you do."
>
> — Laven7

The Shadowsocks plugin was eventually merged — but it only provided `ss-local`
and `ss-server` (a local SOCKS5 listener and server). It never included
transparent gateway routing. That gap is exactly what Proxy Gateway fills.

### Timeline of Unmet Demand

| Year | Platform | Thread | Resolved? |
|------|----------|--------|-----------|
| 2015 | pfSense | ["Socks5 Proxy"](https://forum.netgate.com/topic/81228/socks5-proxy) | Manual Dante workaround |
| 2018 | GitHub | [#467: "Shadowsocks for OPNsense"](https://github.com/opnsense/plugins/issues/467) | Plugin created, but no gateway routing |
| 2019 | OPNsense | ["Redirect all traffic to Shadowsocks"](https://forum.opnsense.org/index.php?topic=10908.0) | Never solved (3.5 years of visitors) |
| 2019 | OPNsense | ["Running external SOCKS5 proxy on WAN"](https://forum.opnsense.org/index.php?topic=12488.0) | Manual FreeBSD ports compilation |
| 2019 | GitHub | [#1423: "Clash for OPNsense"](https://github.com/opnsense/plugins/issues/1423) | Closed, no implementation |
| 2020 | OPNsense | ["Can't redirect TCP/UDP to SOCKS5 proxy"](https://forum.opnsense.org/index.php?topic=16742.0) | Zero replies, 5+ years |
| 2023 | OPNsense | ["SOCKS server as interface or gateway?"](https://forum.opnsense.org/index.php?topic=34058.0) | Told to "forget about it" |
| 2023 | OPNsense | ["Route subnet through Shadowsocks"](https://forum.opnsense.org/index.php?topic=35241.0) | User fell back to separate Linux box |
| 2023 | Blog | [Kre3: Manual tun2socks on OPNsense](https://blog.kre3.net/en/article/setup-tun2socks-in-opnsense/) | 10+ step manual procedure published |
| 2024 | Level1Techs | ["OpenWRT as SOCKS5 gateway"](https://forum.level1techs.com/t/openwrt-as-a-socks5-gateway-to-vpn/212040) | User gave up, created VM |
| 2024 | GitHub | [#3888: "UDP doesn't work in Shadowsocks"](https://github.com/opnsense/plugins/issues/3888) | TCP-only bug confirmed |
| 2025 | OpenWrt | ["tun2socks redirect all traffic"](https://forum.openwrt.org/t/tun2socks-socks5/242342) | Still struggling with nftables |

## Nothing Else Does This

### OPNsense — No Built-in Solution

OPNsense has no concept of proxy-as-gateway. Its routing system handles physical
interfaces, VLAN interfaces, and VPN tunnel interfaces — but not proxy
connections.

The closest existing plugins:

| Plugin | What it does | What it doesn't do |
|--------|-------------|-------------------|
| **os-shadowsocks** | Runs a Shadowsocks client (`ss-local`) as a local SOCKS5 listener on the OPNsense box | No TUN interface, no gateway, no transparent routing. Every client device must be manually configured to use the proxy. Does not include `ss-redir` (the transparent redirect component). UDP was [broken until 2024](https://github.com/opnsense/plugins/issues/3888). |
| **security/tor** | Runs Tor as a local SOCKS5 proxy bound to localhost | Same limitation — requires explicit per-client SOCKS configuration. Tor-only (cannot use arbitrary SOCKS5 servers). High latency. |
| **www/squid** | Transparent HTTP/HTTPS proxy (Squid) | HTTP/HTTPS only — cannot handle arbitrary TCP, UDP, or non-HTTP protocols. Being deprecated from OPNsense. Not a gateway. Cannot route to an upstream SOCKS5 server. |
| **os-wireguard** | WireGuard VPN tunnels with full gateway integration | Requires a WireGuard server on the remote end. Cannot connect to SOCKS5 or HTTP proxies. |
| **os-zerotier** | ZeroTier overlay network | Peer-to-peer mesh, not a proxy gateway. Requires ZeroTier on both ends. |

None of these create a routable gateway from a SOCKS5 or HTTP proxy. None enable
transparent routing for entire subnets or proxy-unaware devices.

**Example of the gap in practice:** A user runs a Shadowsocks server to bypass
censorship. They install `os-shadowsocks` on OPNsense, expecting it to work like
OpenWrt — where Shadowsocks can transparently route all LAN traffic. Instead,
they get a local SOCKS5 listener. Every phone, tablet, smart TV, and IoT device
on the network must be individually configured to use `192.168.1.1:1080` as a
SOCKS5 proxy — assuming the device even supports it (most IoT devices do not).

With Proxy Gateway: create a connection, assign the interface, add one firewall
rule for the LAN subnet, done. Every device on the network transparently routes
through the proxy.

### pfSense — No SOCKS5 Support At All

pfSense has no SOCKS5 support in any form — not as a client, not as a server,
not as a gateway. There is no package, no plugin, no built-in feature.

> "I'm surprised that there isn't another solution. Squid works perfectly for
> HTTP, but nothing that I can find works for SOCKS."
>
> — dlewis_nepean, Netgate Forum, 2015

The only documented workaround is manually SSH-ing into pfSense, downloading the
FreeBSD ports tree, compiling `dante` from source, and configuring it via config
files. This is unsupported, undocumented, and breaks on every pfSense upgrade
because `/usr/local/` is wiped during updates.

**Example:** A home user has a multi-WAN pfSense setup and wants to add a SOCKS5
proxy as a third "WAN exit" for specific devices. On pfSense, this is impossible
without moving to a completely different platform.

### Commercial Firewalls — None Offer This

No major commercial firewall vendor provides proxy-to-gateway routing:

| Vendor | SOCKS5 as Gateway? | What They Actually Offer |
|--------|:------------------:|-------------------------|
| **Fortinet FortiGate** | No | Explicit web proxy with SOCKS support (FortiOS 7.6+) and proxy chaining. Clients must be configured to use the proxy. Does not create a routable gateway interface. |
| **Palo Alto Networks** | No | Transparent and explicit HTTP proxy only. No SOCKS5 at all. Positions itself as a *replacement* for proxies, not a bridge to them. |
| **Check Point** | No | HTTP proxy only via SmartDashboard. No SOCKS5. No gateway conversion. |
| **Sophos XG/XGS** | No | Web filtering proxy (HTTP/HTTPS). No SOCKS5. No gateway integration. |
| **Cisco ASA/FTD** | No | No proxy client or gateway capability. VPN-only tunneling. |
| **Ubiquiti UniFi** | No | No proxy support of any kind. VPN only. |
| **MikroTik** | No | SOCKS server (MikroTik can *be* a SOCKS server), but cannot route traffic *through* an external SOCKS proxy as a gateway. |

**Example:** A company uses Palo Alto firewalls and needs traffic from a specific
VLAN to exit through a datacenter SOCKS5 proxy for compliance. Palo Alto cannot
do this. The workaround is routing through a dedicated Linux VM that runs
tun2socks — adding complexity, latency, and another point of failure.

Commercial firewalls focus on VPN-based tunneling (IPsec, SSL VPN, WireGuard).
Proxy-based routing is considered outside the firewall's scope entirely.

### Manual tun2socks Setup — Expert-Level, Single-Connection, Fragile

Before this plugin, the only way to achieve proxy-as-gateway on OPNsense was a
[manual procedure documented by Kre3](https://blog.kre3.net/en/article/setup-tun2socks-in-opnsense/)
(November 2023). The blog itself notes the motivation:

> "Since the Squid package on OPNsense will be deprecated and this method cannot
> proxy UDP/QUIC traffic, a new method is used to solve this problem."

The manual process requires:

1. SSH into OPNsense as root
2. Download the tun2socks binary for FreeBSD
3. Write a YAML configuration file
4. Create a custom `rc.d` service script
5. Create a configd actions configuration file
6. Write a PHP plugin `.inc` registration file
7. Create a syshook script for early-boot startup
8. Manually assign the TUN interface in the web GUI
9. Manually configure a static IP address on the interface
10. Manually create a gateway with `fargw=1` and `monitor_disable=1`
11. Manually create firewall aliases and routing rules

| Aspect | Manual tun2socks | Proxy Gateway Plugin |
|--------|:----------------:|:-------------------:|
| Setup time | 1-2 hours (if experienced) | 5 minutes |
| SSH required | Yes, for every step | Only for initial `make install` |
| Connections supported | One per manual setup | Unlimited, via GUI |
| GUI management | None | Full OPNsense MVC integration |
| Health monitoring | None | HTTP-based health checks |
| Auto-start on boot | Custom syshook script | Built-in toggle |
| Gateway groups / failover | Manual | OPNsense gateway groups |
| Survives OPNsense upgrade | Partial (must redo some steps) | `git pull && make install` |
| Error handling | None | Structured logging, diagnostics page |
| Credential security | Depends on implementation | Env vars, 0600 file permissions |

**Example:** A user follows the Kre3 guide to set up one SOCKS5 proxy as a
gateway. It takes an hour, it works. Then they want a second proxy for failover.
They need to repeat the entire process — different YAML file, different rc.d
script, different configd action, different interface, different gateway — and
manually coordinate boot ordering. With Proxy Gateway: click +, fill in the
second proxy, click Apply.

### Linux-Based Routers (OpenWrt, DD-WRT)

OpenWrt and DD-WRT users can run tun2socks or
[redsocks](https://github.com/darkk/redsocks) via SSH. This gives them a
functional (if manual) path — which is exactly why users migrating from OpenWrt
to OPNsense are surprised to find nothing equivalent.

| Aspect | OpenWrt (tun2socks/redsocks) | OPNsense (before this plugin) |
|--------|:---------------------------:|:----------------------------:|
| Transparent SOCKS5 routing | Yes (manual CLI) | No |
| UDP support | tun2socks: yes / redsocks: no | N/A |
| GUI | None (LuCI extensions exist for some tools) | N/A |
| iptables/nftables redirect | Works (Linux netfilter) | Does not work (pf, not iptables) |
| Policy-based routing | Manual ip rules | N/A — no proxy gateway to route through |

Even on OpenWrt, users struggle with the manual configuration:

> "I create tun0 interface [...] How to redirect all traffic in tun0? [...] But
> after restart work only local traffic. [...] What I do wrong?"
>
> — [kostin, OpenWrt Forum](https://forum.openwrt.org/t/tun2socks-socks5/242342), October 2025

If it's difficult on OpenWrt (which has full iptables/nftables support), it's
even harder on OPNsense (which uses pf and has no equivalent redirect mechanism).

**Example:** A user runs OpenWrt on a travel router with tun2socks for
censorship circumvention. They upgrade to an OPNsense appliance for their home
network. Their entire SOCKS5 routing workflow — which worked on OpenWrt —
disappears. Before this plugin, the advice was "just use a VPN instead" or "run
OpenWrt in a VM alongside OPNsense."

## Why Not Just Use a VPN?

VPN protocols (WireGuard, OpenVPN, IPsec) provide native Layer 3 tunneling that
OPNsense handles natively. If you can use a VPN, use a VPN — it will be simpler,
faster, and better integrated.

But a VPN is not always an option:

### Only proxy access is available

Many services provide only SOCKS5 or HTTP proxy access, not VPN protocols:
- Residential proxy networks (Bright Data, Oxylabs, Smartproxy)
- Datacenter proxy providers
- Corporate proxy servers (the company provides a SOCKS5 proxy, not a VPN)
- Self-hosted Shadowsocks, V2Ray, Trojan, or Naiveproxy servers
- SSH dynamic port forwarding (`ssh -D`)

There is no VPN equivalent. You cannot "just use WireGuard" when the remote
endpoint only speaks SOCKS5.

### VPN traffic is blocked

Deep Packet Inspection (DPI) deployed by ISPs, governments, and corporate
networks can identify and block VPN protocols:
- WireGuard has a recognizable handshake pattern
- OpenVPN traffic is identifiable even on port 443
- IPsec IKE negotiation is easily fingerprinted

SOCKS5 over TLS looks like ordinary HTTPS traffic. Protocols like Shadowsocks,
V2Ray, and Trojan were specifically designed to be indistinguishable from normal
web browsing — because they were built for environments where VPNs are blocked.

> "I got ~70 Mbps using OpenVPN while ~250 Mbps using shadowsocks client alone.
> Would it be possible to redirect all traffic to use shadowsocks WITHOUT using
> OpenVPN?"
>
> — heartofrainbow, OPNsense Forum, January 2019

Even when VPN protocols aren't blocked, wrapping a fast proxy inside a slower VPN
(OpenVPN over Shadowsocks) can cause a 3.5x performance penalty.

### Corporate/cloud restrictions

Some environments only permit outbound connections through approved HTTP/SOCKS5
proxies. VPN connections are explicitly blocked by firewall policy. A SOCKS5
gateway lets you work within these constraints at the network level.

### Proxy-specific features

Proxy services offer capabilities that VPNs do not:
- **Rotating IP addresses** — each request exits from a different IP
- **Geographic exit selection** — choose country/city per request
- **Proxy chaining** — route through multiple proxies in sequence
- **Protocol-specific optimization** — HTTP CONNECT proxies can cache and optimize

### Existing proxy infrastructure

If you already have a working Shadowsocks server, a V2Ray deployment, or a
commercial SOCKS5 subscription, there is no reason to rebuild your entire
infrastructure as a VPN just because OPNsense doesn't natively understand proxy
protocols. Proxy Gateway bridges that gap.

## Why Firewall-Level Routing Matters

Configuring a proxy on individual devices works for a laptop running Firefox. It
fails for everything else.

> "I use SOCKS5 proxies regularly and I need to configure browsers, change
> system settings every time configuration changes."
>
> — [Alexander Molochko](https://crosp.net/blog/administration/routing-network-traffic-through-socks5-proxy-using-dd-wrt/)

> "Some applications don't respect proxy settings and send network traffic
> directly."

> "Haven't managed to configure system-wide proxy on macOS."

> "There is no better place other than a router to control all network
> communications."

### Per-Device Configuration vs. Firewall-Level Gateway

| Scenario | Per-device proxy config | Proxy Gateway |
|----------|------------------------|---------------|
| **Smart TV** (Samsung, LG, etc.) | Impossible — no SOCKS5 proxy settings in the OS | One firewall rule routes all TV traffic through the proxy |
| **Game console** (PS5, Xbox, Switch) | Impossible — no proxy settings | One firewall rule per console |
| **IoT devices** (cameras, thermostats, smart speakers) | Impossible — no proxy settings, no SSH access | Firewall rule on the IoT VLAN |
| **Guest network** (20+ transient devices) | Must configure each guest's device manually | One firewall rule for the guest subnet |
| **Entire household** (phones, tablets, laptops, TVs, IoT) | Configure each device, each app, and hope they all respect the settings | One firewall rule for the LAN |
| **Apps that ignore proxy settings** (some games, update services, telemetry) | Traffic leaks around the proxy | All traffic is routed at the IP layer — no bypass possible |
| **macOS / iOS** | Partial — system proxy, but many apps ignore it | Transparent. The device doesn't know or care. |
| **Android** | Per-WiFi proxy setting, many apps ignore it | Transparent |
| **Failover between two proxies** | No automatic failover in any OS | OPNsense gateway groups handle automatic failover |
| **Kill switch if proxy goes down** | Depends on each app; most have none | Block the subnet's direct WAN access via firewall rules |
| **Auditing / logging** | Per-device, if at all | Centralized in OPNsense firewall logs |

**Example: Censorship circumvention for a family.** A household of 5 people has
15+ devices (phones, tablets, laptops, a smart TV, a game console, IoT devices).
Each person would need to configure SOCKS5 settings on every device and every
app — and some devices (the TV, the console, the smart speakers) simply cannot
be configured. With Proxy Gateway: one connection, one firewall rule on the LAN
subnet, and every device in the household transparently exits through the proxy.
Nobody needs to install anything. Nobody needs to know the proxy exists.

**Example: Isolating IoT traffic.** IoT devices on a dedicated VLAN should
exit through a specific proxy for privacy (hiding your home IP from IoT
manufacturers). These devices have no proxy settings. A firewall rule on the IoT
VLAN that routes through `PROXYGW_IOTPROXY` handles all of them with zero device
configuration.

**Example: Corporate policy enforcement.** A company network requires that all
traffic from the R&D VLAN exit through a monitored proxy. Employees cannot bypass
this by disabling proxy settings on their devices, because routing is enforced at
the firewall. If the proxy goes down, traffic is dropped (kill switch via
firewall rules) rather than leaking to the direct WAN.

## Feature Comparison

| Feature | Proxy Gateway | os-shadowsocks | Manual tun2socks | redsocks (Linux) | Per-device config |
|---------|:------------:|:--------------:|:----------------:|:----------------:|:-----------------:|
| GUI management | Yes | Yes (limited) | No | No | N/A |
| Proxy-as-gateway | Yes | No | Yes | No (redirect only) | No |
| Multiple connections | Unlimited | One | One per setup | One per setup | Per-app |
| Auto TUN + gateway | Yes | No | Manual | No | N/A |
| Health monitoring | Periodic HTTP + history | No | No | No | No |
| Backup proxy failover | Built-in (auto switch/failback) | No | No | No | No |
| Gateway force-down | Auto on failure | No | No | No | No |
| Speed test | On-demand + scheduled | No | No | No | No |
| Traffic stats + uptime | Yes | No | No | No | No |
| Gateway groups (failover) | Yes | No | No | No | No |
| TCP + UDP support | Yes (SOCKS5) | TCP only (until 2024 fix) | Yes | TCP only | App-dependent |
| Start on boot | Toggle in GUI | Yes | Custom syshook | Custom init script | N/A |
| Survives upgrades | `git pull && make install` | Package manager | Redo manually | Redo manually | N/A |
| Transparent to devices | Yes | No | Yes | Partially | No |
| SOCKS5 + HTTP proxy | Both | Shadowsocks only | Both | Both | App-dependent |
| Diagnostics page | Yes (logs, status, health, speed) | No | No | No | N/A |
| Credential security | Env vars, 0600 perms | Config file | Varies | Config file | Stored per-app |
| Works on OPNsense | Yes | Yes | Yes (manual) | No (Linux only) | N/A |
| Works on pfSense | No | No | Partially (manual) | No | N/A |

## Use Cases

### Route an entire VLAN through a proxy

Create a proxy connection, assign the `pgw_<name>` interface, add a firewall
rule matching the VLAN source with gateway set to `PROXYGW_<NAME>`. All traffic
from that VLAN exits through the proxy. No device configuration needed.

*Real-world scenario:* A small office has a "guest" VLAN. All guest traffic
should exit through a commercial SOCKS5 proxy to separate it from the company's
WAN IP. One connection, one firewall rule.

### Geo-routing for streaming devices

Smart TVs, Apple TVs, Roku, Fire Stick, and game consoles have no proxy
settings. Route their traffic through a proxy in the desired region using a
firewall rule matching the device's IP.

*Real-world scenario:* A user in Germany wants their US-purchased Apple TV to
access US streaming content. They route the Apple TV's IP through a US-based
SOCKS5 proxy via Proxy Gateway.

### Multi-exit policy routing

Run multiple proxy connections and use OPNsense's policy-based routing to send
different traffic through different proxies.

*Real-world scenario:* Work laptop traffic goes through the corporate SOCKS5
proxy (`PROXYGW_WORK`). Streaming devices go through a residential proxy in
another country (`PROXYGW_MEDIA`). Everything else goes through the regular WAN.
Three gateways, three firewall rules.

### Proxy failover with gateway groups

Add multiple proxy gateways to an OPNsense gateway group with tier priorities.
If one proxy goes down, traffic automatically fails over to the next.

*Real-world scenario:* Two SOCKS5 proxy servers for redundancy. Both are added
as connections. Create a gateway group with `PROXYGW_PRIMARY` as Tier 1 and
`PROXYGW_BACKUP` as Tier 2. When the primary proxy is unreachable (detected by
the health check), OPNsense routes traffic through the backup automatically.

### Network-wide censorship circumvention

In environments with Deep Packet Inspection, route all household traffic through
a Shadowsocks or SOCKS5+TLS proxy transparently. No per-device setup.

*Real-world scenario:* A family in a country with internet censorship runs a
Shadowsocks server abroad. Every device in the household — phones, laptops,
smart TVs, game consoles, IoT — transparently exits through the proxy. Nobody
needs to install any app or change any setting. Guests on the WiFi are
automatically covered.

### Enforce proxy usage (no bypass)

Route a subnet through the proxy gateway and add a second firewall rule that
**blocks** direct WAN access for that subnet. Devices cannot bypass the proxy
because routing is enforced at Layer 3.

*Real-world scenario:* A company's security policy requires all engineering
VLAN traffic to pass through a monitored proxy for DLP (Data Loss Prevention).
Firewall rules: (1) route the VLAN through `PROXYGW_DLP`, (2) block all other
outbound from the VLAN. If an employee tries to bypass the proxy, the traffic is
dropped.

### Replace VPN-over-proxy with direct proxy routing

Users in censored networks often chain VPN-over-Shadowsocks, suffering a
significant performance penalty. Proxy Gateway eliminates the VPN layer entirely.

*Real-world scenario:* A user currently runs OpenVPN-over-Shadowsocks, getting
70 Mbps. The Shadowsocks proxy alone can do 250 Mbps. With Proxy Gateway, they
route traffic directly through the Shadowsocks server as a gateway — no OpenVPN
wrapper needed — recovering the full 250 Mbps throughput.

## Getting Started

```bash
# On OPNsense, as root:
git clone https://github.com/DaneBA/os-proxygateway.git ~/os-proxygateway
cd ~/os-proxygateway
make install
```

Then open **Services > Proxy Gateway** in the OPNsense web UI.

See the [README](../README.md) for quick start steps and the
[User Guide](USER_GUIDE_COMPREHENSIVE.md) for detailed configuration with
topology diagrams and firewall rule examples.
