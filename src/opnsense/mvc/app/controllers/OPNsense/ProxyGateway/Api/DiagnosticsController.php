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
 *   GET  /api/proxygateway/diagnostics/getSpeedTestResults
 *   GET  /api/proxygateway/diagnostics/getSpeedTestHistory
 *   POST /api/proxygateway/diagnostics/runSpeedTest
 *   GET  /api/proxygateway/diagnostics/getHealthHistory
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
            $name = $this->request->getPost('name');

            if (empty($name) || !preg_match('/^[a-zA-Z0-9_]{1,16}$/', $name)) {
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
        $name = $this->request->get('name', null, '');
        if (!empty($name) && !preg_match('/^[a-zA-Z0-9_]{1,16}$/', $name)) {
            return ['status' => 'failed', 'message' => 'Invalid connection name'];
        }
        $lines = (int)$this->request->get('lines', null, 50);
        $lines = min(max($lines, 10), 500);

        if ($name === 'reconfigure') {
            $logFile = "/var/log/proxygateway/reconfigure.log";
        } elseif (!empty($name)) {
            $logFile = "/var/log/proxygateway/{$name}.log";
        } else {
            // Aggregate all logs — merge and sort by timestamp
            $logFile = "/var/log/proxygateway/*.log";
        }

        // Use tail to get recent log lines; for multiple files, tail each then sort
        if (!empty($name)) {
            $cmd = sprintf('tail -n %d %s 2>/dev/null', $lines, escapeshellarg($logFile));
        } else {
            // More efficient: tail each file first, then sort only the recent entries
            $cmd = sprintf(
                'tail -q -n %d /var/log/proxygateway/*.log 2>/dev/null | sort | tail -n %d',
                $lines,
                $lines
            );
        }

        $output = [];
        exec($cmd, $output);

        return [
            'status' => 'ok',
            'name'   => $name ?: 'all',
            'lines'  => $output,
        ];
    }

    /**
     * Get list of available connection log names.
     * @return array connection names that have log files
     */
    public function getLogConnectionsAction()
    {
        $connections = [];
        $logDir = '/var/log/proxygateway';

        if (is_dir($logDir)) {
            foreach (glob("{$logDir}/*.log") as $logFile) {
                $name = basename($logFile, '.log');
                $connections[] = $name;
            }
            sort($connections);
        }

        return ['status' => 'ok', 'connections' => $connections];
    }

    /**
     * Clear logs for a specific connection or all connections.
     * @return array result
     */
    public function clearLogsAction()
    {
        $result = ['status' => 'failed'];

        if ($this->request->isPost()) {
            $name = $this->request->getPost('name', null, '');

            if (!empty($name) && !preg_match('/^[a-zA-Z0-9_]{1,16}$/', $name)) {
                return ['status' => 'failed', 'message' => 'Invalid connection name'];
            }

            $backend = new \OPNsense\Core\Backend();
            $response = trim($backend->configdRun("proxygateway clearlogs {$name}"));

            $result = [
                'status'  => 'ok',
                'message' => $response,
            ];
        }

        return $result;
    }

    /**
     * System check — verify prerequisites for the proxy gateway.
     * @return array check results
     */
    public function getSystemCheckAction()
    {
        $checks = [];

        // Check tun2socks binary
        $tun2socks = '/usr/local/bin/tun2socks';
        $checks['tun2socks'] = [
            'label'  => 'tun2socks binary',
            'path'   => $tun2socks,
            'exists' => file_exists($tun2socks),
            'executable' => is_executable($tun2socks),
        ];
        if (is_executable($tun2socks)) {
            $version = trim(shell_exec($tun2socks . ' --version 2>&1') ?? '');
            $checks['tun2socks']['version'] = $version;
        }

        // Check runtime directories
        $checks['rundir'] = [
            'label'  => 'Runtime directory',
            'path'   => '/var/run/proxygateway',
            'exists' => is_dir('/var/run/proxygateway'),
        ];
        $checks['logdir'] = [
            'label'  => 'Log directory',
            'path'   => '/var/log/proxygateway',
            'exists' => is_dir('/var/log/proxygateway'),
        ];

        // Check desired.json
        $desiredPath = '/var/run/proxygateway/desired.json';
        $desiredExists = file_exists($desiredPath);
        $checks['desired_config'] = [
            'label'  => 'Desired config (desired.json)',
            'path'   => $desiredPath,
            'exists' => $desiredExists,
        ];
        if ($desiredExists) {
            $json = json_decode(file_get_contents($desiredPath), true);
            $checks['desired_config']['connections'] = count($json['connections'] ?? []);
            $enabled = 0;
            foreach ($json['connections'] ?? [] as $c) {
                if (($c['enabled'] ?? '0') === '1') {
                    $enabled++;
                }
            }
            $checks['desired_config']['enabled'] = $enabled;
        }

        // Check plugin enabled
        $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
        $checks['plugin_enabled'] = [
            'label'  => 'Plugin globally enabled',
            'value'  => (string)$mdl->general->enabled === '1',
        ];

        // Last reconfigure log
        $reconfigLog = '/var/log/proxygateway/reconfigure.log';
        $lastReconfigure = '';
        if (file_exists($reconfigLog)) {
            $lastReconfigure = trim(shell_exec("tail -n 50 " . escapeshellarg($reconfigLog) . " 2>/dev/null") ?? '');
        }
        $checks['last_reconfigure'] = [
            'label'  => 'Last reconfigure output',
            'log'    => $lastReconfigure,
        ];

        // Check configd actions registered
        $backend = new \OPNsense\Core\Backend();
        $actionsResponse = trim($backend->configdRun('proxygateway status') ?? '');
        $checks['configd_actions'] = [
            'label'      => 'configd status action',
            'responsive' => !empty($actionsResponse),
        ];

        return ['status' => 'ok', 'checks' => $checks];
    }

    /**
     * Get latest speed test results for all connections.
     * Reads .speedtest and .speedtest_domestic files from /var/run/proxygateway/.
     * @return array speed test results per connection
     */
    public function getSpeedTestResultsAction()
    {
        $runDir = '/var/run/proxygateway';
        $results = [];

        $mdl = new \OPNsense\ProxyGateway\ProxyGateway();
        foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
            if (empty((string)$conn->enabled)) {
                continue;
            }

            $name = (string)$conn->name;
            $entry = ['name' => $name, 'international' => null, 'domestic' => null];

            // Read international result
            $intlFile = "{$runDir}/{$name}.speedtest";
            if (file_exists($intlFile)) {
                $entry['international'] = $this->parseSpeedTestFile($intlFile);
            }

            // Read domestic result
            $domFile = "{$runDir}/{$name}.speedtest_domestic";
            if (file_exists($domFile)) {
                $entry['domestic'] = $this->parseSpeedTestFile($domFile);
            }

            $results[] = $entry;
        }

        return ['status' => 'ok', 'data' => $results];
    }

    /**
     * Get speed test history for a specific connection.
     * @return array JSON lines from the history log
     */
    public function getSpeedTestHistoryAction()
    {
        $name = $this->request->get('name', null, '');
        if (empty($name) || !preg_match('/^[a-zA-Z0-9_]{1,16}$/', $name)) {
            return ['status' => 'failed', 'message' => 'Valid connection name is required'];
        }

        $limit = (int)$this->request->get('limit', null, 100);
        $limit = min(max($limit, 10), 500);

        $logFile = "/var/log/proxygateway/{$name}_speedtest.log";
        $history = [];

        if (file_exists($logFile)) {
            $cmd = sprintf('tail -n %d %s 2>/dev/null', $limit, escapeshellarg($logFile));
            $output = [];
            exec($cmd, $output);
            foreach ($output as $line) {
                $decoded = json_decode($line, true);
                if ($decoded !== null) {
                    $history[] = $decoded;
                }
            }
        }

        return ['status' => 'ok', 'name' => $name, 'history' => $history];
    }

    /**
     * Get health check history for a specific connection.
     * @return array JSON lines from the health history log
     */
    public function getHealthHistoryAction()
    {
        $name = $this->request->get('name', null, '');
        if (empty($name) || !preg_match('/^[a-zA-Z0-9_]{1,16}$/', $name)) {
            return ['status' => 'failed', 'message' => 'Valid connection name is required'];
        }

        $limit = (int)$this->request->get('limit', null, 100);
        $limit = min(max($limit, 10), 500);

        $logFile = "/var/log/proxygateway/{$name}_health.log";
        $history = [];

        if (file_exists($logFile)) {
            $cmd = sprintf('tail -n %d %s 2>/dev/null', $limit, escapeshellarg($logFile));
            $output = [];
            exec($cmd, $output);
            foreach ($output as $line) {
                $decoded = json_decode($line, true);
                if ($decoded !== null) {
                    $history[] = $decoded;
                }
            }
        }

        return ['status' => 'ok', 'name' => $name, 'history' => $history];
    }

    /**
     * Trigger a manual speed test for a specific connection.
     * @return array test result
     */
    public function runSpeedTestAction()
    {
        $result = ['status' => 'failed'];

        if ($this->request->isPost()) {
            $name = $this->request->getPost('name');
            $type = $this->request->getPost('type', null, 'international');

            if (empty($name) || !preg_match('/^[a-zA-Z0-9_]{1,16}$/', $name)) {
                return ['status' => 'failed', 'message' => 'Connection name is required'];
            }

            if (!in_array($type, ['international', 'domestic'])) {
                $type = 'international';
            }

            $backend = new \OPNsense\Core\Backend();
            // speedtest.sh args: <name> [test_url] [size_bytes] [timeout] [test_type]
            // Pass empty strings for url/size/timeout to use defaults.
            $response = trim($backend->configdRun("proxygateway speedtest {$name} \"\" \"\" \"\" {$type}"));

            $result = [
                'status' => 'ok',
                'name'   => $name,
                'type'   => $type,
                'result' => $response,
            ];
        }

        return $result;
    }

    /**
     * Parse a .speedtest key=value file into an associative array.
     */
    private function parseSpeedTestFile($path)
    {
        $data = [];
        $lines = @file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if ($lines === false) {
            return null;
        }
        foreach ($lines as $line) {
            if (strpos($line, '=') !== false) {
                list($key, $val) = explode('=', $line, 2);
                $data[trim($key)] = trim($val);
            }
        }
        return $data;
    }
}
