#!/usr/local/bin/php
<?php
require_once('/usr/local/etc/inc/config.inc');

// Test 1: Model loads?
try {
    $m = new \OPNsense\ProxyGateway\ProxyGateway();
    echo "1. Model: OK\n";
} catch (Exception $e) {
    echo "1. Model: FAILED - " . $e->getMessage() . "\n";
}

// Test 2: XML files valid?
$files = [
    '/usr/local/opnsense/mvc/app/models/OPNsense/ProxyGateway/Menu/Menu.xml',
    '/usr/local/opnsense/mvc/app/models/OPNsense/ProxyGateway/ACL/ACL.xml',
    '/usr/local/opnsense/mvc/app/models/OPNsense/ProxyGateway/ProxyGateway.xml',
];
foreach ($files as $f) {
    $x = @simplexml_load_file($f);
    echo "2. " . basename(dirname($f)) . "/" . basename($f) . ": " . ($x ? "OK" : "PARSE ERROR") . "\n";
}

// Test 3: Check ALL user and group privileges
$config = OPNsense\Core\Config::getInstance()->object();

// Build group privilege map
$groupPrivs = [];
if (isset($config->system->group)) {
    foreach ($config->system->group as $group) {
        $gname = (string)$group->name;
        $gid = (string)$group->gid;
        $privs = [];
        if (isset($group->priv)) {
            foreach ($group->priv as $p) {
                $privs[] = (string)$p;
            }
        }
        $groupPrivs[$gid] = ['name' => $gname, 'privs' => $privs];
        $hasAll = in_array('page-all', $privs);
        $hasPgw = false;
        foreach ($privs as $p) {
            if (strpos($p, 'proxygateway') !== false) {
                $hasPgw = true;
            }
        }
        echo "3a. Group '{$gname}' (gid={$gid}): page-all=" . ($hasAll ? "YES" : "NO")
            . ", proxygateway=" . ($hasPgw ? "YES" : "NO")
            . ", total_privs=" . count($privs) . "\n";
    }
}

// Check users and their effective privileges (user + groups)
if (isset($config->system->user)) {
    foreach ($config->system->user as $user) {
        $name = (string)$user->name;
        $uid = (string)$user->uid;

        // User-level privs
        $userPrivs = [];
        if (isset($user->priv)) {
            foreach ($user->priv as $p) {
                $userPrivs[] = (string)$p;
            }
        }

        // Group memberships
        $groups = [];
        if (isset($config->system->group)) {
            foreach ($config->system->group as $group) {
                if (isset($group->member)) {
                    foreach ($group->member as $member) {
                        if ((string)$member === $uid) {
                            $groups[] = (string)$group->name;
                        }
                    }
                }
            }
        }

        // Effective privs = user privs + all group privs
        $effectivePrivs = $userPrivs;
        foreach ($config->system->group as $group) {
            if (isset($group->member)) {
                foreach ($group->member as $member) {
                    if ((string)$member === $uid && isset($group->priv)) {
                        foreach ($group->priv as $p) {
                            $effectivePrivs[] = (string)$p;
                        }
                    }
                }
            }
        }
        $effectivePrivs = array_unique($effectivePrivs);

        $hasAll = in_array('page-all', $effectivePrivs);
        $hasPgw = false;
        foreach ($effectivePrivs as $p) {
            if (strpos($p, 'proxygateway') !== false) {
                $hasPgw = true;
            }
        }

        echo "3b. User '{$name}' (uid={$uid}): groups=[" . implode(',', $groups) . "]"
            . ", effective page-all=" . ($hasAll ? "YES" : "NO")
            . ", proxygateway=" . ($hasPgw ? "YES" : "NO") . "\n";
    }
}

// Test 4: Check what ACL names are registered for our plugin
echo "\n4. Registered ACL entries from ProxyGateway:\n";
$acl = simplexml_load_file('/usr/local/opnsense/mvc/app/models/OPNsense/ProxyGateway/ACL/ACL.xml');
foreach ($acl->children() as $aclName => $aclEntry) {
    echo "   ACL: {$aclName} => " . (string)$aclEntry->name . "\n";
    if (isset($aclEntry->patterns)) {
        foreach ($aclEntry->patterns->pattern as $p) {
            echo "     pattern: {$p}\n";
        }
    }
}

echo "\nDone.\n";
