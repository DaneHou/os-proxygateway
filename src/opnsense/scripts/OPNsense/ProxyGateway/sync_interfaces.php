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

// --- Gateway sync ---
// Create/update <gateway_item> entries named PROXYGW_{NAME} with fargw=1
// (point-to-point /32 subnet) and monitor_disable=1 (plugin uses HTTP health check).

if (!isset($xml->gateways)) {
    $xml->addChild('gateways');
}

// Build map of expected gateways
$expectedGateways = [];

foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
    if (empty((string)$conn->enabled)) {
        continue;
    }

    $name = (string)$conn->name;
    $ifname = "pgw_{$name}";
    $gwName = 'PROXYGW_' . strtoupper($name);

    // Calculate TUN address
    $tunAddress = (string)$conn->tunAddress;
    if (empty($tunAddress)) {
        $hash = md5($name);
        $oct3 = (hexdec(substr($hash, 0, 2)) % 254) + 1;
        $oct4 = (hexdec(substr($hash, 2, 2)) % 126) * 2 + 1;
        $tunAddress = "172.31.{$oct3}.{$oct4}";
    }

    // Calculate peer IP (gateway) = local IP + 1 on last octet
    $parts = explode('.', $tunAddress);
    $parts[3] = (int)$parts[3] + 1;
    $peerIp = implode('.', $parts);

    $priority = (string)$conn->gatewayPriority;
    if (empty($priority)) {
        $priority = '255';
    }

    // Find the assigned OPNsense interface key
    $assignedKey = null;
    if (isset($xml->interfaces)) {
        foreach ($xml->interfaces->children() as $ifkey => $iface) {
            if ((string)$iface->{'if'} === $ifname) {
                $assignedKey = $ifkey;
                break;
            }
        }
    }

    if ($assignedKey === null) {
        continue;
    }

    $expectedGateways[$gwName] = [
        'interface'       => $assignedKey,
        'gateway'         => $peerIp,
        'name'            => $gwName,
        'priority'        => $priority,
        'ipprotocol'      => 'inet',
        'fargw'           => '1',
        'monitor_disable' => '1',
        'descr'           => "Proxy Gateway: {$name}",
    ];

    // Write _router file as fallback for auto-detection
    $routerFile = "/tmp/{$ifname}_router";
    @file_put_contents($routerFile, $peerIp);
    @chmod($routerFile, 0644);
}

// Update or create gateway_item entries
foreach ($expectedGateways as $gwName => $gwData) {
    $found = false;
    foreach ($xml->gateways->children() as $gw) {
        if ($gw->getName() !== 'gateway_item') {
            continue;
        }
        if ((string)$gw->name === $gwName) {
            $found = true;
            $fields = ['interface', 'gateway', 'priority', 'ipprotocol', 'fargw', 'monitor_disable', 'descr'];
            foreach ($fields as $field) {
                if ((string)$gw->{$field} !== $gwData[$field]) {
                    if (isset($gw->{$field})) {
                        $gw->{$field} = $gwData[$field];
                    } else {
                        $gw->addChild($field, $gwData[$field]);
                    }
                    $changed = true;
                }
            }
            break;
        }
    }

    if (!$found) {
        $gw = $xml->gateways->addChild('gateway_item');
        foreach ($gwData as $field => $value) {
            $gw->addChild($field, $value);
        }
        $changed = true;
    }
}

// Remove orphaned PROXYGW_* entries
$toRemove = [];
foreach ($xml->gateways->children() as $gw) {
    if ($gw->getName() !== 'gateway_item') {
        continue;
    }
    $name = (string)$gw->name;
    if (strpos($name, 'PROXYGW_') === 0 && !isset($expectedGateways[$name])) {
        $toRemove[] = $gw;
    }
}
foreach ($toRemove as $gw) {
    $dom = dom_import_simplexml($gw);
    $dom->parentNode->removeChild($dom);
    $changed = true;
}

if ($changed) {
    $configObj->save();
    echo json_encode(['status' => 'ok', 'changed' => true]) . "\n";
} else {
    echo json_encode(['status' => 'ok', 'changed' => false]) . "\n";
}
