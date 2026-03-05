#!/usr/local/bin/php
<?php

/*
 * generate_desired.php - Generate desired.json from MVC model.
 *
 * Reads the proxy gateway model and writes /var/run/proxygateway/desired.json.
 * Called during boot (from rc.d start) when desired.json is missing because
 * /var/run/ is tmpfs and was wiped on reboot.
 */

require_once("config.inc");
require_once("plugins.inc.d/proxygateway.inc");

if (!proxygateway_enabled()) {
    echo json_encode(['status' => 'ok', 'connections' => 0, 'message' => 'plugin disabled']) . "\n";
    exit(0);
}

$mdl = new \OPNsense\ProxyGateway\ProxyGateway();
proxygateway_generate_desired($mdl);

$count = 0;
foreach ($mdl->connections->connection->iterateItems() as $uuid => $conn) {
    $count++;
}

echo json_encode(['status' => 'ok', 'connections' => $count]) . "\n";
