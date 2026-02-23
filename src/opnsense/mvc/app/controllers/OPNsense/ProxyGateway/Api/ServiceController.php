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
     * Reconfigure the service.
     * Writes the desired config JSON, then triggers the reconfigure configd action.
     * @return array status result
     */
    public function reconfigureAction()
    {
        $result = ['status' => 'failed'];

        if ($this->request->isPost()) {
            $this->sessionClose();

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
            file_put_contents('/var/run/proxygateway/desired.json', $configJson);

            $backend = new \OPNsense\Core\Backend();
            $response = trim($backend->configdRun('proxygateway reconfigure'));

            $result = ['status' => 'ok', 'response' => $response];
        }

        return $result;
    }

    /**
     * Get status of all connections.
     * @return array status data
     */
    public function statusAction()
    {
        $backend = new \OPNsense\Core\Backend();
        $response = $backend->configdRun('proxygateway status');
        $data = json_decode($response, true);

        return ['status' => 'ok', 'data' => $data ?: []];
    }
}
