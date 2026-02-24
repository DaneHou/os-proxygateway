# OS Proxy Gateway for OPNsense

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD--2--Clause-blue.svg)](LICENSE)
[![OPNsense](https://img.shields.io/badge/OPNsense-24.7+-orange.svg)](https://opnsense.org/)
[![FreeBSD](https://img.shields.io/badge/FreeBSD-14.x-red.svg)](https://www.freebsd.org/)

**Production Release** - Ready for deployment in home labs, small business networks, and trusted environments. See [Security Status](#security-status) for important information about credential storage.

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

**Before You Start:** Please read the [Security Status](#security-status) section to understand credential storage limitations.

```sh
# On your OPNsense box (SSH as root):
cd /usr/local
git clone https://github.com/DaneBA/os-proxygateway.git
cd os-proxygateway
make install

# Restart web interface
configctl webgui restart
```

Then navigate to **Services → Proxy Gateway → Connections** in the OPNsense web GUI.

**See:** [Comprehensive User Guide](docs/USER_GUIDE_COMPREHENSIVE.md) for detailed step-by-step instructions with topology diagrams.

## Documentation

**📚 Complete Documentation:**

- **[Comprehensive User Guide](docs/USER_GUIDE_COMPREHENSIVE.md)** - Detailed setup with topology diagrams
- **[Release Notes](RELEASE_NOTES.md)** - Version history and changes
- **[Security Policy](SECURITY.md)** - Security status and best practices

**📖 Guides Include:**

- Detailed installation instructions
- How to configure proxy connections
- How to route a specific device by IP (same LAN or isolated VLAN/LAN)
- How to route traffic from an isolated IoT LAN through a LAN-side proxy (e.g., Tailscale SOCKS5 on LAN2 serving devices on a blocked LAN3)
- Kill switch and traffic blocking configuration
- Firewall rule examples with network topology diagrams
- Gateway groups for failover and load balancing
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

- OPNsense 24.7 or later
- FreeBSD 14.x or later
- `tun2socks` v2.6.0+ (automatically downloaded during install)

## Security Status

**Current Version:** 1.0.0
**Production Ready:** ✅ **YES** (with documented limitations)
**Security Level:** 🟢 **Production Ready**

### Security Features ✅

- ✅ **Runtime credential protection** - Passwords never appear in process listings
- ✅ **Secure file permissions** - All sensitive files restricted to root-only access
- ✅ **Environment variable credential passing** - No command-line password exposure
- ✅ **Secure temporary files** - Moved from /tmp to /var/run to prevent attacks
- ✅ **Enhanced input validation** - Strict validation on all user inputs

### Important Security Consideration

**Config.xml Password Storage**

- **Note:** Proxy passwords are stored in plaintext in `/conf/config.xml`
- **Impact:** Configuration backups, HA sync, and config exports contain plaintext credentials
- **Best Practices:**
  - Use strong, unique passwords for each proxy connection
  - Restrict access to configuration backups and system access
  - Consider using SSH tunnels with key-based authentication (eliminates password need)
  - Deploy in trusted environments with controlled administrative access
- **Future Enhancement:** Encrypted credential storage planned for version 1.1.0

### Recommended Deployment Scenarios

✅ **Home labs and home networks**
✅ **Small business networks with trusted administrators**
✅ **Development and testing environments**
✅ **Networks with controlled administrative access**
✅ **Environments using SSH key-based proxy authentication**

⚠️ **Additional Security Recommended For:**
- **Enterprise environments** - Implement additional access controls
- **Multi-administrator systems** - Use role-based access controls
- **High-security environments** - Consider SSH tunnels with key auth instead of passwords

**See [SECURITY.md](SECURITY.md) for complete security policy and best practices.**

## OPNsense Official Plugin Status

**Current Status:** Ready for community use and testing

**Plugin Quality:**
- ✅ All core security requirements met
- ✅ Code quality meets OPNsense standards
- ✅ Documentation complete
- ✅ MVC framework properly implemented
- ✅ Production-ready for typical deployments

**Note:** Official OPNsense plugin repository submission is planned after community feedback and broader testing. The plugin is fully functional and ready for production use in appropriate environments.

## License

BSD-2-Clause
