<?php

/*
 * proxygateway_interface_references() against a small config.xml.
 * Run: php tests/php/test_references.php  (prints JSON, exit 1 on failure)
 */

require_once __DIR__ . '/../../src/etc/inc/plugins.inc.d/proxygateway.inc';

$xml = simplexml_load_string(<<<'XML'
<?xml version="1.0"?>
<opnsense>
  <interfaces>
    <lan><if>igc1</if><descr>LAN</descr><enable>1</enable></lan>
    <opt7><if>pgw_China</if><descr>FRP</descr><enable>1</enable></opt7>
    <opt9><if>pgw_Spare</if><descr>Spare</descr></opt9>
  </interfaces>
  <OPNsense>
    <Gateways>
      <gateway_item><name>PROXYGW_CHINA</name><interface>opt7</interface></gateway_item>
      <gateway_item><name>MY_GW</name><interface>opt7</interface></gateway_item>
    </Gateways>
    <Firewall><Filter><rules>
      <rule><interface>lan</interface><gateway>FRP_GW</gateway></rule>
      <rule><interface>lan,opt7</interface><descr>see opt70 and FRP_GW6x</descr></rule>
    </rules></Filter></Firewall>
    <Approuter><rules>
      <rule><gateway>FRP_GW</gateway></rule>
      <rule><gateway>FRP_GW</gateway></rule>
      <rule><gateway>FRP_GW6x</gateway></rule>
    </rules></Approuter>
  </OPNsense>
</opnsense>
XML
);

$fails = [];
$check = function ($name, $ok) use (&$fails) {
    if (!$ok) {
        $fails[] = $name;
    }
};

$refs = proxygateway_interface_references($xml, 'opt7');
$check('own PROXYGW_ gateway and the assignment itself do not count',
    !in_array('Gateways/gateway_item/name', $refs, true) && count($refs) === 4);
$check('foreign gateway on the interface counts', in_array('OPNsense/Gateways/gateway_item/interface', $refs, true));
$check('dynamic gateway name FRP_GW counts, per place', in_array('OPNsense/Approuter/rules/rule/gateway (2x)', $refs, true)
    && in_array('OPNsense/Firewall/Filter/rules/rule/gateway', $refs, true));
$check('interface lists count', in_array('OPNsense/Firewall/Filter/rules/rule/interface', $refs, true));
$check('no substring matches (opt70, FRP_GW6x)', !preg_grep('/descr/', $refs));
$check('unused interface has no references', proxygateway_interface_references($xml, 'opt9') === []);
$check('unknown key', proxygateway_interface_references($xml, 'opt42') === []);

echo json_encode(['refs' => $refs, 'failures' => $fails], JSON_UNESCAPED_SLASHES), "\n";
exit($fails ? 1 : 0);
