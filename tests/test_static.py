"""Invariants between model, form, desired.json generator and scripts."""

import os
import re
import xml.etree.ElementTree as ET

import pgwconf
import watchdog

ROOT = os.path.join(os.path.dirname(__file__), '..')
SRC = os.path.join(ROOT, 'src')
SCRIPTS = os.path.join(SRC, 'opnsense', 'scripts', 'OPNsense', 'ProxyGateway')
MODEL = os.path.join(SRC, 'opnsense', 'mvc', 'app', 'models', 'OPNsense', 'ProxyGateway', 'ProxyGateway.xml')
FORM = os.path.join(SRC, 'opnsense', 'mvc', 'app', 'controllers', 'OPNsense', 'ProxyGateway', 'forms', 'connection.xml')
INC = os.path.join(SRC, 'etc', 'inc', 'plugins.inc.d', 'proxygateway.inc')


def read(path):
    with open(path) as f:
        return f.read()


def conn_model():
    return ET.parse(MODEL).getroot().find('items/connections/connection')


def test_setup_keeps_freebsd15_ifconfig_mask():
    assert 'ifconfig "$IFACE" inet "${TUN_LOCAL}/32" "$TUN_PEER"' in read(os.path.join(SCRIPTS, 'setup.sh'))


def test_setup_keeps_tun2socks_at_warn():
    setup = read(os.path.join(SCRIPTS, 'setup.sh'))
    assert 'T2S_LOGLEVEL="warn"' in setup
    assert setup.count('-loglevel "$T2S_LOGLEVEL"') == 2


def test_failback_threshold_default_matches_model():
    field = conn_model().find('failbackThreshold')
    assert field is not None and field.get('type') == 'IntegerField'
    assert int(field.findtext('default')) == watchdog.DEFAULT_FAILBACK_THRESHOLD
    assert int(conn_model().find('failoverThreshold').findtext('default')) == watchdog.DEFAULT_FAILOVER_THRESHOLD


def test_model_version_bumped():
    assert ET.parse(MODEL).getroot().findtext('version') == '0.4.2'


def test_form_fields_exist_in_model():
    fields = {c.tag for c in conn_model()}
    for f in ET.parse(FORM).getroot().iter('id'):
        assert f.text.split('.', 1)[1] in fields, f.text


def test_desired_json_carries_failback_threshold():
    assert "'failbackThreshold'   => (string)$conn->failbackThreshold" in read(INC)
    assert 'failbackThreshold' in pgwconf.HOT_KEYS


def test_healthcheck_sh_delegates_to_python():
    sh = read(os.path.join(SCRIPTS, 'healthcheck.sh'))
    assert re.search(r'exec /usr/local/bin/python3 .*healthcheck\.py" "\$@"', sh)


def test_no_old_default_target_left():
    for name in ('watchdog.py', 'pgwhealth.py', 'healthcheck.py'):
        assert not re.search(r'["\']http://1\.1\.1\.1/?["\']', read(os.path.join(SCRIPTS, name))), name


def test_speedtest_caps_download_and_requires_2xx():
    import pathlib
    s = pathlib.Path(__file__).resolve().parent.parent.joinpath(
        "src/opnsense/scripts/OPNsense/ProxyGateway/speedtest.sh").read_text()
    assert '--range "0-$((MAX_BYTES - 1))"' in s
    assert '[ "$HTTP_CODE" = "206" ]' in s
    assert '"$HTTP_CODE" != "000" ]; then' not in s


def test_tunnel_address_is_never_natted_on_upstream_interfaces():
    inc = read(INC)
    # a no-nat rule from the tunnel network on every upstream interface, ahead of the
    # plugin NAT rules (prio 100) and of automatic outbound NAT
    assert "registerSNatRule(50" in inc and "\x27nonat\x27       => true" in inc
    assert "\x27source\x27      => [\x27network\x27 => $intf_id]" in inc
    assert "function proxygateway_upstream_interfaces()" in inc and "pgw_" in inc


def test_cron_jobs_come_from_the_plugin_hook():
    # one cron mechanism: OPNsense's _cron() hook, no file in /etc/cron.d
    inc = read(INC)
    assert "function proxygateway_cron()" in inc
    assert "'/usr/local/sbin/configctl proxygateway watchdog 2>&1', '*'" in inc
    assert "'/usr/local/sbin/configctl proxygateway speedtestcron 2>&1', '*/5'" in inc
    assert not os.path.exists(os.path.join(SRC, 'etc', 'cron.d', 'proxygateway'))
    makefile = read(os.path.join(ROOT, 'Makefile'))
    assert 'cp src/etc/cron.d' not in makefile
    # upgrades drop the old file so the jobs do not run twice
    for path in (os.path.join(ROOT, 'Makefile'), os.path.join(ROOT, 'pkg', '+POST_INSTALL')):
        assert 'rm -f $(DESTDIR)/etc/cron.d/proxygateway' in read(path) or \
            'rm -f /etc/cron.d/proxygateway' in read(path)
    # Apply rewrites the crontab when enabling/disabling changed the jobs
    ctrl = read(os.path.join(SRC, 'opnsense', 'mvc', 'app', 'controllers', 'OPNsense',
                             'ProxyGateway', 'Api', 'ServiceController.php'))
    assert "proxygateway_cron_stale($mdl)" in ctrl and "configdRun('cron restart')" in ctrl
