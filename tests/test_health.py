"""pgwhealth.check()/record() with mocked curl, pfctl and ifconfig."""

import json
import os
import subprocess

import pytest

import pgwconf
import pgwhealth
from test_predictor import FILTER, NAT


ROUTE_DEFAULT = """   route to: 110.242.68.66
destination: 0.0.0.0
       mask: 0.0.0.0
    gateway: 198.18.0.1
        fib: 0
  interface: igc0
      flags: <UP,GATEWAY,DONE,STATIC>
"""
ROUTE_TUN = """   route to: 223.6.6.6
destination: 223.6.6.6
    gateway: 172.31.175.170
        fib: 0
  interface: pgw_China
      flags: <UP,GATEWAY,HOST,DONE,STATIC>
"""
ROUTE_OTHER = ROUTE_TUN.replace('pgw_China', 'wg0')


def resolver(host, port, family, kind):
    assert family == pgwhealth.socket.AF_INET
    return [(family, kind, 6, '', ('110.242.68.66', port))]


class FakeRun:
    """Records commands; answers curl with a given http code and route(8)
    according to ``route``: default (pin added), tun (already routed into
    the tunnel), other (specific route elsewhere), addfail."""

    def __init__(self, http_code='200', iface_ok=True, route='default'):
        self.calls = []
        self.http_code = http_code
        self.iface_ok = iface_ok
        self.route = route

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw.get('input')))
        if cmd[0] == pgwhealth.IFCONFIG:
            return subprocess.CompletedProcess(cmd, 0 if self.iface_ok else 1, '', '')
        if cmd[0] == pgwhealth.ROUTE:
            if cmd[2] == 'get':
                out = {'tun': ROUTE_TUN, 'other': ROUTE_OTHER}.get(self.route, ROUTE_DEFAULT)
                return subprocess.CompletedProcess(cmd, 0, out, '')
            rc = 1 if (cmd[2] == 'add' and self.route == 'addfail') else 0
            return subprocess.CompletedProcess(cmd, rc, '', '')
        if cmd[0] == pgwhealth.CURL:
            rc = 0 if self.http_code != '000' else 7
            return subprocess.CompletedProcess(cmd, rc, self.http_code, '' if rc == 0 else 'curl: (7) Failed')
        raise AssertionError(cmd)

    def curl(self):
        return [c for c in self.calls if c[0][0] == pgwhealth.CURL]

    def routes(self):
        return [c[0][1:] for c in self.calls if c[0][0] == pgwhealth.ROUTE]


@pytest.fixture
def rundir(tmp_path):
    d = tmp_path / 'run'
    d.mkdir()

    def make(proxy_type='socks5', url='socks5://user:p%40ss@192.168.70.1:1080', target=''):
        lines = [pgwconf.conf_line('IFACE', 'pgw_China'), pgwconf.conf_line('PROXY_TYPE', proxy_type),
                 pgwconf.conf_line('PROXY_URL', url), pgwconf.conf_line('TUN_LOCAL', '172.31.175.169'),
                 pgwconf.conf_line('TUN_PEER', '172.31.175.170')]
        if target:
            lines.append(pgwconf.conf_line('HEALTH_TARGET', target))
        (d / 'China.conf').write_text(''.join(lines))
        (d / 'China.pid').write_text('123\n')
        return str(d)
    return make


def run_check(rundir, run, pf=(NAT, FILTER), **kw):
    return pgwhealth.check('China', rundir=rundir, runner=run, pid_alive=lambda p: True,
                           pf_reader=lambda: pf, resolver=resolver, **kw)


def test_leak_predicted_probe_is_pinned_through_tunnel(rundir):
    """Router today: auto outbound NAT covers the tunnel address. The probe
    must still go through pgw_China: temporary host route via the peer."""
    run = FakeRun()
    r = run_check(rundir(), run)
    assert r['ok'] and r['mode'] == 'tun' and r['tun_path'] == 'nat_leak'
    assert r['verified'] and r['pinned'] == '110.242.68.66'
    (cmd, cfg), = run.curl()
    assert cmd[cmd.index('--interface') + 1] == 'pgw_China'
    assert cmd[cmd.index('--resolve') + 1] == 'www.baidu.com:443:110.242.68.66'
    assert cfg == ''                                  # not via the proxy
    assert run.routes() == [['-n', 'get', '110.242.68.66'],
                            ['-n', 'add', '-host', '110.242.68.66', '172.31.175.170'],
                            ['-n', 'delete', '-host', '110.242.68.66', '172.31.175.170']]
    # route added before curl, removed after
    kinds = [c[0][0] for c in run.calls]
    assert kinds.index(pgwhealth.CURL) < len(kinds) - 1 and run.calls[-1][0][2] == 'delete'


def test_pin_route_removed_even_when_curl_raises(rundir):
    run = FakeRun()
    orig = run.__call__

    class Boom(Exception):
        pass

    def call(cmd, **kw):
        if cmd[0] == pgwhealth.CURL:
            run.calls.append((cmd, None))
            raise Boom()
        return orig(cmd, **kw)
    with pytest.raises(Boom):
        run_check(rundir(), call)
    assert run.routes()[-1][1] == 'delete'


def test_existing_tunnel_route_is_used_not_touched(rundir):
    run = FakeRun(route='tun')
    r = run_check(rundir(), run)
    assert r['verified'] and r['mode'] == 'tun'
    assert run.routes() == [['-n', 'get', '110.242.68.66']]


@pytest.mark.parametrize('route', ['other', 'addfail'])
def test_unpinnable_falls_back_to_proxy_unverified(rundir, route):
    run = FakeRun(route=route)
    r = run_check(rundir(), run)
    assert r['ok'] and r['mode'] == 'proxy' and r['tun_path'] == 'nat_leak'
    assert not r['verified'] and r['pin_error']
    assert all(c[1] != 'delete' for c in run.routes())
    (cmd, cfg), = run.curl()
    assert '--interface' not in cmd
    assert cmd[-1] == pgwhealth.DEFAULT_TARGET
    assert cfg.startswith('proxy = "socks5h://user:p%40ss@192.168.70.1:1080"')
    # credentials never on argv and masked in the result
    assert not any('p%40ss' in a for a in cmd)
    assert '***@' in r['via']


def test_tun_path_ok_probes_through_interface(rundir):
    run = FakeRun()
    nat = 'no nat on igc0 inet from 172.31.175.169 to any\n' + NAT
    r = run_check(rundir(target='https://www.iqiyi.com/'), run, pf=(nat, FILTER))
    assert r['ok'] and r['mode'] == 'tun' and r['tun_path'] == 'ok' and r['verified']
    assert run.routes() == [] and '--resolve' not in run.curl()[0][0]
    (cmd, cfg), = run.curl()
    assert cmd[cmd.index('--interface') + 1] == 'pgw_China'
    assert cmd[-1] == 'https://www.iqiyi.com/'
    assert cfg == ''


def test_ss_pinned_and_unpinnable_unverified(rundir):
    run = FakeRun()
    r = run_check(rundir(proxy_type='ss', url='ss://aes:pw@1.2.3.4:8388'), run)
    assert r['mode'] == 'tun' and r['verified'] and r['pinned']
    run = FakeRun(route='addfail')
    r = run_check(rundir(proxy_type='ss', url='ss://aes:pw@1.2.3.4:8388'), run)
    assert r['mode'] == 'tun' and r['tun_path'] == 'nat_leak' and not r['verified']
    assert '--interface' in run.curl()[0][0] and '--resolve' not in run.curl()[0][0]


def test_unresolvable_target_is_unverified(rundir):
    run = FakeRun()
    r = pgwhealth.check('China', rundir=rundir(), runner=run, pid_alive=lambda p: True,
                        pf_reader=lambda: (NAT, FILTER), resolver=lambda *a: [])
    assert r['mode'] == 'proxy' and not r['verified'] and 'resolve' in r['pin_error']


def test_ip_literal_target_needs_no_dns(rundir):
    run = FakeRun()
    r = pgwhealth.check('China', rundir=rundir(target='https://223.6.6.6/resolve?name=x'), runner=run,
                        pid_alive=lambda p: True, pf_reader=lambda: (NAT, FILTER),
                        resolver=lambda *a: pytest.fail('resolver called'))
    assert r['pinned'] == '223.6.6.6'


def test_failed_probe(rundir):
    r = run_check(rundir(), FakeRun(http_code='000'))
    assert not r['ok'] and r['status'] == 'down' and r['reason'] == 'probe_failed' and r['verified']
    r = run_check(rundir(), FakeRun(http_code='000', route='addfail'))
    assert not r['ok'] and r['reason'] == 'proxy_unreachable' and not r['verified']


def test_socks_step():
    run = FakeRun()
    conf = {'PROXY_TYPE': 'socks5', 'PROXY_URL': 'socks5h://192.168.70.1:1080'}
    assert pgwhealth.socks_step(conf, runner=run) == 'up'
    (cmd, cfg), = run.curl()
    assert '--interface' not in cmd and cfg.startswith('proxy = "socks5h://192.168.70.1:1080"')
    assert pgwhealth.socks_step(conf, runner=FakeRun(http_code='000')) == 'down'
    assert pgwhealth.socks_step({'PROXY_TYPE': 'ss', 'PROXY_URL': 'ss://x'}, runner=run) == 'unknown'


def test_any_http_code_is_healthy(rundir):
    assert run_check(rundir(), FakeRun(http_code='503'))['ok']


def test_dead_process_and_missing_interface(rundir):
    d = rundir()
    r = pgwhealth.check('China', rundir=d, runner=FakeRun(), pid_alive=lambda p: False,
                        pf_reader=lambda: (NAT, FILTER))
    assert r['reason'] == 'process_dead' and not r['mode']
    r = run_check(d, FakeRun(iface_ok=False))
    assert r['reason'] == 'no_interface'


def test_bad_target_rejected(rundir):
    r = run_check(rundir(target='file:///etc/passwd'), FakeRun())
    assert r['status'] == 'error'


def test_record_writes_status_log_and_history(rundir, tmp_path):
    d = rundir()
    logdir = tmp_path / 'log'
    r = run_check(d, FakeRun(route='addfail'))
    line = pgwhealth.record('China', r, 1795253581, rundir=d, logdir=str(logdir))
    status = dict(l.split('=', 1) for l in open(os.path.join(d, 'China.status')).read().splitlines())
    assert status['status'] == 'up' and status['mode'] == 'proxy' and status['tun_path'] == 'nat_leak'
    assert status['verified'] == '0' and status['pin_error'] == 'route add failed'
    assert status['timestamp'] == '1795253581' and 'latency_ms' in status
    assert 'p%40ss' not in status['probe']
    hist = json.loads((logdir / 'China_health.log').read_text().splitlines()[-1])
    assert hist == {'timestamp': 1795253581, 'name': 'China', 'status': 'up',
                    'latency_ms': r['latency_ms'], 'http_code': '200', 'mode': 'proxy'}
    assert '[healthcheck]' in line and 'Healthy' in line and 'p%40ss' not in line
    assert 'UNVERIFIED' in line
    assert (logdir / 'China.log').read_text().strip() == line


def test_record_pinned_status(rundir, tmp_path):
    d = rundir()
    line = pgwhealth.record('China', run_check(d, FakeRun()), 1, rundir=d, logdir=str(tmp_path))
    status = dict(l.split('=', 1) for l in open(os.path.join(d, 'China.status')).read().splitlines())
    assert status['verified'] == '1' and status['pinned'] == '110.242.68.66' and status['mode'] == 'tun'
    assert 'UNVERIFIED' not in line and 'pinned:110.242.68.66' in line


def test_record_failure_has_curl_exit(rundir, tmp_path):
    d = rundir()
    r = run_check(d, FakeRun(http_code='000'))
    pgwhealth.record('China', r, 1, rundir=d, logdir=str(tmp_path))
    status = open(os.path.join(d, 'China.status')).read()
    assert 'status=down' in status and 'reason=probe_failed' in status and 'curl_exit=7' in status
    hist = json.loads((tmp_path / 'China_health.log').read_text())
    assert hist['status'] == 'down' and hist['curl_exit'] == 7


def test_record_dead_process_has_no_history(rundir, tmp_path):
    d = rundir()
    r = pgwhealth.check('China', rundir=d, runner=FakeRun(), pid_alive=lambda p: False,
                        pf_reader=lambda: (NAT, FILTER))
    pgwhealth.record('China', r, 1, rundir=d, logdir=str(tmp_path))
    assert 'reason=process_dead' in open(os.path.join(d, 'China.status')).read()
    assert not (tmp_path / 'China_health.log').exists()


def test_build_proxy_url_encodes_credentials():
    assert pgwhealth.build_proxy_url('socks5', 'h', '1', 'u@x', 'p:w') == 'socks5h://u%40x:p%3Aw@h:1'
    assert pgwhealth.build_proxy_url('http', 'h', '8080') == 'http://h:8080'
    assert pgwhealth.build_proxy_url('ss', 'h', '1') == ''


def test_cli_validates_name(capsys):
    import healthcheck
    assert healthcheck.main(['x', 'bad name;rm']) == 1
    assert healthcheck.main(['x']) == 1
