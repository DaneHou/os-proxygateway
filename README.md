# OS Proxy Gateway for OPNsense

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD--2--Clause-blue.svg)](LICENSE)
[![OPNsense](https://img.shields.io/badge/OPNsense-24.7+-orange.svg)](https://opnsense.org/)

An OPNsense plugin that converts SOCKS5 and HTTP/HTTPS proxy servers into
standard OPNsense gateway interfaces. Route traffic from specific devices,
VLANs, or subnets through any proxy using firewall rules — no client-side
configuration required.

## How It Works

```
LAN Device --> OPNsense Firewall Rule --> pgw_<name> (TUN) --> tun2socks --> Proxy Server
```

1. Configure a proxy connection in the plugin UI
2. The plugin creates a TUN interface and runs `tun2socks` to bridge it to the proxy
3. A gateway (`PROXYGW_<NAME>`) is auto-created in OPNsense
4. Create firewall rules to route traffic from specific sources through the gateway
5. Routed traffic exits via the proxy server

## Features

- **Multiple proxy connections** with SOCKS5, SOCKS5+TLS, HTTP, and HTTPS support
- **Auto gateway creation** with `fargw=1` for point-to-point TUN interfaces
- **Transparent routing** via standard OPNsense firewall rules
- **Health monitoring** with HTTP-based connectivity checks
- **Kill switch** to drop traffic if the tunnel goes down
- **Gateway groups** for failover and load balancing
- **Web UI** integrated into OPNsense under Services

## Installation

```bash
# SSH to OPNsense as root
git clone https://github.com/DaneBA/os-proxygateway.git ~/os-proxygateway
cd ~/os-proxygateway
make install
```

This downloads `tun2socks`, installs all plugin files, clears the menu cache,
and restarts configd. Hard-refresh your browser (Ctrl+Shift+R) after install.

Then go to **Services > Proxy Gateway > Connections**.

## Quick Start

1. **Add a connection** — click +, fill in proxy server details, save
2. **Apply changes** — click the Apply button
3. **Assign the interface** — go to Interfaces > Assignments, add `pgw_<name>`, enable it
4. **Apply again** — the plugin auto-configures the IP and gateway
5. **Create a firewall rule** — route a source IP/subnet through `PROXYGW_<NAME>`
6. **Add outbound NAT** — Firewall > NAT > Outbound, add a rule for the pgw interface to WAN

## Updating

```bash
cd ~/os-proxygateway
git pull
make install-plugin && make activate
```

## Uninstalling

```bash
cd ~/os-proxygateway
make uninstall
```

## Requirements

- OPNsense 24.7+ (tested on 26.1)
- `tun2socks` v2.6.0+ (auto-downloaded during install)

## Documentation

- [User Guide](docs/USER_GUIDE_COMPREHENSIVE.md) — detailed setup with topology diagrams and firewall rule examples
- [Changelog](CHANGELOG.md) — version history
- [Security](SECURITY.md) — credential storage notes

## Known Limitations

- Proxy passwords stored in plaintext in `config.xml` (same as other OPNsense credential storage)
- Userland tunneling limits throughput to ~200 Mbps per connection
- HTTP CONNECT proxies are TCP-only (use SOCKS5 for UDP)
- IPv6 not supported

## License

BSD-2-Clause
