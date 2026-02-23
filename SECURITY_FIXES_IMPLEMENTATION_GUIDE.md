# Security Fixes Implementation Guide

This document provides step-by-step instructions for implementing the remaining security improvements identified in the security review.

## Completed Fixes

✅ **CRITICAL-1**: Fixed plaintext passwords in desired.json
- Added `chmod 0600` and `chown root` to ServiceController.php
- File now has owner-only read/write permissions

✅ **CRITICAL-2**: Fixed passwords visible in process arguments
- Modified reconfigure.py to pass credentials via `PROXY_AUTH_PASS` environment variable
- Modified setup.sh to accept `--auth-pass-env` flag
- Passwords no longer appear in `ps` output

✅ **HIGH-1**: Fixed credentials in shell config files
- Added `chmod 600` and `chown root:wheel` to .conf files in setup.sh
- Secured .tundev files with 600 permissions

✅ **HIGH-2**: Fixed insecure temporary file handling
- Changed gateway router files from `/tmp/pgw_*` to `/var/run/pgw_*`
- Updated teardown.sh to clean up both old and new locations for backward compatibility

✅ **MEDIUM-1**: Improved input validation
- Enhanced proxyServer regex to properly validate hostnames and IPv4/IPv6 addresses
- Added length and character restrictions to authUser (1-64 chars, safe characters only)
- Added length and character restrictions to authPass (1-128 chars, printable ASCII only)

## Remaining Critical Fix: Config.xml Encryption

### CRITICAL-3: No Encryption of Credentials in Configuration

**Status:** ⚠️ **REQUIRES RESEARCH AND IMPLEMENTATION**

**Problem:** Passwords are stored in plaintext in `/conf/config.xml`, which is backed up, replicated to HA peers, and exported during configuration backups.

**Solution Strategy:**

#### Step 1: Research OPNsense Credential Encryption

OPNsense provides credential encryption mechanisms used by other plugins. Research the following:

1. **Check existing plugins:**
   ```bash
   # On OPNsense system, examine VPN plugins:
   cd /usr/local/opnsense/mvc/app/models/OPNsense
   grep -r "encrypt\|decrypt" OpenVPN/ WireGuard/ IPsec/
   ```

2. **Check for encryption field attribute:**
   Look for XML attributes like:
   - `<Encryption>1</Encryption>`
   - `<encrypted>`
   - Usage of `Config::encrypt()` / `Config::decrypt()`

3. **Review OPNsense documentation:**
   - https://docs.opnsense.org/development/
   - Search for "credential encryption", "password encryption", "config encryption"

#### Step 2: Implementation Options

**Option A: Use OPNsense Built-in Encryption (Recommended)**

If OPNsense provides a field-level encryption mechanism:

1. Update `ProxyGateway.xml`:
   ```xml
   <authPass type="EncryptedTextField">
       <Required>N</Required>
       <Encryption>aes256</Encryption>
   </authPass>
   ```

2. Update ServiceController.php to decrypt when building desired.json:
   ```php
   use OPNsense\Core\Config;

   // In reconfigureAction():
   foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
       $authPass = (string)$conn->authPass;
       if (!empty($authPass) && $this->isEncrypted($authPass)) {
           $authPass = Config::getInstance()->decrypt($authPass);
       }

       $conn_data = [
           // ...
           'authPass' => $authPass,  // Now decrypted for passing to backend
       ];
   }
   ```

3. Test encryption/decryption cycle:
   - Save connection with password → verify config.xml shows encrypted value
   - Retrieve connection → verify API returns masked value
   - Start connection → verify tun2socks receives plaintext password

**Option B: Implement Custom Encryption**

If OPNsense doesn't provide built-in field encryption:

1. Generate a machine-specific key on installation:
   ```bash
   # In +POST_INSTALL script:
   if [ ! -f /var/db/proxygateway/encryption.key ]; then
       mkdir -p /var/db/proxygateway
       openssl rand -base64 32 > /var/db/proxygateway/encryption.key
       chmod 600 /var/db/proxygateway/encryption.key
       chown root:wheel /var/db/proxygateway/encryption.key
   fi
   ```

2. Implement encryption/decryption in ProxyGateway.php model:
   ```php
   class ProxyGateway extends BaseModel
   {
       private const KEY_FILE = '/var/db/proxygateway/encryption.key';

       private function encryptPassword($plaintext) {
           if (empty($plaintext)) return '';
           $key = trim(file_get_contents(self::KEY_FILE));
           $iv = openssl_random_pseudo_bytes(16);
           $encrypted = openssl_encrypt($plaintext, 'AES-256-CBC', $key, 0, $iv);
           return base64_encode($iv . $encrypted);
       }

       private function decryptPassword($ciphertext) {
           if (empty($ciphertext)) return '';
           $key = trim(file_get_contents(self::KEY_FILE));
           $data = base64_decode($ciphertext);
           $iv = substr($data, 0, 16);
           $encrypted = substr($data, 16);
           return openssl_decrypt($encrypted, 'AES-256-CBC', $key, 0, $iv);
       }

       public function setNodes($data, $set_empty = true) {
           // Encrypt authPass before saving
           if (isset($data['connections']['connection'])) {
               foreach ($data['connections']['connection'] as &$conn) {
                   if (isset($conn['authPass']) && !$this->isEncrypted($conn['authPass'])) {
                       $conn['authPass'] = $this->encryptPassword($conn['authPass']);
                   }
               }
           }
           return parent::setNodes($data, $set_empty);
       }

       private function isEncrypted($value) {
           // Check if value is base64 and has proper length for encrypted data
           if (empty($value)) return false;
           $decoded = @base64_decode($value, true);
           return $decoded !== false && strlen($decoded) >= 16;
       }
   }
   ```

**Option C: Use System Keyring (Most Secure)**

Use FreeBSD's keyring or a secret management system:

1. Store passwords in a separate encrypted store
2. Store only references/IDs in config.xml
3. Retrieve passwords at runtime from secure store

This is more complex but provides better security.

#### Step 3: Migration Path

After implementing encryption, existing plaintext passwords need to be migrated:

1. Add migration script:
   ```php
   // In ProxyGateway.php or separate migration script:
   public function migratePasswordEncryption() {
       $changed = false;
       foreach ($this->connections->connection->iterateItems() as $uuid => $conn) {
           $authPass = (string)$conn->authPass;
           if (!empty($authPass) && !$this->isEncrypted($authPass)) {
               $conn->authPass = $this->encryptPassword($authPass);
               $changed = true;
           }
       }
       if ($changed) {
           $this->serializeToConfig();
       }
       return $changed;
   }
   ```

2. Call migration on plugin upgrade or first access

#### Step 4: API Response Filtering

Ensure API never returns decrypted passwords:

```php
// In ConnectionController.php searchItemAction:
public function searchItemAction()
{
    $result = parent::searchItemBase(...);

    // Mask passwords in API response
    foreach ($result['rows'] as &$row) {
        if (isset($row['authPass']) && !empty($row['authPass'])) {
            $row['authPass'] = '********';
        }
    }

    return $result;
}

// In getItemAction:
public function getItemAction($uuid = null)
{
    $result = parent::getItemAction($uuid);

    // For editing: return a placeholder, not the actual password
    if (isset($result['connection']['authPass']) && !empty($result['connection']['authPass'])) {
        $result['connection']['authPass'] = '';  // Empty field, user must re-enter to change
    }

    return $result;
}
```

#### Step 5: Testing Checklist

- [ ] Create new connection with password → verify encrypted in config.xml
- [ ] Edit connection, change password → verify new password encrypted
- [ ] View connection in UI → verify password not shown (empty or masked)
- [ ] Export config.xml → verify password encrypted in backup
- [ ] Start connection → verify tun2socks receives correct plaintext password
- [ ] Stop and restart connection → verify password still works
- [ ] Reboot system → verify passwords decrypt correctly on boot
- [ ] Test with connection that has no password → verify no encryption errors

## Remaining Medium Priority Fixes

### MEDIUM-2: Health Check Information Disclosure

**Recommendation:** Accept as low risk for now, document in security considerations.

If implementing, add to `DiagnosticsController.php`:

```php
private function filterSensitiveStatus($status, $isAdmin) {
    if ($isAdmin) {
        return $status;  // Admins see everything
    }

    // Non-admin users see limited information
    foreach ($status as &$conn) {
        unset($conn['health']['latency_ms']);
        unset($conn['health']['timestamp']);
        unset($conn['health']['probe']);
        // Keep only status: up/down/degraded
    }
    return $status;
}
```

### MEDIUM-3: No Rate Limiting on API Endpoints

**Recommendation:** Implement if submission to official plugins, otherwise defer.

**Implementation:**

1. Create rate limiter utility:
   ```php
   // In src/opnsense/mvc/app/library/OPNsense/ProxyGateway/RateLimiter.php
   class RateLimiter
   {
       private $cache;

       public function __construct() {
           $this->cache = new \OPNsense\Core\Cache\Cache();
       }

       public function checkLimit($key, $maxPerMinute, $windowSeconds = 60) {
           $cacheKey = "ratelimit_" . md5($key);
           $count = (int)$this->cache->get($cacheKey, 0);

           if ($count >= $maxPerMinute) {
               return false;  // Rate limit exceeded
           }

           $this->cache->set($cacheKey, $count + 1, $windowSeconds);
           return true;  // Within limit
       }
   }
   ```

2. Use in controllers:
   ```php
   // In DiagnosticsController.php:
   use OPNsense\ProxyGateway\RateLimiter;

   public function testConnectionAction() {
       $limiter = new RateLimiter();
       $clientKey = $_SERVER['REMOTE_ADDR'] . '_healthcheck';

       if (!$limiter->checkLimit($clientKey, 6, 60)) {
           return [
               'result' => 'error',
               'message' => 'Rate limit exceeded. Try again in 60 seconds.'
           ];
       }

       // Existing health check logic...
   }
   ```

### MEDIUM-4: Credentials in System Logs

**Status:** Mitigated by CRITICAL-2 fix (env variables)

**Additional Mitigation:**

1. Ensure configd doesn't log command parameters:
   - Check `/var/log/configd.log` after running a setup command
   - If parameters are logged, update `actions_proxygateway.conf` messages to not include %s

2. Review syslog configuration:
   ```bash
   # Ensure proxygateway logs don't go to remote syslog
   # Edit /etc/syslog.conf or /usr/local/etc/syslog.d/proxygateway.conf
   !proxygateway
   *.* /var/log/proxygateway/syslog.log
   ```

## Low Priority Recommendations

### LOW-1: Connection Names in Interface Groups

**Status:** Acceptable as-is. Document in user guide that connection names are visible in interface listings.

### LOW-2: Certificate Pinning for TLS Proxies

**Research needed:** Check if tun2socks supports:
- `--tls-cert-file` for custom CA bundle
- `--tls-insecure` flag (for testing only!)
- `--tls-server-name` for SNI override

If supported, add to model:
```xml
<tlsVerify type="BooleanField">
    <default>1</default>
</tlsVerify>
<tlsCaCert type="CertificateField"/>
<tlsServerName type="TextField"/>
```

### LOW-3: Hardcoded Health Check Target

**Status:** Already configurable via `healthCheckTarget` field. No code changes needed.

**Documentation improvement:** Add to user guide:

> **Privacy Note:** The default health check target is `http://1.1.1.1/` (Cloudflare's public DNS).
> This means Cloudflare may observe periodic health check requests from your proxy. For increased
> privacy, set a custom health check target to a server you control, or disable health checking.

## Additional Security Hardening (Optional)

### 1. Add Security Headers

If implementing a web interface beyond the standard OPNsense UI:

```php
// In controller constructors:
$this->response->setHeader('X-Frame-Options', 'SAMEORIGIN');
$this->response->setHeader('X-Content-Type-Options', 'nosniff');
$this->response->setHeader('X-XSS-Protection', '1; mode=block');
```

### 2. Audit Logging

Log all security-relevant events:

```php
// In ConnectionController.php:
use OPNsense\Core\Syslog;

public function addItemAction() {
    $result = parent::addItemAction();
    if ($result['result'] == 'saved') {
        Syslog::getInstance()->notice(
            "ProxyGateway: Connection '{$result['name']}' created by {$_SERVER['REMOTE_USER']}"
        );
    }
    return $result;
}

public function delItemAction($uuid) {
    $item = $this->model->getItem($uuid);
    $name = (string)$item->name;
    $result = parent::delItemAction($uuid);
    if ($result['result'] == 'deleted') {
        Syslog::getInstance()->warning(
            "ProxyGateway: Connection '{$name}' deleted by {$_SERVER['REMOTE_USER']}"
        );
    }
    return $result;
}
```

### 3. Credential Change Detection

Detect and log password changes:

```php
public function setItemAction($uuid) {
    $oldItem = $this->model->getItem($uuid);
    $oldPass = (string)$oldItem->authPass;

    $result = parent::setItemAction($uuid);

    if ($result['result'] == 'saved') {
        $newItem = $this->model->getItem($uuid);
        $newPass = (string)$newItem->authPass;

        if ($oldPass !== $newPass && !empty($newPass)) {
            Syslog::getInstance()->notice(
                "ProxyGateway: Password changed for connection '{$newItem->name}' by {$_SERVER['REMOTE_USER']}"
            );
        }
    }

    return $result;
}
```

### 4. Secure Log File Permissions

Ensure log rotation preserves permissions:

Update `src/etc/newsyslog.conf.d/proxygateway.conf`:

```
# Syntax: logfile [owner:group] mode count size when flags
/var/log/proxygateway/*.log root:wheel 600 7 * @T00 JC
/var/log/proxygateway/reconfigure.log root:wheel 600 30 * @T00 JC
```

### 5. Defense in Depth: Separate Credential Storage

For maximum security, consider separating credential storage:

1. Create encrypted credential vault:
   ```bash
   mkdir -p /var/db/proxygateway/vault
   chmod 700 /var/db/proxygateway/vault
   ```

2. Store credentials in separate files:
   ```php
   private function storeCredential($connName, $password) {
       $vaultFile = "/var/db/proxygateway/vault/{$connName}.enc";
       $encrypted = $this->encryptPassword($password);
       file_put_contents($vaultFile, $encrypted);
       chmod($vaultFile, 0600);
       chown($vaultFile, 'root');

       // Store only a reference in config.xml
       return "vault:{$connName}";
   }

   private function retrieveCredential($reference) {
       if (strpos($reference, 'vault:') !== 0) {
           return $reference;  // Legacy plaintext
       }
       $connName = substr($reference, 6);
       $vaultFile = "/var/db/proxygateway/vault/{$connName}.enc";
       if (!file_exists($vaultFile)) {
           return '';
       }
       $encrypted = file_get_contents($vaultFile);
       return $this->decryptPassword($encrypted);
   }
   ```

Benefits:
- Credentials never in config.xml (not in backups, exports, or HA sync)
- Easier to rotate encryption keys
- Can implement separate access controls

Drawbacks:
- More complex implementation
- Need to handle vault file cleanup when connection deleted
- Backups need to include vault directory

## Testing Security Fixes

### Security Test Suite

1. **Credential Exposure Test:**
   ```bash
   # After starting a connection, verify password not visible:
   ps auxww | grep -E 'setup\.sh|tun2socks|reconfigure' | grep -i password
   # Should find no results

   # Check file permissions:
   ls -la /var/run/proxygateway/
   # All files should be 600 or 750 (directory)

   # Check if password in config:
   grep -i "password\|authPass" /conf/config.xml
   # Should show encrypted or masked value, not plaintext
   ```

2. **File Permission Test:**
   ```bash
   # Verify sensitive files are not world-readable:
   find /var/run/proxygateway -type f -perm -o+r
   # Should return nothing

   find /var/log/proxygateway -type f -perm -o+r
   # Should return nothing
   ```

3. **Log Exposure Test:**
   ```bash
   # Check if credentials appear in logs:
   grep -ri "password.*=" /var/log/proxygateway/
   grep -ri "socks5://.*:.*@" /var/log/proxygateway/
   # Should find no plaintext passwords
   ```

4. **API Security Test:**
   ```bash
   # Test API doesn't return plaintext passwords:
   curl -k -u root:password https://opnsense.local/api/proxygateway/connection/searchItem
   # Response should not contain plaintext authPass values
   ```

5. **Process Isolation Test:**
   ```bash
   # Verify tun2socks runs as expected user:
   ps aux | grep tun2socks
   # Should run as root (for tun device access)

   # Verify no credential environment variables leaked:
   cat /proc/$(pgrep tun2socks)/environ | tr '\0' '\n' | grep -i pass
   # Should return nothing (env vars are cleared after spawn)
   ```

## Submission Checklist for OPNsense Official Plugins

Before submitting to OPNsense plugin repository:

- [ ] All CRITICAL issues fixed
- [ ] All HIGH issues fixed
- [ ] MEDIUM issues fixed or documented as acceptable
- [ ] Code follows OPNsense style guidelines
- [ ] Security review document updated
- [ ] User documentation includes security considerations
- [ ] Test suite passes
- [ ] Manual security tests pass
- [ ] HA sync tested (if applicable)
- [ ] Upgrade path tested (existing configs migrate cleanly)
- [ ] License compatibility verified (BSD-2-Clause + MIT)
- [ ] Dependencies documented and approved
- [ ] Performance tested (multiple connections, high throughput)
- [ ] FreeBSD compatibility verified on all supported versions
- [ ] No GPL dependencies (tun2socks v2.6.0+ is MIT)

## References

- [OPNsense Plugin Development Guide](https://docs.opnsense.org/development/)
- [OPNsense MVC Framework](https://docs.opnsense.org/development/backend.html)
- [FreeBSD Security Best Practices](https://www.freebsd.org/doc/en_US.ISO8859-1/books/handbook/security.html)
- [OWASP Secure Coding Practices](https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/)

---

**Last Updated:** 2026-02-23
**Next Review:** After implementing CRITICAL-3 (config.xml encryption)
