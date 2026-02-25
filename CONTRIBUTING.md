# Contributing to os-proxygateway

Thanks for your interest in improving os-proxygateway. This guide covers the
development workflow, code conventions, and how to get your changes merged.

## Development Environment

You need a working OPNsense installation for testing. A VM works well:

1. Install OPNsense 24.7+ in a VM (VirtualBox, Proxmox, etc.)
2. Enable SSH access: System > Settings > Administration > Enable Secure Shell
3. SSH in as root and clone the repo:

```sh
git clone https://github.com/DaneBA/os-proxygateway.git ~/os-proxygateway
cd ~/os-proxygateway
make install
```

4. Hard-refresh your browser (Ctrl+Shift+R) to pick up menu changes
5. Navigate to Services > Proxy Gateway

For iterative development, use:

```sh
make install-plugin && make activate
```

This reinstalls plugin files without re-downloading tun2socks.

## Code Style

### PHP

Follow OPNsense conventions:

- 4-space indentation
- Opening brace on the same line for functions
- Use OPNsense MVC patterns (models, controllers, forms, views)
- Docblocks on public functions
- Match the style in `proxygateway.inc` and the existing controllers

### Python

- PEP 8 with 4-space indentation
- Use `logging` (not `print`) for operational messages
- Match the structured logging format in `reconfigure.py`
- Target Python 3.9+ (the version bundled with OPNsense)

### Shell Scripts

- POSIX `sh` (not bash). OPNsense uses FreeBSD `/bin/sh`
- Use the structured logging library (`lib/logging.sh`) for output
- Quote all variable expansions: `"$VAR"`, not `$VAR`
- Prefer `$(command)` over backticks
- Use `set -e` at the top of scripts

### XML (MVC Models, Menus, ACLs)

- 4-space indentation
- Follow the existing OPNsense MVC schema conventions

## Making Changes

### Branch Naming

Use a descriptive prefix:

- `fix/` -- bug fixes (e.g., `fix/gateway-defunct-on-reboot`)
- `feat/` -- new features (e.g., `feat/ipv6-support`)
- `docs/` -- documentation only
- `refactor/` -- code restructuring without behavior changes

### Workflow

1. Fork the repository on GitHub
2. Create a feature branch from `main`
3. Make your changes
4. Test on an OPNsense installation (see below)
5. Commit with a clear message describing what changed and why
6. Push your branch and open a pull request against `main`

### Commit Messages

Write concise commit messages that explain the "why":

```
fix gateway defunct on reboot by syncing IPs before route reconfigure

The boot handler was calling reconfigure before sync_interfaces,
so gateways had no IP and showed as defunct until the next manual apply.
```

## Testing

Before submitting a PR, verify the following on an OPNsense VM:

- [ ] `make install` completes without errors
- [ ] The Services > Proxy Gateway menu appears (after browser hard-refresh)
- [ ] Create a new connection and click Apply -- the TUN interface and gateway appear
- [ ] Assign the interface in Interfaces > Assignments, enable it, apply
- [ ] The gateway shows as online in System > Gateways > Single
- [ ] Traffic routes through the proxy when a firewall rule is configured
- [ ] `make uninstall` cleanly removes the plugin
- [ ] Reboot the OPNsense VM -- connections come back if "Start on boot" is enabled

For log output during testing:

```sh
tail -f /var/log/proxygateway/*.log
```

## Reporting Bugs

Open a [GitHub issue](https://github.com/DaneBA/os-proxygateway/issues/new)
with:

- OPNsense version (`opnsense-version`)
- Plugin version (from `Makefile` or the Changelog)
- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs from `/var/log/proxygateway/`

Redact proxy credentials and server addresses before posting logs.

## Pull Request Process

1. Fill out the PR template (description, testing checklist)
2. Keep PRs focused -- one logical change per PR
3. Maintainers will review within a few days
4. Address review feedback by pushing additional commits (no force-push)
5. Once approved, a maintainer will merge

## Security Issues

Do **not** open public issues for security vulnerabilities. See
[SECURITY.md](SECURITY.md) for the private disclosure process.

## Questions?

- Open a [GitHub Discussion](https://github.com/DaneBA/os-proxygateway/discussions) for general questions
- Check existing issues before opening a new one
- For OPNsense-specific questions (not plugin-related), try the [OPNsense Forum](https://forum.opnsense.org/)

## License

By contributing, you agree that your contributions will be licensed under the
[BSD 2-Clause License](LICENSE).
