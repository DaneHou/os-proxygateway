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

/**
 * Register proxy gateway service with OPNsense service manager.
 * Displayed in Services > Diagnostics > Services.
 */
function proxygateway_services()
{
    $services = [];

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    if ((string)$mdl->general->enabled === '1') {
        $services[] = [
            'description' => gettext('Proxy Gateway'),
            'configd' => [
                'restart' => ['proxygateway restart'],
                'start'   => ['proxygateway start'],
                'stop'    => ['proxygateway stop'],
            ],
            'name' => 'proxygateway',
            'pidfile' => '/var/run/proxygateway/master.pid',
        ];
    }

    return $services;
}

/**
 * Register tun devices created by proxy gateway connections.
 * Allows OPNsense to recognize pgw_* devices in Interfaces > Assignments.
 */
function proxygateway_devices()
{
    $devices = [];

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    if ((string)$mdl->general->enabled !== '1') {
        return $devices;
    }

    $names = [];
    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if ((string)$conn->enabled === '1') {
            $name = (string)$conn->name;
            $ifname = "pgw_{$name}";
            $names[$ifname] = [
                'descr'   => sprintf(gettext('Proxy Gateway: %s'), (string)$conn->description ?: $name),
                'ifdescr' => $name,
                'name'    => $ifname,
            ];
        }
    }

    if (!empty($names)) {
        $devices[] = [
            'function' => 'proxygateway_configure_device',
            'names'    => $names,
            'pattern'  => '^pgw_',
            'volatile' => true,
            'type'     => 'proxygateway',
        ];
    }

    return $devices;
}

/**
 * Register proxy gateway tun interfaces as virtual OPNsense interfaces.
 */
function proxygateway_interfaces()
{
    $interfaces = [];

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    if ((string)$mdl->general->enabled !== '1') {
        return $interfaces;
    }

    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if ((string)$conn->enabled === '1') {
            $name = (string)$conn->name;
            $ifname = "pgw_{$name}";
            $interfaces[$ifname] = [
                'if'       => $ifname,
                'descr'    => sprintf('proxygateway_%s', $name),
                'type'     => 'none',
                'virtual'  => true,
                'networks' => [],
            ];
        }
    }

    return $interfaces;
}

/**
 * Register firewall rules for proxy gateway connections.
 * Handles outbound NAT on tun interfaces and DNS leak prevention.
 */
function proxygateway_firewall(\OPNsense\Firewall\Plugin $fw)
{
    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    if ((string)$mdl->general->enabled !== '1') {
        return;
    }

    foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
        if ((string)$conn->enabled !== '1') {
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
                'interface'   => $ifname,
                'descr'       => "ProxyGW {$name}: Outbound NAT",
                'type'        => 'pass',
                'protocol'    => 'tcp/udp',
                'poolopts'    => '',
                'target'      => 'iface:' . $ifname,
                'staticnatport' => false,
                'log'         => false,
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
        'bootup' => ['proxygateway_configure_bootup:3'],
        'newwanip' => ['proxygateway_configure_newwanip:3'],
    ];
}

/**
 * Start all enabled proxy gateways on bootup.
 */
function proxygateway_configure_bootup($verbose = false)
{
    if ($verbose) {
        echo 'Starting Proxy Gateway connections...';
    }

    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    if ((string)$mdl->general->enabled === '1') {
        configd_run('proxygateway start');
    }

    if ($verbose) {
        echo "done.\n";
    }
}

/**
 * Reconfigure after WAN IP changes.
 */
function proxygateway_configure_newwanip($verbose = false)
{
    $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
    if ((string)$mdl->general->enabled === '1') {
        configd_run('proxygateway reconfigure');
    }
}

/**
 * Callback to create/configure a tun device.
 * Called by the device registration system when an interface needs to be brought up.
 */
function proxygateway_configure_device($device)
{
    // The actual device creation is handled by setup.sh via configd.
    // This callback is invoked by OPNsense when the interface is being configured.
    // We extract the connection name from the device name and trigger setup.
    if (preg_match('/^pgw_(.+)$/', $device, $matches)) {
        $name = $matches[1];
        configd_run("proxygateway setup {$name}");
    }
}

/**
 * Register syslog targets for proxy gateway logging.
 */
function proxygateway_syslog()
{
    $logfacilities = [];

    $logfacilities['proxygateway'] = [
        'facility' => ['proxygateway'],
    ];

    return $logfacilities;
}
