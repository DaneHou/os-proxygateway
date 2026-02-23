# os-proxygateway

An OPNsense plugin that converts remote SOCKS5 and HTTP/HTTPS proxy servers into
standard OPNsense gateway interfaces. Route traffic from specific devices, VLANs,
or subnets through any proxy using standard firewall rules — no client-side
configuration required.

## Features

- **Multiple proxy connections** — Configure as many upstream proxies as you need
- **Gateway integration** — Each proxy appears as a standard OPNsense gateway
- **Transparent routing** — Route devices by IP, subnet, or VLAN via firewall rules
- **Health monitoring** — Automatic health checks with latency tracking
- **Kill switch** — Drop traffic if the proxy tunnel goes down
- **Gateway Groups** — Failover and load balancing between proxies
- **Structured logging** — Timestamped, leveled logs with per-connection filtering
- **Web UI** — Full management through the OPNsense GUI

## Supported Proxy Types

| Type | Protocol |
|------|----------|
| SOCKS5 | `socks5://` |
| SOCKS5 + TLS | `socks5://` with TLS |
| HTTP CONNECT | `http://` |
| HTTPS CONNECT | `http://` with TLS |

## Quick Start

```sh
# On your OPNsense box:
git clone https://github.com/DaneBA/os-proxygateway.git
cd os-proxygateway
make install
```

Then go to **Services → Proxy Gateway → Connections** in the OPNsense web GUI.

## Documentation

See the **[User Guide](docs/guide.md)** for:

- Detailed installation instructions
- How to configure proxy connections
- How to route traffic for specific devices (same LAN or different LAN/VLAN)
- Kill switch and traffic blocking configuration
- Logging, diagnostics, and troubleshooting
- API reference

## How It Works

```
LAN Device ──▶ OPNsense Firewall Rule ──▶ pgw_<name> (TUN) ──▶ tun2socks ──▶ Proxy Server
```

1. You configure an upstream proxy connection in the plugin
2. The plugin creates a TUN interface and runs `tun2socks` to bridge it to the proxy
3. OPNsense registers the tunnel as a gateway (`PROXYGW_<NAME>`)
4. You create firewall rules to route traffic from specific sources through that gateway
5. Routed traffic goes through the tunnel and exits via the proxy server

## Requirements

- OPNsense 24.x or later
- FreeBSD 14.x or later
- `tun2socks` v2.6.0+ (automatically downloaded during install)

## License

BSD-2-Clause
