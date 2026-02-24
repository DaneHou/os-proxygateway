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
    protected static $internalServiceTemplate = 'OPNsense/ProxyGateway';
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
     * Sync interface IPs into config.xml for assigned pgw_* interfaces.
     *
     * Uses OPNsense's MVC Config API (not legacy write_config) to avoid
     * include dependency issues. Without this, get_interface_ip() returns
     * null and gateways show as "defunct".
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
                    // Set IP address if missing or changed
                    if (empty((string)$iface->ipaddr) || (string)$iface->ipaddr !== $tunAddr) {
                        // Use addChild/replace pattern for SimpleXML
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

        if ($changed) {
            $configObj->save();
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
                    'dnsMode'           => (string)$conn->dnsMode,
                    'dnsServer'         => (string)$conn->dnsServer,
                    'healthCheckEnabled' => (string)$conn->healthCheckEnabled,
                    'healthCheckInterval' => (string)$conn->healthCheckInterval,
                    'healthCheckTarget' => (string)$conn->healthCheckTarget,
                    'gatewayPriority'   => (string)$conn->gatewayPriority,
                    'killSwitch'        => (string)$conn->killSwitch,
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
            // Secure file permissions: owner (root) read/write only
            chmod($desiredFile, 0600);
            chown($desiredFile, 'root');

            $backend = new \OPNsense\Core\Backend();

            // Re-register interfaces so OPNsense picks up new/removed devices
            $backend->configdRun('interface invoke registration');

            // Apply the desired config (creates TUN devices, writes _router files)
            $response = trim($backend->configdpRun('proxygateway reconfigure'));

            // Sync interface IPs into config.xml using the MVC Config API.
            // This ensures get_interface_ip() returns the tunnel IP so
            // gateways are not "defunct".
            $this->syncInterfaceIps($mdl);

            // Reconfigure routes to pick up gateways with the updated IPs.
            // This must run AFTER sync so the gateway system sees the IPs.
            $backend->configdRun('interface routes reconfigure');

            $result = ['status' => 'ok', 'response' => $response];
        }

        return $result;
    }

}
