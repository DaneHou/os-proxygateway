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

use OPNsense\Base\ApiControllerBase;

/**
 * API controller for proxy gateway diagnostics.
 *
 * Endpoints:
 *   GET  /api/proxygateway/diagnostics/getStatus
 *   POST /api/proxygateway/diagnostics/testConnection
 *   GET  /api/proxygateway/diagnostics/getLogs
 */
class DiagnosticsController extends ApiControllerBase
{
    /**
     * Get full status of all proxy gateway connections.
     * @return array connection statuses
     */
    public function getStatusAction()
    {
        $backend = new \OPNsense\Core\Backend();
        $response = $backend->configdRun('proxygateway status');
        $data = json_decode($response, true);

        return ['status' => 'ok', 'data' => $data ?: ['connections' => []]];
    }

    /**
     * Test connectivity of a specific connection by triggering a health check.
     * @return array test result
     */
    public function testConnectionAction()
    {
        $result = ['status' => 'failed'];

        if ($this->request->isPost()) {
            $name = $this->request->getPost('name', 'alphanum', '');

            if (empty($name)) {
                return ['status' => 'failed', 'message' => 'Connection name is required'];
            }

            $backend = new \OPNsense\Core\Backend();
            $response = trim($backend->configdRun("proxygateway healthcheck {$name}"));

            $result = [
                'status' => 'ok',
                'name'   => $name,
                'result' => $response,
            ];
        }

        return $result;
    }

    /**
     * Get logs for a specific connection or all connections.
     * @return array log lines
     */
    public function getLogsAction()
    {
        $name = $this->request->get('name', 'alphanum', '');
        $lines = (int)$this->request->get('lines', 'int', 50);
        $lines = min(max($lines, 10), 500);

        if (!empty($name)) {
            $logFile = "/var/log/proxygateway/{$name}.log";
        } else {
            // Aggregate all logs
            $logFile = "/var/log/proxygateway/*.log";
        }

        $backend = new \OPNsense\Core\Backend();

        // Use tail to get recent log lines
        if (!empty($name)) {
            $cmd = sprintf('tail -n %d %s 2>/dev/null', $lines, escapeshellarg($logFile));
        } else {
            $cmd = sprintf('tail -n %d /var/log/proxygateway/*.log 2>/dev/null', $lines);
        }

        $output = [];
        exec($cmd, $output);

        return [
            'status' => 'ok',
            'name'   => $name ?: 'all',
            'lines'  => $output,
        ];
    }
}
