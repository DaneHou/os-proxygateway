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
 * Register a virtual interface group for all proxy gateway connections.
 * This allows OPNsense to show a "Proxy Gateway (Group)" interface.
 */
function proxygateway_interfaces()
{
    $interfaces = [];

    if (!proxygateway_enabled()) {
        return $interfaces;
    }

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
 * Register firewall rules for proxy gateway connections.
 * Handles outbound NAT on tun interfaces and proxy route-loop prevention.
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
        $proxyAddr = (string)$conn->proxyServer;
        $proxyPort = (string)$conn->proxyPort;

        // Outbound NAT on the tunnel interface
        $fw->registerNatRule(
            1000,
            [
                'interface'      => $ifname,
                'descr'          => "ProxyGW {$name}: Outbound NAT",
                'type'           => 'pass',
                'protocol'       => 'tcp/udp',
                'target'         => 'iface:' . $ifname,
                'staticnatport'  => false,
                'log'            => false,
            ]
        );

        // Allow traffic from this firewall to the proxy server (prevent routing loop)
        $fw->registerFilterRule(
            500,
            [
                'interface'   => 'wan',
                'descr'       => "ProxyGW {$name}: Allow proxy connection",
                'type'        => 'pass',
                'direction'   => 'out',
                'protocol'    => 'tcp',
                'to'          => $proxyAddr,
                'to_port'     => $proxyPort,
                'quick'       => true,
                'log'         => false,
            ]
        );
    }
}

/**
 * Register events to hook into during system operations.
 */
function proxygateway_configure()
{
    return [
        'newwanip' => ['proxygateway_configure_do'],
        'vpn'      => ['proxygateway_configure_do'],
    ];
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
