#!/usr/local/bin/php
<?php

/*
 * sync_interfaces.php - Sync proxy gateway interface IPs in OPNsense config.
 *
 * Called by configd to ensure assigned pgw_* interfaces have the correct
 * IP address in config.xml. Without this, OPNsense's gateway system sees
 * the interface as having no IP and marks the gateway as "defunct".
 *
 * This must run AFTER setup.sh creates TUN devices and BEFORE route
 * reconfiguration, so the gateway system detects functional gateways.
 */

require_once("config.inc");
require_once("interfaces.inc");
require_once("plugins.inc.d/proxygateway.inc");

proxygateway_sync_interfaces();

echo json_encode(['status' => 'ok']) . "\n";
