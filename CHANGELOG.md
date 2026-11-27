# Changelog

Plugin versions (Makefile `PLUGIN_VERSION`) are listed here. The MVC model
schema has its own version (`ProxyGateway.xml`), noted where it changed.

## [1.7.0] - 2026-11-26

### Changed

- **Cron jobs move into OPNsense's cron model.** The watchdog (every minute) and speed test (every 5 minutes) come from `proxygateway_cron()` instead of `/etc/cron.d/proxygateway`. They are registered only while the plugin and at least one connection are enabled; the scripts still gate on their flag files. Apply runs `cron restart` when enabling or disabling changed what root's crontab should hold. Install and deinstall remove the old `/etc/cron.d` file so nothing runs twice.

## [1.6.3] - 2026-11-26

### Fixed

- **Route-to check counts only pass rules.** App Router loads a block rule behind each route; those have no `route-to` by design and no longer trigger a filter reload.

## [1.6.2] - 2026-11-26

### Fixed

- **Route-to reload is rate-limited.** Core leaves `route-to` out on purpose while the rules' gateway is down, so `watchdog.sh` reloaded the whole filter (with a DNS hiccup for every client) once a minute during an outage. It now retries at most every 15 minutes.
- **Stale legacy gateways are removed.** Older versions wrote `PROXYGW_<NAME>` into the legacy `<gateways>` section. Reconfigure removes such entries unless the connection is still enabled or something refers to the gateway.

## [1.6.1] - 2026-11-21

### Fixed

- **Path predictor:** a `nat-anchor` line is not a NAT rule; it made the tunnel path always report `nat_leak`.

## [1.6.0] - 2026-11-21

### Fixed

- **Never NAT the tunnel address out of WAN.** Automatic outbound NAT also covers the `pgw_*` network. A `no nat` rule per upstream interface keeps tunnel-sourced traffic off WAN; the watchdog probe no longer needs route pinning.

## [1.5.0] - 2026-11-21

### Fixed

- **Watchdog probe really goes through the tunnel.** With automatic outbound NAT, WAN's NAT rule covers the tunnel network (`nat on igc0 from (pgw_X:network)`); pf applies NAT before filtering, so a request bound to the tunnel address was rewritten to the WAN address, the force-gateway `route-to` rule no longer matched, and the probe left via WAN (`tun_path=nat_leak`). Since 1.3.0 the probe then went to the proxy directly — a dead tun2socks was never noticed. Now the probe is *route-pinned*: the target is resolved to one IPv4 address, a host route to it via the tunnel peer exists only for that one request (`route add -host` / `route delete`, never touching an existing specific route), and curl connects to it (`--resolve`) bound to `pgw_NAME`. When pinning is impossible the proxy-direct fallback is marked `verified=0` (“UNVERIFIED”) and counts neither as tunnel success nor failure; the healthcheck reports it as unverified, not ok.
- **Gateway resolution by device.** The watchdog looked only for `PROXYGW_<NAME>`; a connection whose interface carries a user-made gateway (e.g. `FRP_GW` on the assigned interface) had nothing to force down and retried every minute. Gateways are now resolved by device `pgw_NAME` (plus `PROXYGW_<NAME>` by name). Force-down is a persistent config.xml edit with no runtime equivalent in OPNsense (a monitor-disabled gateway's status comes only from `force_down`), so it is applied only to the plugin's own `PROXYGW_` gateways; for a foreign gateway the watchdog logs once that it skips the force-down and relies on the runtime chain repair below.

### Added

- **Tunnel repair.** After *Failover Threshold* (N, default 3) consecutive failed tunnel probes the watchdog checks the SOCKS step (direct probe of the active proxy) and restarts the least it has to: tun2socks when the proxy answers (or cannot be probed, e.g. Shadowsocks); the local proxy daemon (e.g. `sslocal` via `service sslocal-rust restart`) when the proxy is on this router, is a known proxy daemon and does not answer. A proxy elsewhere that does not answer is only logged. Backoff 2/4/8 min between restarts, at most 3 restarts per connection per hour. State in `/var/run/proxygateway/<name>.repair`.
- **Syslog.** Repair steps, skipped force-downs and unverified probes go to syslog (ident `proxygateway`, priority notice or higher, so OPNsense's catch-all keeps them in `/var/log/system/`) in addition to `/var/log/proxygateway/watchdog.log`.
- **`configctl proxygateway restartconn NAME`** — starts a connection whose tun2socks or interface is down (name validated against the enabled connections, shared lock with reconfigure/watchdog, no config.xml change); a running connection is left alone. The healthcheck's “tun2socks” and “interface” checks carry it as `"fix": {"action": "proxygateway restartconn NAME", "title": ...}` when they fail.
- Healthcheck: `NAME: auto-repair` check (repair capped / failed / upstream not answering / recent restarts).

## [1.4.0] - 2026-11-21

### Added

- **`configctl proxygateway healthcheck`** — read-only health summary in the os-netbaseline plugin health contract (`{"checks": [{name, ok, severity, detail}]}`), so the Netbaseline checkup reports Proxy Gateway problems. Per enabled connection: tun2socks process alive, `pgw_NAME` up/running, the watchdog's last connectivity probe (stale after 15 min) and failover state (forced down / on backup), and the OPNsense gateway on `pgw_NAME` with its dpinger status (`gateway_health.php`). Sends no traffic, prints no proxy addresses or credentials.

### Changed

- The per-connection connectivity probe action is renamed from `healthcheck NAME` to **`probe NAME`** (`configctl proxygateway probe NAME`); the Diagnostics page uses the new name. `healthcheck` without parameters is now the summary above.

## [1.3.0] - 2026-11-21

Model schema 0.4.2 (new field `failbackThreshold`, default 3; no migration).

### Changed

- **Health check tests the tunnel** — the probe is sent through the tunnel (`curl --interface pgw_NAME`) when the firewall really routes it there. If outbound NAT on another interface covers the tunnel address (then a tunnel-bound probe silently leaves via WAN) or the force-gateway `route-to` rule is missing, the probe goes straight to the proxy instead and is labelled `mode=proxy`, `tun_path=nat_leak|no_route_to`. Logic moved to `pgwhealth.py`/`healthcheck.py`; `healthcheck.sh` is a wrapper.
- **Default probe target** is `https://www.baidu.com/` (was `http://1.1.1.1/`, which intermittently returned empty replies through a China exit).
- **Failover hysteresis** — N (`failoverThreshold`) consecutive failures before switching, M (`failbackThreshold`, new) consecutive primary probes after the cooldown before failing back.
- **Backup must work before it is used** — the watchdog probes the backup proxy directly and only switches when that probe succeeds. A dead backup is recorded as `backup_status=down` (shown as "BACKUP DOWN" on Diagnostics) and the gateway is forced down instead. When the backup fails, the watchdog returns to primary only if primary probes OK. Shadowsocks backups cannot be probed directly and are never switched to automatically.

### Added

- `watchdog.py --dry-run` — runs the checks and the failover decision, logs what it would do, changes nothing.
- `tests/` (pytest).

## [1.2.0] - 2026-09-24

Model schema 0.4.1 (migration M0_4_1). The first Apply after upgrading
restarts every running tunnel once, so it is rewritten in the new runtime
format.

### Added

- **Automatic outbound NAT** — per-connection "Outbound NAT" toggle (default: on) registers SNAT rules for RFC1918 sources on each `pgw_*` interface, replacing the manual NAT step.
- **route-to self-healing** — the watchdog reloads the filter when policy-routing rules have lost their `route-to` after a gateway bounce.

### Changed

- **Speed test simplified** — one test URL per connection (default: Tele2 10 MB file, since Cloudflare's endpoint can return a JS challenge). The unused "test file size" and "domestic URL" settings are gone.
- **Hot-updated settings** — health check target, speed test URL and backup settings take effect on Apply without restarting the tunnel.
- **Restart detection** — a connection restarts on Apply when any restart-relevant setting changes (including passwords, MTU and tunnel address, which were previously ignored).

### Security

- **Root command injection via `.conf` files** — `healthcheck.sh` and `speedtest.sh` sourced `/var/run/proxygateway/<name>.conf`, which held user-controlled values (proxy password, health check / speed test URLs) in double quotes. A value containing `"$(...)"` ran as root. Values are now single-quoted and read with a parser; the files are never sourced.
- **Credentials in process listings** — tun2socks received the proxy URL (with password) via `-proxy`, and curl via `--proxy`. tun2socks now reads it from a `0600` YAML file (`-config`), curl from `-K -` on stdin.
- **Credentials not URL-encoded** — passwords containing `@ : / ? # %` broke URL parsing (or could inject URL parameters). They are now percent-encoded.
- **Name validation bypass with trailing newline** — PHP `preg_match('/^...$/')` and `echo | grep` accept `"name\n..."`. PHP regexes and model masks now use the `D` modifier; shell scripts validate with `case`.
- **tun2socks download integrity** — SHA256 is pinned for freebsd-amd64/arm64 and verification is mandatory; download uses a private temp dir.
- **desired.json** (all passwords in plaintext) is written with umask 077 and atomically replaced.
- **Removed misleading proxy types** — "SOCKS5 + TLS" and "HTTPS CONNECT" silently connected in plaintext (tun2socks has no TLS transport to the proxy), and "SSH" never worked (tun2socks rejects the scheme). Migration M0_4_1 maps `socks5tls → socks5` and `https → http` (no behaviour change) and turns `ssh` into a disabled socks5 connection/backup. The SSH key file fields are removed.
- `make activate` and the package post-install now run model migrations.
- File headers and LICENSE name "os-proxygateway contributors" as copyright holder; repository links point to `github.com/DaneHou/os-proxygateway`.

### Fixed

- **Speed test "Parameter mismatch"** — configd parameters now match the action definition.
- **Failover never ran while processes were alive** — `watchdog.sh` only invoked `watchdog.py` when a PID was dead, so health-based failover and force-down never triggered in the common case (proxy down, tun2socks alive).
- **Gateway stayed force-down forever** — nothing cleared `force_down` after recovery. The watchdog now tracks it and brings the gateway back up once healthy, and no longer rewrites config.xml every minute while down.
- **Every Apply restarted every tunnel** — `connection_changed` compared `backupEnabled="0"` against a missing key. Change detection now uses a hash of all restart-relevant settings, which also picks up password/MTU/tunnel address changes that were previously ignored.
- **Backup settings lost after failover/restart** — watchdog re-created the `.conf` without the extra section; it now rewrites it through the same code as reconfigure.
- **Watchdog/reconfigure race** — both could run setup/teardown for the same connection concurrently. They now share a `lockf(1)` lock (the old `reconfigure.lock` check referenced a file nothing created).
- `reconfigure.sh` used bash-only `PIPESTATUS`, which fails under FreeBSD `/bin/sh`.
- `watchdog.sh` called `/usr/local/bin/configctl` (actual path: `/usr/local/sbin`).
- Speed test for Shadowsocks connections used a socks5 URL against the ss server; it now goes through the TUN interface.
- Anti-loop firewall rules for IPv6 proxy servers used `inet` and a bracketed address, breaking the pf ruleset.

## [1.1.0] - 2026-03-08

Model schema 0.4.0.

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
