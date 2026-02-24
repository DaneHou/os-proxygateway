# Changelog

All notable changes to the OS Proxy Gateway plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-02-24

### Fixed

- Added UDP timeout configuration for SOCKS5 proxies to fix UDP relay issues with Tailscale and other SOCKS5 servers
- Improved UDP packet handling for DNS and other UDP-based protocols through SOCKS5 proxies
- Fixed "packet not handled" errors when using Tailscale SOCKS5 proxy connections

### Added

- Comprehensive Tailscale SOCKS5 proxy troubleshooting section in user guide
- Automatic UDP timeout (300s) for SOCKS5 and SOCKS5+TLS connections
- Detailed documentation for configuring Tailscale as a SOCKS5 proxy server

### Changed

- Enhanced tun2socks command invocation to include UDP timeout for improved SOCKS5 compatibility

## [1.0.0] - 2026-02-24

### Production Release

First stable production release of os-proxygateway. Ready for deployment in home labs, small business networks, development environments, and other trusted network scenarios.

### Added

- Multi-proxy connection support with unlimited simultaneous connections
- Full OPNsense gateway integration with dpinger health monitoring
- Transparent traffic routing via native firewall rules
- Gateway groups support for failover and load balancing
- Kill switch functionality to prevent traffic leaks
- Web-based management interface integrated into OPNsense GUI
- Real-time connection status dashboard
- Health check monitoring with configurable intervals (5-3600 seconds)
- Structured logging system with per-connection log files
- Comprehensive diagnostics API
- Support for SOCKS5, SOCKS5+TLS, HTTP CONNECT, and HTTPS CONNECT proxies
- Automatic tunnel IP assignment from 172.31.0.0/16 pool
- Configurable MTU settings (1280-9000 bytes)
- Custom DNS server support with tunnel or custom DNS modes
- Log viewer with filtering capabilities
- Complete API endpoints for all operations
- Production-ready documentation suite

### Security

- Fixed runtime credential exposure in files (chmod 0600 on sensitive files)
- Fixed password exposure in process listings (environment variable passing)
- Fixed credentials in shell config files (secured with 0600 permissions)
- Fixed insecure temporary file handling (moved from /tmp to /var/run)
- Enhanced input validation for all user inputs
- Implemented secure credential passing mechanisms
- Documented credential storage considerations and best practices
- Comprehensive security review completed

### Documentation

- Complete README.md with quick start guide
- Comprehensive user guide with topology diagrams
- Security policy (SECURITY.md) with best practices
- Release notes with detailed feature descriptions
- API reference documentation
- Installation and upgrade guides
- Troubleshooting documentation
- Production deployment guidelines

### Known Limitations

- Config.xml stores passwords in plaintext (planned enhancement for v1.1.0)
- Userland tunneling limits throughput to ~200 Mbps per connection
- HTTP CONNECT proxies are TCP-only (no UDP support)
- IPv6 not currently supported
- No built-in API rate limiting (mitigated by OPNsense session management)

## [1.0.0-rc1] - 2026-02-23

### Release Candidate

Initial release candidate with core functionality complete.

### Added

- Initial plugin implementation
- Core proxy connection management
- Gateway registration system
- Basic web UI
- Logging infrastructure
- Health check system
- API endpoints

### Security

- Initial security fixes for runtime credential exposure
- File permission hardening
- Input validation implementation

---

## Release Notes

### Version Numbering

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

### Upgrade Policy

- **1.x.x versions**: Fully compatible, safe to upgrade
- **Major version changes**: Review migration guide before upgrading

### Support

- **Latest stable release**: Full support with security updates
- **Previous minor versions**: Security updates for 6 months
- **Older versions**: Upgrade recommended

---

## Upcoming Releases

### [1.1.0] - Planned

**Focus:** Enhanced Security and Monitoring

- [ ] Encrypted credential storage in config.xml
- [ ] API rate limiting implementation
- [ ] Enhanced monitoring dashboard
- [ ] Audit logging for all operations
- [ ] Automated test suite

### [1.2.0] - Future

**Focus:** Advanced Features

- [ ] IPv6 support for proxy connections
- [ ] Proxy chaining capability
- [ ] PAC file generation
- [ ] Bandwidth monitoring per connection
- [ ] Unbound DNS integration

### [2.0.0] - Long-term

**Focus:** Enterprise Features

- [ ] Certificate pinning for TLS proxies
- [ ] Credential rotation automation
- [ ] Advanced traffic matching (domain-based routing)
- [ ] Mobile app integration
- [ ] Cloud proxy subscription support

---

## Links

- **Repository**: https://github.com/DaneBA/os-proxygateway
- **Issue Tracker**: https://github.com/DaneBA/os-proxygateway/issues
- **Security Advisories**: https://github.com/DaneBA/os-proxygateway/security
- **Documentation**: See docs/ directory

---

**Note**: For detailed release information, see [RELEASE_NOTES.md](RELEASE_NOTES.md)
