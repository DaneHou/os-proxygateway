<?php

/*
 * leftovers.php — list what uninstalling leaves in config.xml.
 *
 * Uninstall does not edit config.xml: removing an interface assignment or a
 * gateway that firewall rules still use would break the live ruleset. This
 * only prints the pgw_* assignments and PROXYGW_* gateways that remain, so
 * the admin can remove them in the GUI once nothing uses them.
 * Standalone on purpose (no plugin code): pkg runs it after the files are gone.
 */

$xml = @simplexml_load_file('/conf/config.xml');
if ($xml === false) {
    exit(0);
}
$left = [];
foreach ($xml->interfaces->children() as $key => $iface) {
    $dev = (string)$iface->{'if'};
    if (strpos($dev, 'pgw_') === 0) {
        $descr = (string)$iface->descr;
        $left[] = "interface {$key} ({$dev}" . ($descr !== '' ? ", {$descr}" : '') . ')'
            . " -> Interfaces > Assignments";
    }
}
foreach ([$xml->gateways ?? null, $xml->OPNsense->Gateways ?? null, $xml->Gateways ?? null] as $section) {
    if ($section === null) {
        continue;
    }
    foreach ($section->children() as $gw) {
        $name = (string)$gw->name;
        if (strpos($name, 'PROXYGW_') === 0) {
            $left[] = "gateway {$name} -> System > Gateways > Configuration";
        }
    }
}
if (!empty($left)) {
    echo "Note: os-proxygateway left these in config.xml (not removed automatically, rules may still use them):\n";
    foreach ($left as $line) {
        echo "  - {$line}\n";
    }
}
