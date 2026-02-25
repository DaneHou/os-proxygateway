# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
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
- Passwords are **never exposed in process listings** (`ps`). The reconfigure
  script passes credentials via environment variables, not command-line
  arguments.
- Runtime config files (`/var/run/proxygateway/*.conf`) that contain proxy URLs
  with embedded credentials are restricted to `0600 root:wheel`.
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
  validation.
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
  [xjasonlyu/tun2socks](https://github.com/xjasonlyu/tun2socks). The binary
  is fetched over HTTPS from GitHub Releases. Verify the binary integrity if
  your threat model requires it.
