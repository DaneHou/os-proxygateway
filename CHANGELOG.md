# Changelog

## [0.4.0] - 2026-03-08

### Added

- **Traffic statistics** — real-time per-connection traffic in/out counters parsed from `netstat`
- **Connection uptime** — tracks `STARTED_AT` timestamp in .conf, displays uptime in diagnostics
- **Periodic health checks** — watchdog runs health checks every 60s for all enabled connections, logs JSON-line history to `/var/log/proxygateway/{name}_health.log`
- **Health history API** — `GET /api/proxygateway/diagnostics/getHealthHistory` returns recent health check results
- **Health history UI** — mini status indicators (green/red dots) for last 10 health checks in diagnostics
- **Backup proxy support** — configure a backup proxy per connection with type, server, port, and optional auth
- **Automatic failover** — watchdog switches to backup proxy after configurable consecutive health failures (default: 3)
- **Automatic failback** — when primary proxy recovers (2 consecutive successful probes), automatically switch back after 5-minute cooldown
- **Gateway force-down** — new `gateway_force_down.php` script sets `force_down=1` on the gateway when no backup is available and health fails
- **Auto force-down setting** — global toggle (`autoForceDown`) to enable/disable automatic gateway force-down
- **Failover state tracking** — `.failover` JSON files in `/var/run/proxygateway/` track active proxy, failure counts, switch history
- **Speed test** — on-demand bandwidth testing through each proxy connection via diagnostics page
- **Scheduled speed test** — cron-based periodic speed tests with history logging
- **Speed test history API** — `GET /api/proxygateway/diagnostics/getSpeedTestHistory` returns results
- **Backup proxy firewall rules** — anti-routing-loop rules auto-generated for backup proxy servers
- **Migration M0_4_0** — schema migration with defaults for all new model fields

### Changed

- **watchdog.py** — expanded from simple PID monitor to full monitoring loop with health checks, failover logic, and primary probing
- **healthcheck.sh** — now appends JSON-line history to health log files
- **setup.sh** — records `STARTED_AT` timestamp in .conf for uptime tracking
- **status.py** — reports traffic stats, uptime, active proxy, failover state, and gateway force-down status
- **proxygateway.inc** — generates backup proxy fields in desired.json, writes autoforcedown flag file, backup antiloop firewall rules, `sync_gateways` no longer overwrites `force_down`
- **reconfigure.py** — saves backup proxy config and speed test URLs to .conf files
- **diagnostics.volt** — new columns for traffic, uptime, health dots, backup badge, speed test UI
- **index.volt** — backup proxy field toggles, "Connected (Backup)" status badge

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
