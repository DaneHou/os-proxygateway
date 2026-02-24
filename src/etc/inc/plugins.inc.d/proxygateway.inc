<?php

/*
 * Copyright (c) 2024-2026 DaneBA
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
 */

function proxygateway_enabled()
{
    return (string)(new \OPNsense\ProxyGateway\ProxyGateway())->general->enabled == '1';
}

/**
 * Register proxy gateway services with OPNsense service manager.
 * Each enabled connection is registered as a separate service instance,
 * following the same pattern as WireGuard.
 */
function proxygateway_services()
{
    $services = [];

    if (!proxygateway_enabled()) {
        return $services;
    }

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if (!empty((string)$conn->enabled)) {
            $services[] = [
                'description' => 'Proxy Gateway ' . htmlspecialchars($conn->name),
                'configd' => [
                    'start'   => ["proxygateway start {$uuid}"],
                    'restart' => ["proxygateway restart {$uuid}"],
                    'stop'    => ["proxygateway stop {$uuid}"],
                ],
                'name' => 'proxygateway',
                'nocheck' => true,
                'id' => $uuid,
            ];
        }
    }

    return $services;
}

/**
 * Register tun devices created by proxy gateway connections.
 * Allows OPNsense to recognize pgw_* devices in Interfaces > Assignments.
 */
function proxygateway_devices()
{
    $names = [];

    if (!proxygateway_enabled()) {
        return [['pattern' => '^pgw', 'volatile' => true]];
    }

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if (!empty((string)$conn->enabled)) {
            $name = (string)$conn->name;
            $ifname = "pgw_{$name}";
            $names[$ifname] = [
                'descr'   => sprintf('%s (Proxy Gateway - %s)', $ifname, (string)$conn->description ?: $name),
                'ifdescr' => (string)$conn->description ?: $name,
                'name'    => $ifname,
            ];
        }
    }

    return [[
        'function'     => 'proxygateway_prepare',
        'configurable' => false,
        'pattern'      => '^pgw',
        'type'         => 'proxygateway',
        'volatile'     => true,
        'names'        => $names,
    ]];
}

/**
 * Device creation callback. Called by the device registration system when
 * an interface needs to be brought up. Creates the tun device if it doesn't exist.
 */
function proxygateway_prepare($device)
{
    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        $ifname = "pgw_" . (string)$conn->name;
        if ($device != $ifname) {
            continue;
        }

        if (!does_interface_exist($device)) {
            // On FreeBSD, create a tun device via the tun cloner, then rename it.
            // "ifconfig <custom_name> create" does NOT work for tun devices.
            $tundev = trim(shell_exec('/sbin/ifconfig tun create 2>&1'));
            if (!empty($tundev) && strpos($tundev, 'tun') === 0) {
                mwexecf('/sbin/ifconfig %s name %s', [$tundev, $device]);
                mwexecf('/sbin/ifconfig %s group proxygateway', $device);
                // Save the original tun device name so tun2socks can open /dev/tunN
                @mkdir('/var/run/proxygateway', 0750, true);
                @file_put_contents(
                    '/var/run/proxygateway/' . (string)$conn->name . '.tundev',
                    $tundev
                );
            }
        }

        return $device;
    }

    return null;
}

/**
 * Calculate the deterministic TUN address for a connection name.
 * Uses the same algorithm as setup.sh to ensure consistency.
 *
 * @param string $name       Connection name
 * @param string $tunAddress Optional explicit TUN address from config
 * @return string IPv4 address in 172.31.0.0/16 range
 */
function proxygateway_tun_address($name, $tunAddress = '')
{
    if (!empty($tunAddress)) {
        return $tunAddress;
    }
    $hash = md5($name);
    $oct3 = (hexdec(substr($hash, 0, 2)) % 254) + 1;
    $oct4 = (hexdec(substr($hash, 2, 2)) % 126) * 2 + 1;
    return "172.31.{$oct3}.{$oct4}";
}

/**
 * Register virtual interfaces for proxy gateway connections.
 *
 * Only registers the group interface here. Individual pgw_* interfaces
 * are NOT registered as virtual interfaces — they are registered via
 * proxygateway_devices() instead, which makes them available in
 * Interfaces > Assignments for the user to assign manually.
 *
 * This matches the WireGuard pattern: wireguard_interfaces() only
 * returns the group, individual wg* devices are in wireguard_devices().
 *
 * After the user assigns a pgw_* interface, proxygateway_sync_interfaces()
 * auto-configures the IP address so the gateway becomes functional.
 */
function proxygateway_interfaces()
{
    $interfaces = [];

    if (!proxygateway_enabled()) {
        return $interfaces;
    }

    // Group interface for all proxy gateways
    $interfaces['proxygateway'] = [
        'descr'   => gettext('Proxy Gateway (Group)'),
        'if'      => 'proxygateway',
        'virtual' => true,
        'enable'  => true,
        'type'    => 'group',
        'networks' => [],
    ];

    return $interfaces;
}

/**
 * Firewall integration hook.
 *
 * Generates automatic firewall rules for proxy gateway connections:
 * 1. Anti-routing-loop: Ensures tun2socks traffic to the proxy server exits
 *    through the correct physical interface, not through its own TUN.
 * 2. Pass rules on pgw_* interfaces: Allows tunnel traffic in both directions.
 */
function proxygateway_firewall(\OPNsense\Firewall\Plugin $fw)
{
    if (!proxygateway_enabled()) {
        return;
    }

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if (empty((string)$conn->enabled)) {
            continue;
        }

        $name = (string)$conn->name;
        $ifname = "pgw_{$name}";
        $proxyServer = (string)$conn->proxyServer;
        $proxyPort = (string)$conn->proxyPort;

        // Rule 1: Anti-routing-loop — ensure tun2socks traffic to the proxy
        // server exits through the correct physical interface, not the TUN.
        // Without this, policy routing rules could capture tun2socks's own
        // connection to the proxy, creating a routing loop.
        $fw->registerFilterRule(
            1,
            [
                'ipprotocol' => 'inet',
                'protocol'   => 'tcp',
                'from'       => '(self)',
                'to'         => $proxyServer,
                'to_port'    => $proxyPort,
                'direction'  => 'out',
                'quick'      => true,
                '#ref'       => "pgw_{$name}_antiloop",
                'descr'      => "Proxy Gateway: anti-loop {$name}",
                'log'        => false,
            ]
        );

        // Rule 2: Allow traffic on the pgw_* TUN interface.
        // If the user has assigned the interface (via Interfaces > Assignments),
        // use the assigned OPNsense identifier. Otherwise, skip per-interface
        // rules — the group pass rule below covers unassigned interfaces.
        $intf_id = null;
        foreach (legacy_config_get_interfaces() as $id => $cfg) {
            if (isset($cfg['if']) && $cfg['if'] === $ifname) {
                $intf_id = $id;
                break;
            }
        }

        if ($intf_id !== null) {
            $fw->registerFilterRule(
                2,
                [
                    'ipprotocol' => 'inet',
                    'interface'  => $intf_id,
                    '#ref'       => "pgw_{$name}_pass",
                    'descr'      => "Proxy Gateway: pass tunnel {$name}",
                    'log'        => false,
                ]
            );
        }
    }

    // Group pass rule: allow traffic on the proxygateway group interface.
    // Covers any pgw_* interface that is NOT assigned in Interfaces > Assignments.
    $fw->registerFilterRule(
        2,
        [
            'ipprotocol' => 'inet',
            'interface'  => 'proxygateway',
            '#ref'       => 'pgw_group_pass',
            'descr'      => 'Proxy Gateway: pass group traffic',
            'log'        => false,
        ]
    );
}

/**
 * Register events to hook into during system operations.
 *
 * 'bootup' ensures interface IPs are synced in config after reboot, so
 * gateways are not "defunct" when services start.
 *
 * 'newwanip' and 'vpn' are intentionally NOT handled here — proxy tunnels
 * connect via a fixed proxy IP/hostname and use static TUN IPs, so WAN/VPN
 * changes don't require reconfiguration. Handling 'newwanip' would also
 * create a feedback loop: reconfigure -> route change -> WAN DHCP renewal
 * -> newwanip -> reconfigure -> ...
 */
function proxygateway_configure()
{
    return [
        'bootup' => ['proxygateway_sync_only:2'],
    ];
}

/**
 * Lightweight sync handler for bootup events.
 * Only syncs interface IPs — does not trigger a full reconfigure.
 */
function proxygateway_sync_only($verbose = false)
{
    if (!proxygateway_enabled()) {
        return;
    }

    service_log('Syncing Proxy Gateway interface IPs...', $verbose);
    proxygateway_sync_interfaces();
    service_log("done.\n", $verbose);
}

/**
 * Sync IP configuration for assigned proxy gateway interfaces.
 *
 * When a user assigns a pgw_* interface in Interfaces → Assignments,
 * OPNsense creates a config entry but without IP configuration.
 * This function auto-populates the correct tunnel IP address so the
 * associated gateway is functional (not "defunct").
 *
 * Uses the MVC Config API to save, avoiding legacy include dependencies.
 */
function proxygateway_sync_interfaces()
{
    $configObj = \OPNsense\Core\Config::getInstance();
    $xml = $configObj->object();

    if (!isset($xml->interfaces)) {
        return;
    }

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    $changed = false;

    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if (empty((string)$conn->enabled)) {
            continue;
        }

        $name = (string)$conn->name;
        $ifname = "pgw_{$name}";
        $tunAddr = proxygateway_tun_address($name, (string)$conn->tunAddress);

        // Find this interface in OPNsense's assigned interfaces
        foreach ($xml->interfaces->children() as $ifkey => $iface) {
            if ((string)$iface->{'if'} === $ifname) {
                // Auto-configure IP if missing or changed
                if (empty((string)$iface->ipaddr) || (string)$iface->ipaddr !== $tunAddr) {
                    if (isset($iface->ipaddr)) {
                        $iface->ipaddr = $tunAddr;
                    } else {
                        $iface->addChild('ipaddr', $tunAddr);
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

    proxygateway_sync_gateways($mdl, $xml, $changed);

    if ($changed) {
        $configObj->save();
    }
}

/**
 * Sync gateway entries in config.xml for proxy gateway connections.
 *
 * Creates/updates <gateway_item> entries named PROXYGW_{NAME} under the
 * MVC <Gateways> section (capital G, with uuid attributes) with fargw=1
 * (point-to-point /32 subnet compatibility) and monitor_disable=1 (SOCKS5
 * doesn't support ICMP; the plugin uses its own HTTP health check).
 *
 * Also removes orphaned PROXYGW_* entries for disabled/deleted connections
 * and writes /tmp/pgw_{name}_router as a fallback for auto-detection.
 *
 * @param \OPNsense\ProxyGateway\ProxyGateway $mdl     Plugin model
 * @param \SimpleXMLElement                    $xml     Config XML root
 * @param bool                                 &$changed Set to true if config was modified
 */
function proxygateway_sync_gateways($mdl, $xml, &$changed)
{
    if (!isset($xml->interfaces)) {
        return;
    }

    // OPNsense stores gateways under <Gateways> (MVC model, capital G)
    if (!isset($xml->Gateways)) {
        return;
    }

    // Build map of expected gateway names for enabled connections with assigned interfaces
    $expectedGateways = [];

    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if (empty((string)$conn->enabled)) {
            continue;
        }

        $name = (string)$conn->name;
        $ifname = "pgw_{$name}";
        $tunAddr = proxygateway_tun_address($name, (string)$conn->tunAddress);
        $gwName = 'PROXYGW_' . strtoupper($name);

        // Calculate peer IP (gateway) = local IP + 1 on last octet
        $parts = explode('.', $tunAddr);
        $parts[3] = (int)$parts[3] + 1;
        $peerIp = implode('.', $parts);

        $priority = (string)$conn->gatewayPriority;
        if (empty($priority)) {
            $priority = '255';
        }

        // Find the assigned OPNsense interface key (e.g. opt4)
        $assignedKey = null;
        foreach ($xml->interfaces->children() as $ifkey => $iface) {
            if ((string)$iface->{'if'} === $ifname) {
                $assignedKey = $ifkey;
                break;
            }
        }

        if ($assignedKey === null) {
            continue;
        }

        $expectedGateways[$gwName] = [
            'disabled'                  => '0',
            'name'                      => $gwName,
            'descr'                     => "Proxy Gateway: {$name}",
            'interface'                 => $assignedKey,
            'ipprotocol'                => 'inet',
            'gateway'                   => $peerIp,
            'defaultgw'                 => '0',
            'fargw'                     => '1',
            'monitor_disable'           => '1',
            'monitor_noroute'           => '0',
            'monitor_killstates'        => '0',
            'monitor_killstates_priority' => '0',
            'monitor'                   => '',
            'force_down'                => '0',
            'priority'                  => $priority,
            'weight'                    => '1',
            'latencylow'                => '',
            'latencyhigh'               => '',
            'losslow'                   => '',
            'losshigh'                  => '',
            'interval'                  => '',
            'loss_interval'             => '',
            'data_length'               => '',
        ];

        // Write _router file as fallback for auto-detection
        $routerFile = "/tmp/{$ifname}_router";
        @file_put_contents($routerFile, $peerIp);
        @chmod($routerFile, 0644);
    }

    // Fields to check for updates on existing entries
    $updateFields = ['disabled', 'interface', 'gateway', 'priority', 'ipprotocol',
                     'fargw', 'monitor_disable', 'descr'];

    // Update or create gateway_item entries
    foreach ($expectedGateways as $gwName => $gwData) {
        $found = false;
        foreach ($xml->Gateways->children() as $gw) {
            if ($gw->getName() !== 'gateway_item') {
                continue;
            }
            if ((string)$gw->name === $gwName) {
                $found = true;
                foreach ($updateFields as $field) {
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
            $gw = $xml->Gateways->addChild('gateway_item');
            // Generate a UUID v4 for the new entry
            $newUuid = sprintf(
                '%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
                mt_rand(0, 0xffff), mt_rand(0, 0xffff),
                mt_rand(0, 0xffff),
                mt_rand(0, 0x0fff) | 0x4000,
                mt_rand(0, 0x3fff) | 0x8000,
                mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff)
            );
            $gw->addAttribute('uuid', $newUuid);
            foreach ($gwData as $field => $value) {
                $gw->addChild($field, $value);
            }
            $changed = true;
        }
    }

    // Remove orphaned PROXYGW_* entries
    $toRemove = [];
    foreach ($xml->Gateways->children() as $gw) {
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
}

/**
 * Configuration handler called on system events.
 */
function proxygateway_configure_do($verbose = false)
{
    if (!proxygateway_enabled()) {
        return;
    }

    service_log('Configuring Proxy Gateway...', $verbose);
    proxygateway_sync_interfaces();
    configd_run('proxygateway reconfigure');
    service_log("done.\n", $verbose);
}

/**
 * HA sync metadata.
 */
function proxygateway_xmlrpc_sync()
{
    return [[
        'id'          => 'proxygateway',
        'section'     => 'OPNsense.ProxyGateway',
        'description' => gettext('Proxy Gateway'),
        'services'    => ['proxygateway'],
    ]];
}

/**
 * Register syslog targets for proxy gateway logging.
 */
function proxygateway_syslog()
{
    return [
        'proxygateway' => ['facility' => ['proxygateway']],
    ];
}
