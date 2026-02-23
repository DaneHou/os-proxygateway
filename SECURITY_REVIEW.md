# Security Review of os-proxygateway

**Review Date:** 2026-02-23
**Reviewer:** Security Review Agent
**Component:** OPNsense Proxy Gateway Plugin

## Executive Summary

This security review identifies **13 security issues** in the os-proxygateway plugin, ranging from **CRITICAL** to **LOW** severity. The most critical issues involve plaintext credential storage in world-readable files and exposure of passwords in process arguments.

### Risk Summary

| Severity | Count | Issues |
|----------|-------|--------|
| CRITICAL | 3 | Plaintext passwords in files, process arguments, config backups |
| HIGH | 3 | Shell config files with creds, temp file vulnerabilities, log exposure |
| MEDIUM | 4 | URL validation, health check disclosure, API rate limiting, syslog exposure |
| LOW | 3 | Interface naming disclosure, missing cert pinning, health check target hardcoded |

**Overall Assessment:** The plugin has a solid architecture but requires immediate attention to credential handling before it can be considered production-ready or suitable for OPNsense official plugin repository.

---

## Critical Issues

### CRITICAL-1: Plaintext Passwords in desired.json

**File:** `src/opnsense/mvc/app/controllers/OPNsense/ProxyGateway/Api/ServiceController.php:70-86`

**Issue:**
The `reconfigureAction()` method writes all connection configurations, including plaintext passwords, to `/var/run/proxygateway/desired.json`. This file is created with default permissions (likely 0644), making it world-readable.

**Code:**
```php
$connections = [];
foreach ($model->connections->connection->iterateItems() as $uuid => $connection) {
    if ((string)$connection->enabled === '1') {
        $conn_data = [
            'uuid' => $uuid,
            'name' => (string)$connection->name,
            // ... other fields ...
            'authEnabled' => (string)$connection->authEnabled === '1',
            'authUser' => (string)$connection->authUser,
            'authPass' => (string)$connection->authPass,  // ← PLAINTEXT PASSWORD!
        ];
        $connections[] = $conn_data;
    }
}
$desired = ['connections' => $connections];
file_put_contents('/var/run/proxygateway/desired.json', json_encode($desired, JSON_PRETTY_PRINT));
```

**Impact:**
- Any local user can read all proxy credentials
- System monitoring tools may capture this file
- Backup systems may archive it
- Compromised non-root accounts can harvest credentials

**Proof of Concept:**
```bash
# As any user on the OPNsense system:
cat /var/run/proxygateway/desired.json
# Reveals all proxy passwords in plaintext
```

**Recommendations:**

1. **Immediate Fix (Permissions):**
   ```php
   $desired_file = '/var/run/proxygateway/desired.json';
   file_put_contents($desired_file, json_encode($desired, JSON_PRETTY_PRINT));
   chmod($desired_file, 0600);  // Owner read/write only
   chown($desired_file, 'root:wheel');
   ```

2. **Better Solution (Encrypted IPC):**
   - Use OPNsense's configd socket communication instead of file-based IPC
   - Pass credentials through environment variables to child processes
   - Implement a credential vault pattern

3. **Best Solution (Credential Encryption):**
   - Encrypt passwords in the XML model using OPNsense's config encryption
   - Decrypt only in memory when needed
   - Reference: See how OPNsense handles VPN credentials

**OPNsense Plugin Requirement Violation:**
This violates OPNsense's security best practices for credential handling. Official plugins must not store plaintext secrets in world-readable files.

---

### CRITICAL-2: Passwords Visible in Process Arguments

**File:** `src/opnsense/scripts/OPNsense/ProxyGateway/setup.sh:85-105`

**Issue:**
The `setup.sh` script receives the proxy password as a command-line argument (`--auth-pass <password>`) and constructs the proxy URL with embedded credentials. This makes passwords visible in:
- Process listing (`ps aux`)
- `/proc/<pid>/cmdline`
- Process accounting logs
- System monitoring tools

**Code:**
```bash
# setup.sh is called with:
setup.sh myconn socks5 proxy.example.com 1080 --auth-user admin --auth-pass secret123

# Later constructs:
PROXY_URL="socks5://admin:secret123@proxy.example.com:1080"

# Then spawns tun2socks:
/usr/local/bin/tun2socks -device tun0 -proxy "$PROXY_URL" &
```

**Impact:**
- Any user can see passwords via `ps auxww | grep setup.sh`
- Process monitoring tools capture credentials
- tun2socks process may log the proxy URL with embedded credentials
- Forensic analysis of system reveals historical passwords

**Proof of Concept:**
```bash
# On OPNsense system while connection is being set up:
ps auxww | grep -E 'setup\.sh|tun2socks'
# Output shows: setup.sh myconn socks5 1.2.3.4 1080 --auth-pass MySecretPassword
```

**Recommendations:**

1. **Immediate Fix (Environment Variables):**
   ```bash
   # In reconfigure.py, instead of passing --auth-pass as argument:
   env = os.environ.copy()
   env['PROXY_AUTH_PASS'] = password
   subprocess.run(['/bin/sh', 'setup.sh', name, ...], env=env)

   # In setup.sh, read from environment:
   if [ -n "$PROXY_AUTH_PASS" ]; then
       AUTH_PASS="$PROXY_AUTH_PASS"
   fi
   ```

2. **Better Solution (File Descriptor Passing):**
   ```bash
   # Write password to temporary file descriptor
   echo "$password" | /bin/sh setup.sh myconn socks5 ... --auth-pass-fd 3 3<&0
   ```

3. **Best Solution (Named Pipe):**
   ```bash
   # Create named pipe, pass credentials through it
   mkfifo /var/run/proxygateway/${NAME}.auth
   chmod 600 /var/run/proxygateway/${NAME}.auth
   (echo "$password" > /var/run/proxygateway/${NAME}.auth &)
   /bin/sh setup.sh myconn ... --auth-pass-file /var/run/proxygateway/${NAME}.auth
   ```

**OPNsense Plugin Requirement Violation:**
Official plugins must not expose credentials in process arguments. This is a security audit failure.

---

### CRITICAL-3: No Encryption of Credentials in Configuration

**File:** `src/opnsense/mvc/app/models/OPNsense/ProxyGateway/ProxyGateway.xml:220-223`

**Issue:**
Proxy authentication passwords are stored in plaintext in the OPNsense configuration XML file (`/conf/config.xml`). While this file has restricted permissions (0600 root:wheel), it creates several risks:

1. **Backup Exposure:** Config backups may be stored insecurely
2. **Remote Backup:** Backups sent to remote systems
3. **HA Sync:** Config replication to secondary firewall
4. **Admin Access:** Any admin can view raw config
5. **Config History:** OPNsense maintains config history

**Code:**
```xml
<authPass type="TextField"/>
<!-- No encryption, no masking, just TextField -->
```

**Current Storage in /conf/config.xml:**
```xml
<connection uuid="12345">
    <name>myproxy</name>
    <authUser>admin</authUser>
    <authPass>MySecretPassword</authPass>  <!-- PLAINTEXT! -->
</connection>
```

**Impact:**
- Backup compromise reveals all proxy credentials
- Config export/import exposes passwords
- Web UI shows passwords in forms (mitigated by input type="password" but API returns them)
- XML-RPC HA sync transmits plaintext passwords

**Recommendations:**

1. **Immediate Fix (Password Encryption):**
   Study how other OPNsense plugins handle credentials:
   ```php
   // Example from os-wireguard or os-openvpn:
   use OPNsense\Core\Config;
   $config = Config::getInstance()->object();

   // When saving:
   $encrypted = $config->encrypt($plaintext_password);

   // When reading:
   $plaintext = $config->decrypt($encrypted_password);
   ```

2. **Update XML Model:**
   ```xml
   <authPass type="TextField">
       <Encryption>1</Encryption>  <!-- Enable encryption -->
   </authPass>
   ```

3. **API Filtering:**
   Ensure API responses don't return decrypted passwords:
   ```php
   // In ConnectionController:
   public function searchItemAction() {
       $result = parent::searchItemBase(...);
       foreach ($result['rows'] as &$row) {
           if (isset($row['authPass'])) {
               $row['authPass'] = '***';  // Mask in API response
           }
       }
       return $result;
   }
   ```

**OPNsense Plugin Requirement:**
Official plugins MUST encrypt sensitive credentials in config.xml. This is a mandatory requirement for plugin acceptance.

---

## High Issues

### HIGH-1: Credentials in Shell Config Files

**File:** `src/opnsense/scripts/OPNsense/ProxyGateway/setup.sh:150-165`

**Issue:**
Connection configuration files written to `/var/run/proxygateway/<name>.conf` contain proxy URLs with embedded credentials in plaintext. These files are shell-sourceable and persist while the connection is active.

**Code:**
```bash
# setup.sh creates:
cat > "/var/run/proxygateway/${NAME}.conf" <<EOF
NAME="${NAME}"
PROXY_TYPE="${PROXY_TYPE}"
PROXY_URL="${PROXY_URL}"  # Contains: socks5://user:pass@host:port
TUN_LOCAL="${TUN_LOCAL}"
# ... etc ...
EOF
```

**Impact:**
- Configuration files readable by root and potentially other processes
- May be included in debug dumps or system snapshots
- Accidental `cat *.conf` in logs reveals credentials
- Source of credentials for other attack vectors

**Recommendations:**

1. **Separate Credentials from Config:**
   ```bash
   # Write two files:
   # 1. Public config (no credentials)
   cat > "/var/run/proxygateway/${NAME}.conf" <<EOF
   NAME="${NAME}"
   PROXY_TYPE="${PROXY_TYPE}"
   PROXY_SERVER="${PROXY_ADDR}"
   PROXY_PORT="${PROXY_PORT}"
   # ... other non-sensitive data ...
   EOF

   # 2. Credentials file (restricted permissions)
   cat > "/var/run/proxygateway/${NAME}.auth" <<EOF
   AUTH_USER="${AUTH_USER}"
   AUTH_PASS="${AUTH_PASS}"
   EOF
   chmod 600 "/var/run/proxygateway/${NAME}.auth"
   ```

2. **Don't Store Credentials at All:**
   - Only store PID, interface name, and non-sensitive metadata
   - Retrieve credentials from model when needed for operations

3. **Ensure Proper Permissions:**
   ```bash
   chmod 600 "/var/run/proxygateway/${NAME}.conf"
   chown root:wheel "/var/run/proxygateway/${NAME}.conf"
   ```

---

### HIGH-2: Insecure Temporary File Handling

**File:** Multiple (setup.sh, teardown.sh, gateway registration)

**Issue:**
Gateway registration uses predictable temporary file paths in `/tmp/pgw_<name>_router`. The `/tmp` directory is world-writable and subject to:
- Symlink attacks
- Race conditions
- Predictable naming exploitation

**Code:**
```bash
# In setup.sh:
echo "${TUN_PEER}" > "/tmp/pgw_${NAME}_router"
```

**Impact:**
- Attacker can create symlink `/tmp/pgw_myconn_router` → `/etc/passwd`
- setup.sh would then write IP address to /etc/passwd
- Denial of service by pre-creating files
- Information disclosure about active proxies

**Recommendations:**

1. **Use Secure Directory:**
   ```bash
   # OPNsense uses /var/run which is cleaned on boot and restricted:
   echo "${TUN_PEER}" > "/var/run/proxygateway/gateway_${NAME}_router"

   # Or use dedicated directory:
   mkdir -p /var/db/proxygateway/gateways
   chmod 755 /var/db/proxygateway/gateways
   echo "${TUN_PEER}" > "/var/db/proxygateway/gateways/${NAME}"
   ```

2. **Atomic File Creation:**
   ```bash
   # Use noclobber to prevent overwriting:
   set -C
   echo "${TUN_PEER}" > "/var/run/pgw_${NAME}_router" || exit 1
   set +C
   ```

3. **Check Before Writing:**
   ```bash
   if [ -e "/tmp/pgw_${NAME}_router" ] && [ ! -f "/tmp/pgw_${NAME}_router" ]; then
       log_error "Security: /tmp/pgw_${NAME}_router is not a regular file!"
       exit 1
   fi
   ```

**Note:** OPNsense may already handle gateway registration via a different mechanism. Verify if `/tmp/pgw_*` files are actually used or if this is legacy code.

---

### HIGH-3: Potential Log File Credential Exposure

**File:** Multiple (setup.sh, tun2socks output, reconfigure.py)

**Issue:**
When log level is set to DEBUG, or when tun2socks encounters errors, credentials may be logged to:
- `/var/log/proxygateway/<name>.log`
- `/var/log/proxygateway/reconfigure.log`
- System syslog

**Examples:**

1. **tun2socks Debug Output:**
   ```bash
   # tun2socks may log:
   [DEBUG] Connecting to proxy: socks5://admin:password@proxy.example.com:1080
   ```

2. **Error Messages:**
   ```bash
   # Shell error messages may include full command:
   /bin/sh: /usr/local/bin/tun2socks -proxy socks5://user:pass@host:1080: command failed
   ```

3. **Reconfigure Log:**
   ```
   2026-02-23T10:00:00Z [INFO ] [reconfigure] [myconn] Calling: setup.sh myconn socks5 1.2.3.4 1080 --auth-user admin --auth-pass ***
   ```
   While the code redacts `--auth-pass` in logs, shell trace (set -x) or error messages may still expose it.

**Recommendations:**

1. **Credential Redaction in Logging:**
   Already partially implemented in reconfigure.py, but ensure:
   ```python
   # In reconfigure.py:
   def redact_password(cmd_parts):
       redacted = []
       skip_next = False
       for part in cmd_parts:
           if skip_next:
               redacted.append('***')
               skip_next = False
           elif part == '--auth-pass':
               redacted.append(part)
               skip_next = True
           else:
               redacted.append(part)
       return redacted
   ```

2. **tun2socks Log Level:**
   Ensure tun2socks is NOT run with `-loglevel debug` in production:
   ```bash
   /usr/local/bin/tun2socks \
       -device "${TUN_DEVICE}" \
       -proxy "${PROXY_URL}" \
       -loglevel warning \  # Not debug!
       >> "${LOG_FILE}" 2>&1 &
   ```

3. **Log File Permissions:**
   ```bash
   touch "${LOG_FILE}"
   chmod 600 "${LOG_FILE}"
   chown root:wheel "${LOG_FILE}"
   ```

4. **Log Rotation Security:**
   Ensure newsyslog config preserves permissions:
   ```
   # In src/etc/newsyslog.conf.d/proxygateway.conf:
   /var/log/proxygateway/*.log root:wheel 600 7 * @T00 JC
   ```

---

## Medium Issues

### MEDIUM-1: Insufficient Input Validation on Proxy URL Components

**File:** `src/opnsense/mvc/app/models/OPNsense/ProxyGateway/ProxyGateway.xml:212-219`

**Issue:**
The `proxyServer` field uses `TextField` with basic regex validation, but doesn't strictly validate against injection attacks or malformed inputs that could break shell commands.

**Current Validation:**
```xml
<proxyServer type="TextField">
    <Required>Y</Required>
    <ValidationMessage>Please enter a valid hostname or IP address</ValidationMessage>
    <Mask>/^[a-zA-Z0-9.-]+$/</Mask>
</proxyServer>
```

**Concerns:**
1. **Hostname Validation:** Allows `-` at start (invalid DNS name)
2. **No FQDN Length Check:** DNS names limited to 253 characters
3. **No IP Address Validation:** Should validate IPv4/IPv6 format
4. **Username/Password Fields:** TextField allows any UTF-8, could include shell metacharacters

**Potential Attack:**
While `setup.sh` uses shell parameters (not eval), there are still edge cases:
```bash
# Malicious username:
AUTH_USER='admin"; touch /tmp/pwned; echo "'

# In setup.sh variable substitution:
PROXY_URL="${PROXY_TYPE}://${AUTH_USER}:${AUTH_PASS}@${PROXY_ADDR}:${PROXY_PORT}"
# Results in: socks5://admin"; touch /tmp/pwned; echo ":password@proxy:1080
```

**Recommendations:**

1. **Stricter Field Validation:**
   ```xml
   <proxyServer type="TextField">
       <Required>Y</Required>
       <ValidationMessage>Enter valid hostname or IP</ValidationMessage>
       <Mask>/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$|^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$|^\[(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\]$/i</Mask>
   </proxyServer>

   <authUser type="TextField">
       <Mask>/^[a-zA-Z0-9@._-]{1,64}$/</Mask>
   </authUser>

   <authPass type="TextField">
       <!-- Passwords can contain special chars, but limit to printable ASCII -->
       <Mask>/^[ -~]{1,128}$/</Mask>
   </authPass>
   ```

2. **Server-Side Validation:**
   ```php
   // In ProxyGateway.php model:
   public function validateProxyServer($value) {
       // Validate as hostname OR IPv4 OR IPv6
       if (!filter_var($value, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4 | FILTER_FLAG_IPV6)) {
           if (!preg_match('/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i', $value)) {
               return ['Invalid hostname or IP address'];
           }
       }
       return [];
   }
   ```

3. **Shell Parameter Quoting:**
   Ensure all variable expansions in shell scripts use proper quoting:
   ```bash
   # Always quote variables:
   PROXY_URL="${PROXY_TYPE}://${AUTH_USER}:${AUTH_PASS}@${PROXY_ADDR}:${PROXY_PORT}"

   # When passing to commands, use -- separator:
   /usr/local/bin/tun2socks -device "${TUN_DEVICE}" -proxy "${PROXY_URL}" --
   ```

---

### MEDIUM-2: Health Check Information Disclosure

**File:** `src/opnsense/mvc/app/controllers/OPNsense/ProxyGateway/Api/DiagnosticsController.php:50-80`

**Issue:**
The diagnostics API endpoints return detailed health check information including:
- Proxy server latency measurements
- Timestamp of last successful connection
- Connection state transitions
- Probe target URLs

This information could be used for:
- Traffic analysis (when is proxy being used)
- Performance profiling
- Identifying proxy usage patterns

**API Response Example:**
```json
{
    "name": "myproxy",
    "status": "up",
    "health": {
        "status": "up",
        "latency_ms": "42",
        "timestamp": "1708698000",
        "probe": "http://1.1.1.1/",
        "last_success": "2026-02-23T10:30:00Z"
    }
}
```

**Impact:**
- Low-privileged users with API access can monitor proxy usage
- Time-based correlation attacks
- Service enumeration

**Recommendations:**

1. **Require Higher Privilege:**
   ```php
   // In DiagnosticsController.php:
   /**
    * @Privilege health-monitoring
    */
   public function getStatusAction() {
       // Existing code
   }
   ```

2. **Limit Information Returned:**
   ```php
   // For non-admin users, return simplified status:
   if (!$this->isAdminUser()) {
       foreach ($result as &$conn) {
           unset($conn['health']['latency_ms']);
           unset($conn['health']['timestamp']);
           unset($conn['health']['probe']);
           // Only return: up/down/degraded
       }
   }
   ```

3. **Rate Limit Health Checks:**
   ```php
   // In testConnectionAction:
   $cache_key = "healthcheck_ratelimit_{$name}";
   if ($this->cache->has($cache_key)) {
       return ['result' => 'rate_limited', 'message' => 'Try again in 10 seconds'];
   }
   $this->cache->set($cache_key, true, 10);  // 10 second cooldown
   ```

---

### MEDIUM-3: No Rate Limiting on API Endpoints

**File:** All API controllers

**Issue:**
API endpoints have no rate limiting, allowing:
- Brute force testing of connection names
- Resource exhaustion via repeated health checks
- DOS via rapid reconfigure calls

**Vulnerable Endpoints:**
```php
POST /api/proxygateway/diagnostics/testConnection  // Triggers curl probe
POST /api/proxygateway/service/reconfigure         // Heavy operation
GET  /api/proxygateway/diagnostics/getLogs         // File I/O
```

**Recommendations:**

1. **Implement API Rate Limiting:**
   OPNsense may provide built-in rate limiting. If not, implement:
   ```php
   // In base API controller or via middleware:
   protected function checkRateLimit($action, $limit_per_minute = 10) {
       $client_ip = $_SERVER['REMOTE_ADDR'];
       $cache_key = "ratelimit_{$action}_{$client_ip}";

       $count = (int)$this->cache->get($cache_key, 0);
       if ($count >= $limit_per_minute) {
           $this->response->setStatusCode(429, 'Too Many Requests');
           return $this->response->setJsonContent(['error' => 'Rate limit exceeded']);
       }

       $this->cache->set($cache_key, $count + 1, 60);
       return null;
   }
   ```

2. **Cooldown for Heavy Operations:**
   ```php
   public function reconfigureAction() {
       $limit = $this->checkRateLimit('reconfigure', 2);  // Max 2/minute
       if ($limit !== null) return $limit;

       // Existing reconfigure logic
   }
   ```

3. **Throttle Health Checks:**
   ```php
   public function testConnectionAction() {
       $limit = $this->checkRateLimit('healthcheck', 6);  // Max 6/minute
       if ($limit !== null) return $limit;

       // Existing health check logic
   }
   ```

---

### MEDIUM-4: Credentials May Appear in System Logs

**File:** Multiple (syslog integration, configd logs)

**Issue:**
OPNsense's configd daemon logs all commands executed. If credentials are passed as arguments, they may appear in:
- `/var/log/configd.log`
- System syslog
- Centralized log aggregation systems

**Example Log Entry:**
```
2026-02-23T10:00:00 configd: executing action proxygateway setup myconn socks5 1.2.3.4 1080 --auth-user admin --auth-pass secret123
```

**Impact:**
- Syslog servers store credentials
- Log analysis tools expose passwords
- SIEM systems index plaintext credentials

**Recommendations:**

1. **Verify configd Logging Behavior:**
   Test what actually gets logged:
   ```bash
   tail -f /var/log/configd.log &
   configctl proxygateway setup testconn socks5 1.2.3.4 1080 --auth-user admin --auth-pass test123
   ```

2. **If Logged, Change Command Structure:**
   Instead of passing credentials as arguments:
   ```bash
   # Current (bad):
   configctl proxygateway setup myconn socks5 1.2.3.4 1080 --auth-user admin --auth-pass secret

   # Better:
   configctl proxygateway setup myconn socks5 1.2.3.4 1080 --auth-from-config
   # setup.sh then reads credentials from desired.json or encrypted config
   ```

3. **Configd Action Message Redaction:**
   In `actions_proxygateway.conf`, ensure message doesn't include full parameters:
   ```conf
   [setup]
   command: /bin/sh /usr/local/opnsense/scripts/OPNsense/ProxyGateway/setup.sh
   parameters: %s
   type: script
   message: setup proxy gateway connection [redacted]  # Don't echo parameters
   ```

---

## Low Issues

### LOW-1: Connection Names Disclosed in Interface Groups

**File:** `src/etc/inc/plugins.inc.d/proxygateway.inc:40-45`

**Issue:**
All proxy gateway interfaces are added to the `proxygateway` interface group, which may disclose connection names to lower-privileged users who can view interfaces but not manage connections.

**Impact:**
- Information disclosure: attacker learns proxy connection names
- Minor privacy concern: naming conventions may reveal usage patterns

**Recommendations:**

1. **Use Generic Interface Names:**
   Instead of `pgw_<name>`, use `pgw0`, `pgw1`, `pgw2`:
   ```php
   // Assign numeric IDs instead of names for interface naming
   $iface_id = $this->getNextInterfaceId();
   $interface_name = "pgw{$iface_id}";
   ```

2. **Restrict Interface Group Visibility:**
   Ensure OPNsense ACLs prevent non-admin users from viewing interface groups.

3. **Accept as Low Risk:**
   This is minor information disclosure and may be acceptable for usability.

---

### LOW-2: No Certificate Pinning for TLS Proxies

**File:** `src/opnsense/scripts/OPNsense/ProxyGateway/setup.sh:120-130`

**Issue:**
When using `socks5tls` or `https` proxy types, tun2socks establishes TLS connections but doesn't support certificate pinning. This relies on the system's CA trust store.

**Impact:**
- Man-in-the-middle attacks possible if system CA store is compromised
- Attacker with CA access can intercept proxy connections
- Lower risk in typical home/SMB scenarios

**Recommendations:**

1. **Check tun2socks TLS Options:**
   Review tun2socks documentation for:
   - Certificate pinning support
   - Custom CA bundle
   - TLS version enforcement

2. **Add Configuration Options:**
   ```xml
   <tlsVerify type="BooleanField">
       <default>1</default>
   </tlsVerify>
   <tlsCaCert type="CertificateField"/>
   <tlsServerName type="TextField"/>  <!-- SNI override -->
   ```

3. **Document Limitation:**
   In user documentation, note that TLS proxies rely on system trust store.

**Priority:** Low - Implement only if tun2socks supports it.

---

### LOW-3: Hardcoded Default Health Check Target

**File:** `src/opnsense/scripts/OPNsense/ProxyGateway/healthcheck.sh:15-20`

**Issue:**
The default health check target is `http://1.1.1.1/` (Cloudflare). This means:
- Cloudflare can observe health check traffic from all users who don't customize the target
- Timing correlation: Cloudflare knows when proxies are being tested
- Privacy concern: Usage patterns leaked to third party

**Impact:**
- Minor privacy disclosure
- Cloudflare DDoS protection may block health checks
- Single point of failure for health monitoring

**Recommendations:**

1. **Diversify Default Targets:**
   ```bash
   # Use different targets based on connection name hash:
   TARGETS=(
       "http://1.1.1.1/"
       "http://8.8.8.8/"
       "http://9.9.9.9/"
       "http://208.67.222.222/"
   )
   HASH=$(echo -n "$NAME" | md5 | cut -c1-2)
   INDEX=$((0x$HASH % ${#TARGETS[@]}))
   DEFAULT_TARGET="${TARGETS[$INDEX]}"
   ```

2. **Allow Custom Target in Config:**
   Already implemented! Users can set `healthCheckTarget` in connection config.

3. **Document Privacy Implications:**
   In user guide, explain that health check target receives periodic requests and recommend using own monitoring endpoint for privacy.

**Priority:** Low - Document and accept.

---

## OPNsense Official Plugin Requirements Review

### Requirements Checklist

Based on OPNsense plugin development guidelines:

| Requirement | Status | Notes |
|-------------|--------|-------|
| **License Compatibility** | ✅ PASS | BSD-2-Clause for plugin, MIT for tun2socks |
| **Code Quality** | ⚠️ PARTIAL | Good structure, but security issues present |
| **MVC Architecture** | ✅ PASS | Proper use of OPNsense MVC framework |
| **configd Integration** | ✅ PASS | Correct action definitions and usage |
| **Service Management** | ✅ PASS | Proper rc.d script and service registration |
| **API Design** | ✅ PASS | RESTful API with proper controllers |
| **UI/UX** | ✅ PASS | Volt templates, forms, diagnostics page |
| **Documentation** | ⚠️ PARTIAL | Good README and design docs, needs security docs |
| **Security** | ❌ FAIL | Critical credential handling issues |
| **Error Handling** | ⚠️ PARTIAL | Basic error handling present, needs improvement |
| **Logging** | ✅ PASS | Structured logging implemented |
| **ACL/Permissions** | ⚠️ PARTIAL | Basic ACL defined, needs privilege separation |
| **HA Sync Support** | ✅ PASS | XML-RPC sync metadata defined |
| **Upgrade Path** | ⚠️ NEEDS TESTING | No migration scripts visible |
| **Dependencies** | ✅ PASS | Clean dependency on tun2socks binary |
| **FreeBSD Compatibility** | ✅ PASS | Proper use of FreeBSD tun devices |
| **Plugin Hooks** | ✅ PASS | Correct implementation of all hooks |
| **Firewall Integration** | ✅ PASS | Proper rule generation via plugins.inc.d |
| **Gateway Integration** | ✅ PASS | Proper gateway registration mechanism |

### Critical Blockers for Official Plugin Acceptance

1. **MUST FIX - Credential Encryption:**
   - Implement encrypted storage of passwords in config.xml
   - Remove plaintext credential files
   - Use secure IPC for credential passing

2. **MUST FIX - Process Argument Exposure:**
   - Use environment variables or file descriptors for credentials
   - Never pass passwords as command-line arguments

3. **MUST FIX - File Permissions:**
   - Ensure all credential-containing files are mode 0600
   - Use /var/run (not /tmp) for temporary files

4. **SHOULD FIX - Input Validation:**
   - Strengthen hostname/IP validation
   - Add length limits on all text fields
   - Server-side validation in addition to XML masks

5. **SHOULD FIX - API Rate Limiting:**
   - Implement rate limiting on expensive operations
   - Prevent resource exhaustion attacks

### Additional Recommendations for Official Plugin

1. **Code Review:**
   - Submit to OPNsense plugin review team
   - Address all feedback before acceptance

2. **Testing:**
   - Automated tests for setup/teardown
   - Integration tests with actual proxy servers
   - Stress testing (multiple connections, rapid changes)
   - HA failover testing

3. **Documentation:**
   - Security considerations section
   - Backup/restore implications
   - Upgrade procedure
   - Troubleshooting guide

4. **Internationalization:**
   - Add translation support (gettext)
   - Translate UI strings

5. **Performance:**
   - Benchmark tun2socks overhead
   - Document performance characteristics
   - Resource limits guidance

---

## Recommended Implementation Priority

### Phase 1: Critical Security Fixes (Required before any production use)

1. **Encrypt passwords in config.xml** (CRITICAL-3)
   - Research OPNsense config encryption API
   - Update ProxyGateway.xml model
   - Add encryption/decryption to ServiceController

2. **Fix process argument exposure** (CRITICAL-2)
   - Change setup.sh to receive credentials via environment
   - Update reconfigure.py to pass via environment
   - Test with ps/procfs monitoring

3. **Secure desired.json** (CRITICAL-1)
   - Change file permissions to 0600
   - Or better: eliminate file, use configd socket
   - Verify no other world-readable credential files

4. **Fix shell config credential exposure** (HIGH-1)
   - Separate credentials from .conf files
   - Use .auth files with 0600 permissions
   - Update status.py to read from both files

### Phase 2: High-Priority Fixes

5. **Secure temporary file handling** (HIGH-2)
   - Move gateway files from /tmp to /var/run
   - Add atomic file creation
   - Test for race conditions

6. **Log credential redaction** (HIGH-3)
   - Audit all log output paths
   - Ensure tun2socks logs are restricted
   - Test with debug logging enabled

### Phase 3: Medium-Priority Improvements

7. **Input validation** (MEDIUM-1)
   - Strengthen regex masks
   - Add server-side validation
   - Fuzz test input fields

8. **API rate limiting** (MEDIUM-3)
   - Implement rate limiter
   - Add cooldowns for heavy operations
   - Test DoS scenarios

9. **Reduce health check disclosure** (MEDIUM-2)
   - Limit information in API responses
   - Require higher privilege for detailed status
   - Add rate limits

### Phase 4: Documentation and Polish

10. **Security documentation**
    - Document credential handling
    - Backup security implications
    - Threat model

11. **OPNsense plugin submission prep**
    - Address all blockers
    - Create test suite
    - Internationalization

---

## Testing Recommendations

### Security Testing Checklist

- [ ] **Credential Exposure Tests:**
  - [ ] Check all files in /var/run/proxygateway/ for plaintext passwords
  - [ ] Monitor process list during connection setup
  - [ ] Grep all log files for password patterns
  - [ ] Export config.xml and verify passwords encrypted
  - [ ] Test backup/restore doesn't expose passwords

- [ ] **Input Validation Tests:**
  - [ ] Fuzz test all text fields with special characters
  - [ ] Test SQL injection patterns (though using XML, not SQL)
  - [ ] Test command injection in proxy server field
  - [ ] Test path traversal in connection names
  - [ ] Test XXE in XML import (if applicable)

- [ ] **Access Control Tests:**
  - [ ] Verify ACLs prevent unauthorized access
  - [ ] Test with non-admin user accounts
  - [ ] Test API authentication bypass attempts
  - [ ] Test privilege escalation via API

- [ ] **Resource Exhaustion Tests:**
  - [ ] Rapid connection creation/deletion
  - [ ] Rapid health check triggering
  - [ ] Large number of simultaneous connections
  - [ ] Memory leak testing (long-running connections)

- [ ] **File Permission Tests:**
  - [ ] Check all created files have correct permissions
  - [ ] Verify no world-readable sensitive files
  - [ ] Test symbolic link attacks in /tmp
  - [ ] Test directory traversal in file paths

### Functional Testing

- [ ] **Connection Lifecycle:**
  - [ ] Create, enable, disable, delete connections
  - [ ] Verify tun devices created/destroyed
  - [ ] Verify processes started/stopped
  - [ ] Verify gateway registration/deregistration

- [ ] **Proxy Types:**
  - [ ] Test SOCKS5 proxy (with/without auth)
  - [ ] Test SOCKS5+TLS proxy
  - [ ] Test HTTP CONNECT proxy
  - [ ] Test HTTPS CONNECT proxy

- [ ] **Edge Cases:**
  - [ ] Connection with same name as deleted connection
  - [ ] Rapid enable/disable toggling
  - [ ] Reconfigure while health check running
  - [ ] System reboot with active connections
  - [ ] WAN IP change during active connection

- [ ] **Integration:**
  - [ ] Firewall rule routing to proxy gateway
  - [ ] Gateway group failover
  - [ ] NAT rule generation
  - [ ] DNS handling through tunnel
  - [ ] Kill switch functionality

---

## Conclusion

The os-proxygateway plugin demonstrates **excellent architecture and OPNsense integration** but has **critical security vulnerabilities** that must be addressed before production use or submission to the official OPNsense plugin repository.

### Summary of Findings

- **3 Critical Issues:** All related to credential handling
- **3 High Issues:** Credential exposure and file security
- **4 Medium Issues:** Validation, information disclosure, rate limiting
- **3 Low Issues:** Minor privacy and security concerns

### Next Steps

1. **Immediate:** Fix Critical-1, Critical-2, Critical-3 (credential security)
2. **Before Production:** Fix all HIGH issues
3. **Before Plugin Submission:** Fix all MEDIUM issues, document all LOW issues
4. **Long-term:** Implement comprehensive test suite

### Estimated Effort

- **Critical Fixes:** 2-3 days development + 1 day testing
- **High Fixes:** 1-2 days development + 1 day testing
- **Medium Fixes:** 2-3 days development + 1 day testing
- **Documentation:** 1-2 days
- **Total:** ~2 weeks for complete security hardening

### Plugin Quality Assessment

**Architecture:** ⭐⭐⭐⭐⭐ (5/5) - Excellent OPNsense integration
**Functionality:** ⭐⭐⭐⭐⭐ (5/5) - Feature-complete and well-designed
**Code Quality:** ⭐⭐⭐⭐ (4/5) - Good structure, minor improvements needed
**Security:** ⭐⭐ (2/5) - Critical issues must be fixed
**Documentation:** ⭐⭐⭐⭐ (4/5) - Good docs, needs security section

**Overall:** ⭐⭐⭐ (3/5) - **Solid foundation, security fixes required**

---

**Reviewed by:** Security Review Agent
**Date:** 2026-02-23
**Version:** os-proxygateway current main branch
