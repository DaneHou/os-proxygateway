#!/usr/local/bin/php
<?php

/*
 * sync_interfaces.php - Sync proxy gateway interface IPs in OPNsense config.
 *
 * Called by configd (bootup event or manual) to ensure assigned pgw_*
 * interfaces have the correct IP address in config.xml.
 *
 * Uses OPNsense's MVC Config API to avoid legacy include dependency issues.
 */

require_once("config.inc");

use OPNsense\Core\Config;

$mdl = new \OPNsense\ProxyGateway\ProxyGateway();
$configObj = Config::getInstance();
$xml = $configObj->object();
$changed = false;

if (isset($xml->interfaces)) {
    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if (empty((string)$conn->enabled)) {
            continue;
        }

        $name = (string)$conn->name;
        $ifname = "pgw_{$name}";

        // Calculate TUN address (same algorithm as setup.sh)
        $tunAddress = (string)$conn->tunAddress;
        if (empty($tunAddress)) {
            $hash = md5($name);
            $oct3 = (hexdec(substr($hash, 0, 2)) % 254) + 1;
            $oct4 = (hexdec(substr($hash, 2, 2)) % 126) * 2 + 1;
            $tunAddress = "172.31.{$oct3}.{$oct4}";
        }

        foreach ($xml->interfaces->children() as $ifkey => $iface) {
            if ((string)$iface->{'if'} === $ifname) {
                if (empty((string)$iface->ipaddr) || (string)$iface->ipaddr !== $tunAddress) {
                    if (isset($iface->ipaddr)) {
                        $iface->ipaddr = $tunAddress;
                    } else {
                        $iface->addChild('ipaddr', $tunAddress);
                    }
                    if (isset($iface->subnet)) {
                        $iface->subnet = '32';
                    } else {
                        $iface->addChild('subnet', '32');
                    }
                    if (empty((string)$iface->enable)) {
                        if (isset($iface->enable)) {
                            $iface->enable = '1';
                        } else {
                            $iface->addChild('enable', '1');
                        }
                    }
                    $changed = true;
                }
                break;
            }
        }
    }
}

if ($changed) {
    $configObj->save();
    echo json_encode(['status' => 'ok', 'changed' => true]) . "\n";
} else {
    echo json_encode(['status' => 'ok', 'changed' => false]) . "\n";
}
