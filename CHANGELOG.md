# Changelog

## [1.0.2] - 2026-02-24

### Fixed

- **Gateway "defunct" fix** — auto-create `<gateway_item>` entries in config.xml with `fargw=1` and `monitor_disable=1`, eliminating manual gateway setup
- **TUN device mismatch** — let tun2socks create and own the TUN device directly via `-device pgw_<name>` instead of pre-creating and renaming
- **Menu cache path** — clear `/var/lib/php/tmp/opnsense_menu_cache.xml` (not `/tmp/`) so the Services menu appears after install
- **Makefile service name** — use `configctl webgui restart` instead of incorrect `service php-fpm restart`

### Changed

- Gateway entries now use MVC `<Gateways>` format (capital G) with UUID attributes and all required fields
- Gateway sync runs both before and after reconfigure to catch new interface assignments
- setup.sh simplified: tun2socks opens `/dev/tun` cloner, gets auto-assigned tunN, renames to `pgw_<name>`

## [1.0.1] - 2026-02-24

### Fixed

- Added UDP timeout (300s) for SOCKS5 proxies to fix UDP relay issues with Tailscale
- Fixed "packet not handled" errors when using Tailscale SOCKS5 proxy

## [1.0.0] - 2026-02-24

### Initial Release

- Multiple proxy connections (SOCKS5, SOCKS5+TLS, HTTP CONNECT, HTTPS CONNECT)
- OPNsense gateway integration with health monitoring
- Transparent routing via firewall rules
- Gateway groups for failover and load balancing
- Kill switch to prevent traffic leaks
- Web UI under Services > Proxy Gateway
- Structured logging with per-connection log files
- Auto tunnel IP assignment from 172.31.0.0/16
