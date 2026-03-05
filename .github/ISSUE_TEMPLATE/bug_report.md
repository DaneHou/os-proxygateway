---
name: Bug Report
about: Report a problem with the Proxy Gateway plugin
title: ""
labels: bug
assignees: ""
---

## Environment

- **OPNsense version:** (e.g., 26.1.3 -- run `opnsense-version`)
- **Plugin version:** (e.g., 1.0.2 -- see Makefile or Changelog)
- **Architecture:** (amd64 / arm64)
- **Installation method:** git clone + make install

## Description

A clear description of the bug.

## Steps to Reproduce

1. Go to ...
2. Configure ...
3. Click ...
4. See error

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened.

## Connection Configuration

Paste your connection config with credentials redacted:

```
Proxy type: SOCKS5
Proxy server: [REDACTED]
Proxy port: 1080
Auth enabled: No
Tunnel address: (auto)
MTU: 1500
```

## Logs

Paste relevant log output. Redact any proxy server addresses or credentials.

**Plugin logs** (`/var/log/proxygateway/<name>.log`):

```
(paste here)
```

**Reconfigure log** (`/var/log/proxygateway/reconfigure.log`):

```
(paste here)
```

**PHP errors** (`/tmp/PHP_errors.log`):

```
(paste here)
```

## Gateway Status

Paste the output of System > Gateways > Single (or `pluginctl -g`):

```
(paste here)
```

## Additional Context

Any other information that might help diagnose the issue (screenshots,
firewall rule configuration, network topology, etc.).
