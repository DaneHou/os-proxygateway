# CLAUDE.md — Project Guide for Claude Code

## What This Project Is

os-proxygateway is an OPNsense plugin that converts SOCKS5 and HTTP/HTTPS proxy servers into standard OPNsense gateway interfaces using tun2socks. Users route traffic through proxies via firewall rules — no client-side configuration needed.

## Target Environment

- **OS**: OPNsense 24.7+ (FreeBSD-based)
- **Default shell**: `csh` (not bash) — `2>/dev/null`, heredocs, `$var` escaping differ
- **Python**: 3.9+ (bundled with OPNsense)
- **Shell scripts**: POSIX `sh` (not bash), FreeBSD `/bin/sh`
- **PHP**: OPNsense MVC framework

## Project Structure

```
src/
├── etc/
│   ├── cron.d/proxygateway              # Cron jobs (watchdog, speedtest)
│   ├── inc/plugins.inc.d/
│   │   └── proxygateway.inc             # Core PHP plugin: firewall rules, gateway sync, desired.json generation
│   ├── newsyslog.conf.d/               # Log rotation
│   └── rc.d/                            # Service script
├── opnsense/
│   ├── mvc/app/
│   │   ├── controllers/OPNsense/ProxyGateway/
│   │   │   ├── Api/                     # REST API controllers (Connection, Service, Settings, Diagnostics)
│   │   │   ├── IndexController.php      # UI controller
│   │   │   ├── DiagnosticsController.php # UI diagnostics page
│   │   │   └── forms/                   # Form XML definitions (general.xml, connection.xml)
│   │   ├── models/OPNsense/ProxyGateway/
│   │   │   ├── ProxyGateway.xml         # MVC model: all fields, validators, defaults
│   │   │   ├── ProxyGateway.php         # Model class
│   │   │   ├── Migrations/              # Schema migrations (M0_4_0.php, etc.)
│   │   │   ├── ACL/                     # Access control
│   │   │   └── Menu/                    # OPNsense menu registration
│   │   └── views/OPNsense/ProxyGateway/
│   │       ├── index.volt               # Main connections page (Volt template)
│   │       └── diagnostics.volt         # Diagnostics page
│   ├── scripts/OPNsense/ProxyGateway/
│   │   ├── setup.sh                     # Start a connection (tun2socks + TUN interface)
│   │   ├── teardown.sh                  # Stop a connection
│   │   ├── reconfigure.py               # Orchestrates setup/teardown based on desired.json
│   │   ├── status.py                    # Get connection statuses (traffic, uptime, failover)
│   │   ├── healthcheck.sh              # HTTP-based connectivity probe
│   │   ├── watchdog.py                  # Periodic monitoring: PID check, health check, failover
│   │   ├── gateway_force_down.php       # Set gateway force_down via OPNsense Config API
│   │   ├── speedtest.sh                # Run speed test through proxy
│   │   ├── speedtest_cron.sh           # Cron wrapper for speed test
│   │   ├── generate_desired.php         # Legacy desired.json generator
│   │   ├── clear_logs.sh               # Log cleanup
│   │   └── lib/logging.sh              # Shared logging functions
│   └── service/conf/actions.d/
│       └── actions_proxygateway.conf    # configd action definitions
```

## Key Architecture Concepts

### Data Flow
1. User edits connection in Web UI → saved to `config.xml` via MVC model
2. "Apply" calls `proxygateway.inc` → generates `/var/run/proxygateway/desired.json`
3. `reconfigure.py` reads `desired.json`, compares with running state, calls `setup.sh`/`teardown.sh`
4. `setup.sh` starts tun2socks with `-device pgw_NAME`, creating TUN interface directly
5. `proxygateway.inc` syncs gateway entries (`PROXYGW_NAME`) into `config.xml`

### Gateway Integration
- Gateway entries use MVC `<Gateways>` (capital G) with UUID attributes
- `fargw=1` required for /32 point-to-point TUN interfaces
- `monitor_disable=1` because SOCKS5 doesn't support ICMP (dpinger fails)
- Gateway naming: `PROXYGW_` prefix + uppercase connection name

### Failover System (v0.4.0)
- `watchdog.py` runs every 60s via cron, checks PID + health for each connection
- Failover state stored in `/var/run/proxygateway/{name}.failover` (JSON)
- On consecutive health failures ≥ threshold: switch to backup proxy or force-down gateway
- `gateway_force_down.php` modifies `config.xml` gateway `force_down` field
- 5-minute cooldown after switch to prevent rapid flapping
- Primary probe runs independently (curl directly to primary proxy, not through TUN)

### Runtime Files
- `/var/run/proxygateway/` — PID files, .conf files, .failover state, desired.json
- `/var/log/proxygateway/` — Per-connection logs, health history, speed test results

## Code Style

### PHP
- 4-space indentation, opening brace on same line
- Follow OPNsense MVC patterns
- Match style in `proxygateway.inc` and existing controllers

### Python
- PEP 8, 4-space indent
- Use `logging` module (not print)
- Target Python 3.9+

### Shell Scripts
- POSIX `sh` (not bash) — no bashisms
- Use `lib/logging.sh` for structured logging
- Quote all variable expansions: `"$VAR"`
- Use `set -e` at top

### XML
- 4-space indentation
- Follow OPNsense MVC schema conventions

## Common Pitfalls

- **csh shell**: Inline PHP with `$var` gets interpreted by csh; use scripts instead of one-liners
- **Menu cache**: Must clear `/var/lib/php/tmp/opnsense_menu_cache.xml` after plugin install
- **PHP service**: Named `php_fpm` (underscore, not hyphen)
- **Web GUI restart**: Use `configctl webgui restart`
- **Gateway fields**: OPNsense gateway_item requires ~20 MVC fields
- **proxygateway.inc sync_gateways**: Must NOT overwrite `force_down` field (managed by watchdog)

## Testing

Test on OPNsense VM:
```sh
cd ~/os-proxygateway
make install-plugin && make activate
```

Check logs:
```sh
tail -f /var/log/proxygateway/*.log
```

Key verification points:
- `configctl proxygateway status` — connection status JSON
- `configctl proxygateway reconfigure` — apply changes
- Web UI: Services > Proxy Gateway > Diagnostics
