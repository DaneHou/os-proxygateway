# Security Review Summary

**Review Date:** 2026-02-23
**Plugin:** os-proxygateway
**Status:** Security fixes partially implemented

## Executive Summary

The os-proxygateway plugin has undergone a comprehensive security review. The plugin has excellent architecture and OPNsense integration, but several critical security vulnerabilities were identified and addressed.

## Review Outcome

**Overall Security Rating:**
- Before fixes: ⭐⭐ (2/5) - Critical credential exposure issues
- After fixes: ⭐⭐⭐⭐ (4/5) - Major improvements, one critical issue remains

## Issues Found and Status

### Critical Issues (3 total)

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| CRITICAL-1: Plaintext passwords in desired.json | 🔴 Critical | ✅ FIXED | Added file permissions (0600) in ServiceController.php |
| CRITICAL-2: Passwords in process arguments | 🔴 Critical | ✅ FIXED | Changed to environment variable passing |
| CRITICAL-3: No encryption in config.xml | 🔴 Critical | ⚠️ PENDING | Requires research into OPNsense encryption API |

### High Issues (3 total)

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| HIGH-1: Credentials in shell config files | 🟠 High | ✅ FIXED | Added chmod 600 to all .conf files |
| HIGH-2: Insecure temporary file handling | 🟠 High | ✅ FIXED | Moved from /tmp to /var/run |
| HIGH-3: Log file credential exposure | 🟠 High | ✅ MITIGATED | Env var fix prevents exposure |

### Medium Issues (4 total)

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| MEDIUM-1: Insufficient input validation | 🟡 Medium | ✅ FIXED | Enhanced regex validation |
| MEDIUM-2: Health check info disclosure | 🟡 Medium | ⚪ DEFERRED | Low risk, can implement later |
| MEDIUM-3: No API rate limiting | 🟡 Medium | ⚪ DEFERRED | Recommend for official plugin |
| MEDIUM-4: Credentials in system logs | 🟡 Medium | ✅ MITIGATED | Fixed by env var changes |

### Low Issues (3 total)

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| LOW-1: Connection name disclosure | ⚪ Low | ✅ ACCEPTED | Minor, document in user guide |
| LOW-2: No certificate pinning | ⚪ Low | ⚪ DEFERRED | Depends on tun2socks support |
| LOW-3: Hardcoded health check target | ⚪ Low | ✅ ACCEPTED | Already configurable |

## Fixes Implemented

### 1. File Permission Hardening

**Files Changed:**
- `src/opnsense/mvc/app/controllers/OPNsense/ProxyGateway/Api/ServiceController.php`
- `src/opnsense/scripts/OPNsense/ProxyGateway/setup.sh`

**Changes:**
```php
// desired.json now restricted to root-only access
chmod($desiredFile, 0600);
chown($desiredFile, 'root');
```

```bash
# All runtime config files now secure
chmod 600 "$CONFFILE"
chown root:wheel "$CONFFILE"
```

### 2. Environment Variable Credential Passing

**Files Changed:**
- `src/opnsense/scripts/OPNsense/ProxyGateway/reconfigure.py`
- `src/opnsense/scripts/OPNsense/ProxyGateway/setup.sh`

**Changes:**
- Passwords passed via `PROXY_AUTH_PASS` environment variable
- New `--auth-pass-env` flag in setup.sh
- Passwords no longer visible in process listings

**Before:**
```bash
setup.sh myconn socks5 proxy.com 1080 --auth-pass MySecretPassword
# ^^^ Visible in 'ps auxww'
```

**After:**
```bash
PROXY_AUTH_PASS=MySecretPassword setup.sh myconn socks5 proxy.com 1080 --auth-pass-env
# Environment variable not visible in 'ps' output
```

### 3. Secure Temporary File Locations

**Files Changed:**
- `src/opnsense/scripts/OPNsense/ProxyGateway/setup.sh`
- `src/opnsense/scripts/OPNsense/ProxyGateway/teardown.sh`

**Changes:**
- Gateway router files moved from `/tmp/pgw_*` to `/var/run/pgw_*`
- Prevents symlink attacks and race conditions
- Backward compatibility maintained in teardown.sh

### 4. Enhanced Input Validation

**Files Changed:**
- `src/opnsense/mvc/app/models/OPNsense/ProxyGateway/ProxyGateway.xml`

**Changes:**
- `proxyServer`: Now validates proper hostname format, IPv4, and IPv6 addresses
- `authUser`: Limited to 1-64 characters, alphanumeric + `@._-`
- `authPass`: Limited to 1-128 printable ASCII characters

**New validation regex:**
```xml
<!-- Hostname OR IPv4 OR IPv6 -->
<Mask>/^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$|^([0-9]{1,3}\.){3}[0-9]{1,3}$|^\[([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\]$/</Mask>
```

## Remaining Work

### Priority 1: CRITICAL-3 - Config.xml Encryption

**Requirement:** Encrypt passwords in `/conf/config.xml` before production use.

**Action Items:**
1. Research OPNsense's credential encryption API (check other VPN plugins)
2. Implement field-level encryption using OPNsense framework
3. Add migration path for existing plaintext passwords
4. Test encryption/decryption cycle thoroughly

**Estimated Effort:** 1-2 days

See `SECURITY_FIXES_IMPLEMENTATION_GUIDE.md` for detailed implementation options.

### Priority 2: Documentation Updates

**Required Documentation:**
- [ ] Update README.md with security considerations
- [ ] Create SECURITY.md with security policy
- [ ] Add security section to user guide (docs/guide.md)
- [ ] Document credential handling in SECURITY_REVIEW.md

### Priority 3: Testing

**Required Tests:**
- [ ] Security test suite (credential exposure, file permissions)
- [ ] Functional tests (connection lifecycle, all proxy types)
- [ ] Integration tests (firewall rules, gateway groups)
- [ ] Upgrade tests (config migration)

## OPNsense Official Plugin Readiness

### Current Status: ⚠️ NOT READY

**Blockers:**
1. ✅ ~~Plaintext passwords in runtime files~~ (FIXED)
2. ✅ ~~Passwords in process arguments~~ (FIXED)
3. ⚠️ **No encryption in config.xml** (CRITICAL - must fix)

**Recommendations:**
1. ✅ ~~Improve input validation~~ (DONE)
2. ⚪ Add API rate limiting (defer to review feedback)
3. ⚪ Implement audit logging (nice to have)

### Readiness Checklist

- [x] Plugin architecture follows OPNsense standards
- [x] MVC framework properly used
- [x] configd integration correct
- [x] Service management proper
- [x] License compatible (BSD-2-Clause + MIT)
- [x] Runtime credential exposure fixed
- [ ] Config.xml encryption implemented
- [ ] Security documentation complete
- [ ] Test suite created
- [ ] HA sync tested
- [ ] Performance benchmarked

**Estimated Time to Submission:** 1-2 weeks

## Security Posture

### Strengths

✅ **Excellent Architecture**
- Proper OPNsense MVC framework usage
- Clean separation of concerns
- Well-structured plugin hooks

✅ **Good Security Practices**
- Structured logging with proper levels
- ACL definitions for access control
- Validation framework usage

✅ **Fixed Critical Runtime Issues**
- No password exposure in process lists
- Secure file permissions on runtime files
- Protected temporary file handling

### Weaknesses (Remaining)

⚠️ **Config Backup Exposure**
- Passwords stored in plaintext in config.xml
- Config backups contain plaintext credentials
- HA sync transmits plaintext passwords

⚠️ **Limited Defense in Depth**
- No API rate limiting
- No detailed audit logging
- No credential rotation mechanism

## Recommendations

### Immediate (Before Production)

1. **Implement config.xml encryption** (CRITICAL-3)
   - Research OPNsense encryption API
   - Implement field-level encryption
   - Test thoroughly

2. **Security documentation**
   - Create SECURITY.md policy
   - Document credential handling
   - Add backup security warnings

### Short-term (Before Official Plugin Submission)

3. **Implement API rate limiting** (MEDIUM-3)
   - Protect health check endpoint
   - Protect reconfigure endpoint
   - Add cooldowns for expensive operations

4. **Create test suite**
   - Automated security tests
   - Functional tests
   - Integration tests

5. **Performance testing**
   - Benchmark multiple connections
   - Test high throughput scenarios
   - Memory leak testing

### Long-term (Post-submission)

6. **Enhanced security features**
   - Certificate pinning for TLS proxies
   - Audit logging for all operations
   - Credential rotation support

7. **Monitoring and alerting**
   - Connection health dashboard
   - Alert on repeated failures
   - Bandwidth usage reporting

## Conclusion

The os-proxygateway plugin is a well-architected OPNsense plugin with **one remaining critical security issue** that must be addressed before production use. The implemented fixes have significantly improved the security posture by eliminating runtime credential exposure.

**Current Recommendation:**
- ✅ Safe for testing environments with trusted users
- ⚠️ NOT READY for production without config.xml encryption
- ⚠️ NOT READY for OPNsense official plugin submission

**After implementing CRITICAL-3:**
- ✅ Safe for production use
- ✅ Ready for OPNsense plugin review
- ✅ Meets security best practices

## References

- **Full Security Review:** `SECURITY_REVIEW.md`
- **Implementation Guide:** `SECURITY_FIXES_IMPLEMENTATION_GUIDE.md`
- **Design Document:** `opnsense-multi-proxy-gateway-design.md`
- **Evaluation Plan:** `evaluation-and-execution-plan.md`

---

**Reviewed by:** Security Review Agent
**Date:** 2026-02-23
**Next Action:** Implement CRITICAL-3 (config.xml encryption)
