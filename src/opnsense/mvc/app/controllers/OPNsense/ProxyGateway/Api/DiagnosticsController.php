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
     * Merges runtime status with configured connections so that
     * connections that are configured but not running are also shown.
     * @return array connection statuses
     */
    public function getStatusAction()
    {
        // Get runtime status from backend
        $backend = new \OPNsense\Core\Backend();
        $response = $backend->configdRun('proxygateway status');
        $runtimeData = json_decode($response, true);
        $runtimeMap = [];
        if (!empty($runtimeData['connections'])) {
            foreach ($runtimeData['connections'] as $conn) {
                $runtimeMap[$conn['name']] = $conn;
            }
        }

        // Merge with configured connections from model
        $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
        $connections = [];
        foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
            $name = (string)$conn->name;
            if (isset($runtimeMap[$name])) {
                $entry = $runtimeMap[$name];
                $entry['configured'] = true;
                $entry['enabled'] = (string)$conn->enabled;
                $connections[] = $entry;
                unset($runtimeMap[$name]);
            } else {
                $connections[] = [
                    'name'            => $name,
                    'interface'       => 'pgw_' . $name,
                    'proxy_type'      => (string)$conn->proxyType,
                    'proxy_addr'      => (string)$conn->proxyServer,
                    'proxy_port'      => (string)$conn->proxyPort,
                    'tun_local'       => '-',
                    'tun_peer'        => '-',
                    'pid'             => null,
                    'process_alive'   => false,
                    'interface_exists' => false,
                    'status'          => (string)$conn->enabled === '1' ? 'not_running' : 'disabled',
                    'health'          => [],
                    'configured'      => true,
                    'enabled'         => (string)$conn->enabled,
                ];
            }
        }

        // Include any orphaned runtime connections (running but removed from config)
        foreach ($runtimeMap as $conn) {
            $conn['configured'] = false;
            $connections[] = $conn;
        }

        return ['status' => 'ok', 'data' => ['connections' => $connections]];
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
