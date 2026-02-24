# Security

## Credential Storage

Proxy passwords are stored in plaintext in `/conf/config.xml`. This is consistent with how OPNsense stores other credentials (OpenVPN, IPsec, etc.).

**Implications:**
- Config backups contain plaintext passwords
- HA sync transmits passwords (over encrypted channel)
- Admins with config access can view passwords

**Recommendations:**
- Use strong, unique passwords per proxy connection
- Encrypt config backups stored externally
- Consider SSH tunnels with key auth (no password needed)
- Restrict admin access to trusted personnel

## Runtime Security

- Passwords are never exposed in process listings (`ps`)
- Credentials passed via environment variables, not command-line arguments
- Runtime config files (`/var/run/proxygateway/*.conf`) are `0600 root:wheel`
- Log files redact passwords

## Reporting Vulnerabilities

Report security issues via [GitHub Security Advisories](https://github.com/DaneBA/os-proxygateway/security/advisories). Do not open public issues for security vulnerabilities.
