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

require_once '/usr/local/etc/inc/plugins.inc.d/proxygateway.inc';

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
     * Reconfigure the service.
     * Generates desired.json, triggers reconfigure, then syncs config.xml.
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

            // Generate desired.json from model (shared with boot handler)
            proxygateway_generate_desired($mdl);

            $backend = new \OPNsense\Core\Backend();

            // Re-register interfaces so OPNsense picks up new/removed devices
            $backend->configdRun('interface invoke registration');

            // Apply the desired config (creates TUN devices, writes _router files)
            $response = trim($backend->configdpRun('proxygateway reconfigure'));

            // Sync interface IPs + gateways into config.xml ONCE, after
            // reconfigure has created TUN devices and written _router files.
            proxygateway_sync_interfaces();

            // Reconfigure routes ONCE to pick up gateways with the updated IPs.
            $backend->configdRun('interface routes reconfigure');

            $result = ['status' => 'ok', 'response' => $response];
        }

        return $result;
    }

}
