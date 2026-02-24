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

// Test 3: Check user privileges
$config = OPNsense\Core\Config::getInstance()->object();
if (isset($config->system->user)) {
    foreach ($config->system->user as $user) {
        $name = (string)$user->name;
        $privs = [];
        if (isset($user->priv)) {
            foreach ($user->priv as $p) {
                $privs[] = (string)$p;
            }
        }
        $hasAll = in_array('page-all', $privs);
        $hasPgw = false;
        foreach ($privs as $p) {
            if (strpos($p, 'proxygateway') !== false) {
                $hasPgw = true;
            }
        }
        echo "3. User '{$name}': page-all=" . ($hasAll ? "YES" : "NO") . ", proxygateway=" . ($hasPgw ? "YES" : "NO") . "\n";
    }
}

// Test 4: Check menu generation
try {
    $menuSystem = new \OPNsense\Core\Menu\MenuSystem();
    echo "4. MenuSystem created OK\n";

    // Dump Services subtree
    $xml = simplexml_load_file('/usr/local/opnsense/mvc/app/models/OPNsense/ProxyGateway/Menu/Menu.xml');
    echo "5. Menu.xml root children: ";
    foreach ($xml->children() as $child) {
        echo $child->getName() . " ";
    }
    echo "\n";
} catch (Exception $e) {
    echo "4. Menu: ERROR - " . $e->getMessage() . "\n";
}

echo "\nDone.\n";
