# OS Proxy Gateway for OPNsense

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD--2--Clause-blue.svg)](LICENSE)
[![OPNsense](https://img.shields.io/badge/OPNsense-24.7+-orange.svg)](https://opnsense.org/)
[![FreeBSD](https://img.shields.io/badge/FreeBSD-14.x-red.svg)](https://www.freebsd.org/)

**⚠️ SECURITY NOTICE:** This is a **Release Candidate (rc1)** with one remaining critical security issue. **NOT RECOMMENDED for production use** until config.xml password encryption is implemented. See [Security Status](#security-status) below.

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

⚠️ **Before You Start:** Please read the [Security Status](#security-status) section below.

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
- **[Quick Guide](docs/guide.md)** - Original concise guide
- **[Release Notes](RELEASE_NOTES.md)** - Version history and changes
- **[Security Policy](SECURITY.md)** - Security status and best practices
- **[Security Review](SECURITY_REVIEW.md)** - Complete security audit
- **[Security Fixes Guide](SECURITY_FIXES_IMPLEMENTATION_GUIDE.md)** - Implementation details

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

**Current Version:** 1.0.0-rc1 (Release Candidate)
**Production Ready:** ⚠️ **NO**
**Security Level:** 🟡 **Partially Secure**

### What's Fixed ✅

- ✅ **Runtime credential protection** - Passwords never appear in process listings
- ✅ **Secure file permissions** - All sensitive files restricted to root-only access
- ✅ **Environment variable credential passing** - No command-line password exposure
- ✅ **Secure temporary files** - Moved from /tmp to /var/run to prevent attacks
- ✅ **Enhanced input validation** - Strict validation on all user inputs

### Remaining Critical Issue ⚠️

**CRITICAL-3: Config.xml Password Encryption**

- **Issue:** Proxy passwords stored in plaintext in `/conf/config.xml`
- **Impact:** Configuration backups, HA sync, and config exports contain plaintext credentials
- **Status:** Documented in `SECURITY_FIXES_IMPLEMENTATION_GUIDE.md`
- **Fix Planned:** Version 1.1.0
- **Workaround:** Use strong unique passwords; restrict config access; deploy only in trusted environments

### Safe Usage Until Fix

✅ **Testing environments with trusted administrators**
✅ **Home labs and development setups**
✅ **Non-production testing**

❌ **Production deployments**
❌ **Enterprise environments**
❌ **Untrusted networks**
❌ **Systems with multiple administrators**

**See [SECURITY.md](SECURITY.md) for complete security policy and best practices.**

## OPNsense Official Plugin Status

**Current Status:** ⚠️ NOT READY for official submission

**Blockers:**
1. Config.xml encryption must be implemented (CRITICAL-3)

**Ready After Fix:**
- ✅ All security requirements will be met
- ✅ Code quality meets OPNsense standards
- ✅ Documentation complete
- ✅ MVC framework properly used

## License

BSD-2-Clause
