# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | Yes                |
| 1.0.x   | Yes                |
| < 1.0   | No                 |

Only the latest release receives security fixes. Upgrade to the latest version
by running `git pull && make install` on your OPNsense system.

## Reporting Vulnerabilities

**Do not open public GitHub issues for security vulnerabilities.**

Report security issues through
[GitHub Security Advisories](https://github.com/DaneBA/os-proxygateway/security/advisories/new).

When reporting, please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof of concept
- The plugin version and OPNsense version you tested on
- Any suggested fix, if you have one

## Response Timeline

- **Acknowledgment:** within 72 hours of your report
- **Initial assessment:** within 1 week
- **Fix or mitigation:** depends on severity, typically within 2 weeks for
  critical issues

You will be credited in the fix commit and changelog unless you prefer to
remain anonymous.

## Security Design

### Privilege Model

The plugin runs as **root** on OPNsense, which is standard for OPNsense
plugins. All backend scripts (`setup.sh`, `teardown.sh`, `reconfigure.py`) are
executed by configd, which runs as root.

### Credential Handling

- Proxy passwords are stored in **plaintext** in `/conf/config.xml`. This is
  consistent with how OPNsense stores credentials for OpenVPN, IPsec, and other
  services.
- Passwords are **never exposed in process listings** (`ps`). Scripts pass
  credentials via environment variables; tun2socks reads its proxy URL from a
  `0600` YAML file (`-config`), and curl reads it from a config on stdin
  (`-K -`).
- Credentials are percent-encoded before being placed in proxy URLs.
- Runtime config files (`/var/run/proxygateway/*.conf`, `*.t2s.yaml`,
  `desired.json`) that contain credentials are created `0600` (umask 077).
- `.conf` values are stored shell single-quoted and read back with a parser
  (`conf_get` / `pgwconf.read_conf`); they are never sourced, so a password or
  URL containing `$(...)` cannot execute commands.
- The runtime directory (`/var/run/proxygateway/`) is created with mode `0750`.
- Log files redact passwords.

### Network Security

- Anti-routing-loop firewall rules are auto-generated to prevent tun2socks
  traffic from being routed back through its own TUN interface.
- TUN interfaces use point-to-point addressing in the `172.31.0.0/16` range
  with `/32` subnets.
- Health checks use HTTP (not ICMP) because SOCKS5 proxies do not relay ICMP.

### Input Validation

- Connection names are restricted to `[a-zA-Z0-9_]{1,16}` via MVC model
  validation, and re-validated in every backend script. Regexes use the `D`
  modifier (PHP) or `case` patterns (sh) so a trailing newline cannot slip
  through.
- Proxy server addresses are validated against hostname and IP patterns.
- All user input passes through OPNsense MVC field validators before reaching
  backend scripts.

## Known Security Considerations

- **Config backups contain plaintext passwords.** Encrypt config backups stored
  off-device.
- **HA sync transmits passwords** over the encrypted xmlrpc channel between
  cluster nodes.
- **Admins with config.xml access** can read proxy credentials. Restrict admin
  access to trusted personnel.
- **tun2socks is a third-party binary** downloaded from
  [xjasonlyu/tun2socks](https://github.com/xjasonlyu/tun2socks).
  `make install-tun2socks` pins the SHA256 of each release zip and refuses to
  install on mismatch.
- **No TLS to the proxy.** tun2socks v2.6 has no TLS transport for SOCKS5 or
  HTTP proxies, so those connections are plaintext between OPNsense and the
  proxy (credentials and destination hostnames are visible on that path).
  The misleading "SOCKS5 + TLS" / "HTTPS CONNECT" types and the non-working
  "SSH" type were removed in 0.4.1. Use Shadowsocks, or carry the tunnel
  over a VPN, when that path is untrusted.
- **The connection edit dialog returns stored passwords** to the browser, like
  most OPNsense plugins. Anyone with access to the Proxy Gateway pages can read
  them.
