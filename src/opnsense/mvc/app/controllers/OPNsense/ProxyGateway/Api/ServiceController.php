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

namespace OPNsense\ProxyGateway\Api;

use OPNsense\Base\ApiMutableServiceControllerBase;
use OPNsense\Core\Config;

/**
 * API controller for managing the proxy gateway service lifecycle.
 *
 * Endpoints:
 *   POST /api/proxygateway/service/start
 *   POST /api/proxygateway/service/stop
 *   POST /api/proxygateway/service/restart
 *   POST /api/proxygateway/service/reconfigure
 *   GET  /api/proxygateway/service/status
 */
class ServiceController extends ApiMutableServiceControllerBase
{
    protected static $internalServiceClass = '\OPNsense\ProxyGateway\ProxyGateway';
    protected static $internalServiceEnabled = 'general.enabled';
    protected static $internalServiceName = 'proxygateway';

    /**
     * Calculate the deterministic TUN address for a connection name.
     * Must match the algorithm in setup.sh and proxygateway.inc.
     */
    private function tunAddress($name, $tunAddress = '')
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
     * Sync interface IPs and gateway entries into config.xml for assigned pgw_* interfaces.
     */
    private function syncInterfaceIps($mdl)
    {
        $configObj = Config::getInstance();
        $xml = $configObj->object();
        $changed = false;

        if (!isset($xml->interfaces)) {
            return;
        }

        foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
            if (empty((string)$conn->enabled)) {
                continue;
            }

            $name = (string)$conn->name;
            $ifname = "pgw_{$name}";
            $tunAddr = $this->tunAddress($name, (string)$conn->tunAddress);

            foreach ($xml->interfaces->children() as $ifkey => $iface) {
                if ((string)$iface->{'if'} === $ifname) {
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

        $this->syncGateways($mdl, $xml, $changed);

        if ($changed) {
            $configObj->save();
        }
    }

    /**
     * Sync gateway entries in config.xml for proxy gateway connections.
     */
    private function syncGateways($mdl, $xml, &$changed)
    {
        if (!isset($xml->interfaces) || !isset($xml->Gateways)) {
            return;
        }

        $expectedGateways = [];

        foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
            if (empty((string)$conn->enabled)) {
                continue;
            }

            $name = (string)$conn->name;
            $ifname = "pgw_{$name}";
            $tunAddr = $this->tunAddress($name, (string)$conn->tunAddress);
            $gwName = 'PROXYGW_' . strtoupper($name);

            $parts = explode('.', $tunAddr);
            $parts[3] = (int)$parts[3] + 1;
            $peerIp = implode('.', $parts);

            $priority = (string)$conn->gatewayPriority;
            if (empty($priority)) {
                $priority = '255';
            }

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

            $routerFile = "/tmp/{$ifname}_router";
            @file_put_contents($routerFile, $peerIp);
            @chmod($routerFile, 0644);
        }

        $updateFields = ['disabled', 'interface', 'gateway', 'priority', 'ipprotocol',
                         'fargw', 'monitor_disable', 'descr'];

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
                $newUuid = sprintf(
                    '%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
                    random_int(0, 0xffff), random_int(0, 0xffff),
                    random_int(0, 0xffff),
                    random_int(0, 0x0fff) | 0x4000,
                    random_int(0, 0x3fff) | 0x8000,
                    random_int(0, 0xffff), random_int(0, 0xffff), random_int(0, 0xffff)
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
     * Reconfigure the service.
     * Writes the desired config JSON, then triggers the reconfigure configd action.
     * @return array status result
     */
    public function reconfigureAction()
    {
        $result = ['status' => 'failed'];

        if ($this->request->isPost()) {
            // Release PHP session lock so the browser isn't blocked during
            // the potentially long-running backend call.
            session_write_close();

            $mdl = new \OPNsense\ProxyGateway\ProxyGateway();

            // Build desired config JSON from model
            $connections = [];
            foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
                $connections[] = [
                    'uuid'              => $uuid,
                    'name'              => (string)$conn->name,
                    'enabled'           => (string)$conn->enabled,
                    'proxyType'         => (string)$conn->proxyType,
                    'proxyServer'       => (string)$conn->proxyServer,
                    'proxyPort'         => (string)$conn->proxyPort,
                    'proxyInterface'    => (string)$conn->proxyInterface ?: 'wan',
                    'authEnabled'       => (string)$conn->authEnabled,
                    'authUser'          => (string)$conn->authUser,
                    'authPass'          => (string)$conn->authPass,
                    'tunAddress'        => (string)$conn->tunAddress,
                    'tunMTU'            => (string)$conn->tunMTU,
                    'healthCheckEnabled' => (string)$conn->healthCheckEnabled,
                    'healthCheckTarget' => (string)$conn->healthCheckTarget,
                    'gatewayPriority'   => (string)$conn->gatewayPriority,
                    'logLevel'          => (string)$mdl->general->logLevel,
                ];
            }

            $configJson = json_encode(
                ['connections' => $connections],
                JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES
            );

            @mkdir('/var/run/proxygateway', 0750, true);
            $desiredFile = '/var/run/proxygateway/desired.json';
            file_put_contents($desiredFile, $configJson);
            chmod($desiredFile, 0600);
            chown($desiredFile, 'root');

            $backend = new \OPNsense\Core\Backend();

            // Re-register interfaces so OPNsense picks up new/removed devices
            $backend->configdRun('interface invoke registration');

            // Apply the desired config (creates TUN devices, writes _router files)
            $response = trim($backend->configdpRun('proxygateway reconfigure'));

            // Sync interface IPs + gateways into config.xml ONCE, after
            // reconfigure has created TUN devices and written _router files.
            $this->syncInterfaceIps($mdl);

            // Reconfigure routes ONCE to pick up gateways with the updated IPs.
            $backend->configdRun('interface routes reconfigure');

            $result = ['status' => 'ok', 'response' => $response];
        }

        return $result;
    }

}
