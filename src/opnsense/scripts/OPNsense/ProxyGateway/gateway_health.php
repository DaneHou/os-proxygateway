#!/usr/local/bin/php
<?php

/*
 * gateway_health.php — Read-only gateway list with dpinger status, for
 * plugin_health.py (configctl proxygateway healthcheck).
 *
 * Prints {"gateways": [{name, interface, device, disabled, force_down,
 * monitor_disable, status}]}: OPNsense's own gateway list (configured and
 * dynamic ones, as the core gateway_status.php uses) joined with
 * dpinger_status(). Whitelisted fields only; changes nothing.
 */

require_once 'config.inc';
require_once 'util.inc';
require_once 'interfaces.inc';
require_once 'plugins.inc.d/dpinger.inc';

$out = [];
try {
    $status = dpinger_status();
    foreach ((new \OPNsense\Routing\Gateways())->gatewaysIndexedByName(true) as $name => $gw) {
        $out[] = [
            'name' => (string)$name,
            'interface' => (string)($gw['interface'] ?? ''),
            'device' => (string)($gw['if'] ?? ''),
            'disabled' => !empty($gw['disabled']),
            'force_down' => !empty($gw['force_down']),
            'monitor_disable' => !empty($gw['monitor_disable']),
            'status' => !empty($status[$name]['status']) ? strtolower((string)$status[$name]['status']) : 'none',
        ];
    }
} catch (\Throwable $e) {
    echo json_encode(['error' => 'gateways unavailable']) . PHP_EOL;
    exit(0);
}
echo json_encode(['gateways' => $out]) . PHP_EOL;
