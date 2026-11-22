"""configctl proxygateway healthcheck: os-netbaseline plugin health contract, read-only."""

import configparser
import json
import os
import re
import types

import plugin_health

ROOT = os.path.join(os.path.dirname(__file__), '..')
SRC = os.path.join(ROOT, 'src')
ACTIONS = os.path.join(SRC, 'opnsense', 'service', 'conf', 'actions.d', 'actions_proxygateway.conf')
SCRIPTS = os.path.join(SRC, 'opnsense', 'scripts', 'OPNsense', 'ProxyGateway')
DIAG = os.path.join(SRC, 'opnsense', 'mvc', 'app', 'controllers', 'OPNsense', 'ProxyGateway', 'Api',
                    'DiagnosticsController.php')
NOW = 1795300000

CONFIG = """<opnsense><OPNsense><ProxyGateway>
  <general><enabled>{enabled}</enabled></general>
  <connections>
    <connection uuid="1"><enabled>1</enabled><name>China</name><healthCheckEnabled>1</healthCheckEnabled>
      <proxyServer>203.0.113.9</proxyServer><authPass>s3cretPass</authPass></connection>
    <connection uuid="2"><enabled>0</enabled><name>Off</name></connection>
    <connection uuid="3"><enabled>1</enabled><name>NoProbe</name><healthCheckEnabled>0</healthCheckEnabled></connection>
  </connections>
</ProxyGateway></OPNsense></opnsense>"""

GWS = {'gateways': [
    {'name': 'WAN_DHCP', 'device': 'igc0', 'disabled': False, 'force_down': False, 'monitor_disable': True, 'status': 'none'},
    {'name': 'CHINA_GW', 'device': 'pgw_China', 'disabled': False, 'force_down': False, 'monitor_disable': True,
     'status': 'none'}]}

UP = 'pgw_China: flags=1008043<UP,BROADCAST,RUNNING,MULTICAST,LOWER_UP> metric 0 mtu 1500\n'


class Runner:
    def __init__(self, ifaces=None, gws=GWS):
        self.ifaces = {'pgw_China': UP, 'pgw_NoProbe': UP} if ifaces is None else ifaces
        self.gws = gws
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        if argv[0] == plugin_health.IFCONFIG:
            out = self.ifaces.get(argv[1])
            return types.SimpleNamespace(returncode=0 if out else 1, stdout=out or '')
        if argv[0] == '/usr/local/bin/php':
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(self.gws) if self.gws else 'Fatal')
        raise AssertionError('unexpected command %s' % argv)


def world(tmp_path, enabled='1', status='status=up\nlatency_ms=120\nmode=tun\ntun_path=ok\ntimestamp=%d\n' % (NOW - 60),
          failover=None, pid=True):
    cfg = tmp_path / 'config.xml'
    cfg.write_text(CONFIG.format(enabled=enabled))
    run = tmp_path / 'run'
    run.mkdir()
    if pid:
        (run / 'China.pid').write_text(str(os.getpid()))
        (run / 'NoProbe.pid').write_text(str(os.getpid()))
    if status is not None:
        (run / 'China.status').write_text(status)
    if failover is not None:
        (run / 'China.failover').write_text(json.dumps(failover))
    return str(cfg), str(run)


def checks(tmp_path, runner=None, **kw):
    cfg, run = world(tmp_path, **kw)
    out = plugin_health.build(cfg, run, runner or Runner(), now=NOW)
    return {c['name']: c for c in out['checks']}, out


def test_action_is_the_parameterless_contract_action_and_probe_is_separate():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ACTIONS)
    hc = cp['healthcheck']
    assert hc['type'] == 'script_output' and not hc.get('parameters', '').strip()
    assert hc['command'].endswith('/plugin_health.py')
    assert cp['probe']['command'].endswith('/healthcheck.sh') and cp['probe']['parameters'] == '%s'
    assert 'proxygateway probe {$name}' in open(DIAG).read()
    assert 'proxygateway healthcheck {' not in open(DIAG).read()


def test_all_good(tmp_path):
    c, out = checks(tmp_path)
    assert sorted(c) == ['China: connectivity', 'China: gateway', 'China: interface', 'China: tun2socks',
                         'NoProbe: connectivity', 'NoProbe: gateway', 'NoProbe: interface', 'NoProbe: tun2socks']
    assert c['China: gateway'] == {'name': 'China: gateway', 'ok': True, 'severity': 'medium',
                                   'detail': 'CHINA_GW online (monitoring disabled)'}
    assert c['China: connectivity']['ok'] is True and '120 ms' in c['China: connectivity']['detail']
    assert c['NoProbe: connectivity']['ok'] is None and c['NoProbe: connectivity']['severity'] == 'info'
    assert c['NoProbe: gateway']['ok'] is False and c['NoProbe: gateway']['severity'] == 'low'
    for x in out['checks']:
        assert set(x) == {'name', 'ok', 'severity', 'detail'}
        assert x['ok'] in (True, False, None) and x['severity'] in ('medium', 'low', 'info')
    text = json.dumps(out)
    assert 's3cretPass' not in text and '203.0.113.9' not in text


def test_process_and_interface_down(tmp_path):
    c, _ = checks(tmp_path, runner=Runner(ifaces={}), pid=False)
    assert c['China: tun2socks'] == {'name': 'China: tun2socks', 'ok': False, 'severity': 'medium',
                                     'detail': 'not started (no pid file)'}
    assert c['China: interface']['ok'] is False and 'does not exist' in c['China: interface']['detail']
    (tmp_path / 'b').mkdir()
    c, _ = checks(tmp_path / 'b', runner=Runner(ifaces={'pgw_China': 'pgw_China: flags=8002<BROADCAST,MULTICAST> mtu 1500\n'}))
    assert c['China: interface']['ok'] is False and 'not up' in c['China: interface']['detail']


def test_stale_pid(tmp_path):
    cfg, run = world(tmp_path)
    open(os.path.join(run, 'China.pid'), 'w').write('99999999')
    c = {x['name']: x for x in plugin_health.build(cfg, run, Runner(), now=NOW)['checks']}
    assert c['China: tun2socks']['ok'] is False and 'stale' in c['China: tun2socks']['detail']


def test_probe_failed_stale_and_missing(tmp_path):
    c, _ = checks(tmp_path, status='status=down\nreason=http_000\ntimestamp=%d\n' % (NOW - 60))
    assert c['China: connectivity']['ok'] is False and '(http_000)' in c['China: connectivity']['detail']
    (tmp_path / 'b').mkdir()
    c, _ = checks(tmp_path / 'b', status='status=up\nlatency_ms=9\ntimestamp=%d\n' % (NOW - 3600))
    assert c['China: connectivity']['ok'] is False and c['China: connectivity']['severity'] == 'low'
    assert '60 min old' in c['China: connectivity']['detail']
    (tmp_path / 'c').mkdir()
    c, _ = checks(tmp_path / 'c', status=None)
    assert c['China: connectivity']['ok'] is None


def test_failover_states(tmp_path):
    c, _ = checks(tmp_path, failover={'active_proxy': 'primary', 'forced_down': True})
    assert c['China: failover']['ok'] is False and c['China: failover']['severity'] == 'medium'
    (tmp_path / 'b').mkdir()
    c, _ = checks(tmp_path / 'b', failover={'active_proxy': 'backup', 'forced_down': False})
    assert c['China: failover']['ok'] is False and c['China: failover']['severity'] == 'info'
    (tmp_path / 'c').mkdir()
    c, _ = checks(tmp_path / 'c', failover={'active_proxy': 'primary', 'forced_down': False})
    assert 'China: failover' not in c


def test_gateway_states(tmp_path):
    gws = json.loads(json.dumps(GWS))
    gws['gateways'][1]['status'] = 'down'
    c, _ = checks(tmp_path, runner=Runner(gws=gws))
    assert c['China: gateway']['ok'] is False and c['China: gateway']['detail'] == 'CHINA_GW status down'
    gws['gateways'][1].update(status='none', force_down=True)
    (tmp_path / 'b').mkdir()
    c, _ = checks(tmp_path / 'b', runner=Runner(gws=gws))
    assert c['China: gateway']['detail'] == 'CHINA_GW is forced down'
    (tmp_path / 'c').mkdir()
    c, _ = checks(tmp_path / 'c', runner=Runner(gws=None))
    assert c['China: gateway']['ok'] is None


def test_disabled_plugin_and_no_connections(tmp_path):
    _, out = checks(tmp_path, enabled='0')
    assert out == {'checks': []}
    cfg = tmp_path / 'empty.xml'
    cfg.write_text('<opnsense><OPNsense><ProxyGateway><general><enabled>1</enabled></general>'
                   '</ProxyGateway></OPNsense></opnsense>')
    out = plugin_health.build(str(cfg), str(tmp_path), Runner(), now=NOW)
    assert out['checks'][0]['ok'] is None
    out = plugin_health.build(str(tmp_path / 'missing.xml'), str(tmp_path), Runner(), now=NOW)
    assert out['checks'][0]['ok'] is None


def test_only_read_only_commands():
    """No curl/setup/teardown/configctl writes: ifconfig <iface> and the gateway reader only."""
    text = open(os.path.join(SCRIPTS, 'plugin_health.py')).read().split('"""', 2)[2]     # code, not docstring
    for bad in ('curl', 'setup.sh', 'teardown.sh', 'forcedown', 'configctl', 'open(', "'w'", '"w"'):
        if bad == 'open(':
            assert text.count('open(') == 1          # _read() only
            continue
        assert bad not in text, bad
    php = open(os.path.join(SCRIPTS, 'gateway_health.php')).read()
    assert not re.search(r'->save\(|file_put_contents|configdRun|exec\(|system\(', php)
