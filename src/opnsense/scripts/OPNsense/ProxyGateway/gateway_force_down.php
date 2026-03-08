#!/usr/local/bin/php
<?php

/*
 * gateway_force_down.php — Set or clear force_down on a proxy gateway.
 *
 * Usage: gateway_force_down.php <connection_name> <up|down>
 *
 * Modifies the PROXYGW_<NAME> gateway_item in config.xml's <Gateways> section,
 * then triggers route reconfiguration so the change takes effect immediately.
 *
 * Called via configd: configctl proxygateway forcedown <name> <up|down>
 */

require_once 'config.inc';

if ($argc < 3) {
    echo json_encode(['status' => 'error', 'message' => 'Usage: gateway_force_down.php <name> <up|down>']);
    exit(1);
}

$name = $argv[1];
$action = $argv[2];

// Validate name
if (!preg_match('/^[a-zA-Z0-9_]{1,16}$/', $name)) {
    echo json_encode(['status' => 'error', 'message' => 'Invalid connection name']);
    exit(1);
}

if (!in_array($action, ['up', 'down'])) {
    echo json_encode(['status' => 'error', 'message' => 'Action must be "up" or "down"']);
    exit(1);
}

$gwName = 'PROXYGW_' . strtoupper($name);
$forceDown = ($action === 'down') ? '1' : '0';

// Use OPNsense Config singleton (provides locking)
$configObj = \OPNsense\Core\Config::getInstance();
$xml = $configObj->object();

if (!isset($xml->Gateways)) {
    echo json_encode(['status' => 'error', 'message' => 'No Gateways section in config.xml']);
    exit(1);
}

$found = false;
foreach ($xml->Gateways->children() as $gw) {
    if ($gw->getName() !== 'gateway_item') {
        continue;
    }
    if ((string)$gw->name === $gwName) {
        if (isset($gw->force_down)) {
            $gw->force_down = $forceDown;
        } else {
            $gw->addChild('force_down', $forceDown);
        }
        $found = true;
        break;
    }
}

if (!$found) {
    echo json_encode(['status' => 'error', 'message' => "Gateway {$gwName} not found"]);
    exit(1);
}

$configObj->save();

// Trigger route reconfiguration so the force_down takes effect immediately
$backend = new \OPNsense\Core\Backend();
$backend->configdRun('interface routes reconfigure');

echo json_encode([
    'status' => 'ok',
    'gateway' => $gwName,
    'force_down' => $forceDown,
    'message' => "Gateway {$gwName} force_down set to {$forceDown}"
]);
