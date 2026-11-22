"""Watchdog tunnel repair, gateway resolution, local proxy service detection,
restartconn action and the healthcheck "fix" field."""

import configparser
import json
import os
import subprocess
import types

import pytest

import pgwrepair
import plugin_health
import watchdog

ROOT = os.path.join(os.path.dirname(__file__), '..')
SCRIPTS = os.path.join(ROOT, 'src', 'opnsense', 'scripts', 'OPNsense', 'ProxyGateway')
ACTIONS = os.path.join(ROOT, 'src', 'opnsense', 'service', 'conf', 'actions.d', 'actions_proxygateway.conf')

# The live router: China on sslocal at the router's LAN address, no backup,
# gateway FRP_GW (user-made, dynamic) on the assigned interface opt7.
CONN = {'name': 'China', 'enabled': '1', 'proxyType': 'socks5', 'proxyServer': '192.168.70.1',
        'proxyPort': '1080', 'authEnabled': '0', 'backupEnabled': '0', 'failoverThreshold': '3',
        'autoForceDown': '1', 'healthCheckEnabled': '1'}
GWS = [
    {'name': 'WAN_DHCP', 'interface': 'wan', 'device': 'igc0', 'disabled': False},
    {'name': 'FRP_GW', 'interface': 'opt7', 'device': 'pgw_China', 'disabled': False, 'status': 'none'},
    {'name': 'WAN_DHCP6', 'interface': 'wan', 'device': 'igc0', 'disabled': True},
]

TUN_OK = {'ok': True, 'verified': True, 'mode': 'tun', 'tun_path': 'nat_leak', 'pinned': '1.2.3.4'}
TUN_FAIL = {'ok': False, 'verified': True, 'mode': 'tun', 'tun_path': 'nat_leak', 'reason': 'probe_failed'}
UNVERIFIED = {'ok': True, 'verified': False, 'mode': 'proxy', 'tun_path': 'nat_leak',
              'pin_error': 'route add failed'}


class FakeSyslog:
    LOG_PID, LOG_DAEMON = 1, 24
    LOG_ERR, LOG_WARNING, LOG_NOTICE, LOG_INFO = 3, 4, 5, 6

    def __init__(self):
        self.lines = []

    def openlog(self, ident, opt, fac):
        assert ident == 'proxygateway'

    def syslog(self, prio, msg):
        self.lines.append((prio, msg))


class World:
    def __init__(self, monkeypatch, tmp_path):
        self.dir = tmp_path
        self.socks = 'up'
        self.service = ('sslocal-rust', 'sslocal (pid 76031)')
        self.tunnel_restarts = []
        self.service_restarts = []
        self.forced = []
        self.syslog = FakeSyslog()
        monkeypatch.setattr(watchdog, 'RUNDIR', str(tmp_path))
        monkeypatch.setattr(watchdog, 'DRY_RUN', False)
        monkeypatch.setattr(watchdog.time, 'sleep', lambda s: None)
        monkeypatch.setattr(watchdog, 'check_connection', lambda name: True)
        monkeypatch.setattr(watchdog, 'restart_tunnel', self._restart_tunnel)
        monkeypatch.setattr(watchdog, 'force_down_gateway', lambda n, d: self.forced.append(d) or True)
        monkeypatch.setattr(watchdog.pgwhealth, 'socks_step', lambda conf: self.socks)
        monkeypatch.setattr(pgwrepair, 'local_proxy_service', lambda addr, port: self.service)
        monkeypatch.setattr(pgwrepair, 'restart_service', self._restart_service)
        monkeypatch.setattr(pgwrepair, 'load_gateways', lambda: GWS)
        monkeypatch.setattr(pgwrepair, 'syslog', self.syslog)
        monkeypatch.setattr(pgwrepair, '_SYSLOG_PRIO', {10: 5, 20: 5, 30: 4, 40: 3})

    def _restart_tunnel(self, name, conn, to_backup):
        self.tunnel_restarts.append(to_backup)
        return True

    def _restart_service(self, svc):
        self.service_restarts.append(svc)
        return True

    def tick(self, result, now, conn=CONN, failover=None):
        return watchdog.check_repair('China', conn, result, failover, now=now, rundir=str(self.dir))

    def state(self):
        return json.loads((self.dir / 'China.repair').read_text())


@pytest.fixture
def world(monkeypatch, tmp_path):
    return World(monkeypatch, tmp_path)


# ---------------------------------------------------------------- gateways

def test_resolve_gateways_by_device_and_owned_name():
    r = pgwrepair.resolve_gateways('China', GWS)
    assert [g['name'] for g in r] == ['FRP_GW'] and not r[0]['owned']
    gws = GWS + [{'name': 'PROXYGW_CHINA', 'device': 'pgw_China', 'disabled': False}]
    assert [(g['name'], g['owned']) for g in pgwrepair.resolve_gateways('China', gws)] == \
        [('FRP_GW', False), ('PROXYGW_CHINA', True)]
    # PROXYGW_ by name even when the device is not reported (interface down)
    assert pgwrepair.resolve_gateways('China', [{'name': 'PROXYGW_CHINA', 'device': ''}])[0]['owned']
    assert pgwrepair.resolve_gateways('Other', GWS) == []


def test_foreign_gateway_is_never_forced_down(world):
    """Bug 1: force-down looked for PROXYGW_CHINA, which does not exist here,
    and retried every minute. Now: FRP_GW is resolved but not edited."""
    for i in range(6):
        watchdog.check_failover('China', CONN, False, now=1000 + 60 * i)
    assert world.forced == []
    fo = json.loads((world.dir / 'China.failover').read_text())
    assert fo['forced_down'] is False and fo['force_down_skipped'] == 'FRP_GW'
    notes = [m for _, m in world.syslog.lines if 'not managed by Proxy Gateway' in m]
    assert len(notes) == 1 and 'FRP_GW' in notes[0]
    watchdog.check_failover('China', CONN, True, now=2000)
    assert 'force_down_skipped' not in json.loads((world.dir / 'China.failover').read_text())


def test_owned_gateway_still_forced_down(world, monkeypatch):
    monkeypatch.setattr(pgwrepair, 'load_gateways',
                        lambda: GWS + [{'name': 'PROXYGW_CHINA', 'device': 'pgw_China', 'disabled': False}])
    for i in range(3):
        watchdog.check_failover('China', CONN, False, now=1000 + 60 * i)
    assert world.forced == [True]
    watchdog.check_failover('China', CONN, True, now=2000)
    assert world.forced == [True, False]


def test_gateway_list_unavailable_postpones(world, monkeypatch):
    monkeypatch.setattr(pgwrepair, 'load_gateways', lambda: None)
    for i in range(4):
        watchdog.check_failover('China', CONN, False, now=1000 + 60 * i)
    assert world.forced == []


# ---------------------------------------------------------------- repair

def test_n_failures_then_tun2socks_restart_with_backoff_and_cap(world):
    t = 10000
    world.tick(TUN_FAIL, t)
    world.tick(TUN_FAIL, t + 60)
    assert world.tunnel_restarts == []
    world.tick(TUN_FAIL, t + 120)                         # 3rd: repair
    assert world.tunnel_restarts == [False] and world.service_restarts == []
    s = world.state()
    assert s['restarts'] == [t + 120] and s['next_allowed'] == t + 120 + 120
    assert s['last_action'] == 'tun2socks' and s['last_result'] == 'ok' and s['tunnel_failures'] == 0
    # still broken: 3 more failures, but 2 min backoff after the first restart
    world.tick(TUN_FAIL, t + 180)
    world.tick(TUN_FAIL, t + 200)
    world.tick(TUN_FAIL, t + 220)
    assert len(world.tunnel_restarts) == 1 and world.state()['tunnel_failures'] == 3
    world.tick(TUN_FAIL, t + 240)                         # backoff over -> 2nd restart
    assert len(world.tunnel_restarts) == 2 and world.state()['next_allowed'] == t + 240 + 240
    for i in range(3):
        world.tick(TUN_FAIL, t + 480 + i)
    assert len(world.tunnel_restarts) == 3 and world.state()['next_allowed'] == t + 482 + 480
    for i in range(10):                                   # 4th within the hour: capped
        world.tick(TUN_FAIL, t + 1000 + 60 * i)
    assert len(world.tunnel_restarts) == 3
    assert any('cap reached' in m for _, m in world.syslog.lines)
    for i in range(3):                                    # an hour after the first restart
        world.tick(TUN_FAIL, t + 120 + 3600 + i)
    assert len(world.tunnel_restarts) == 4


def test_socks_step_failing_restarts_local_proxy_service(world):
    world.socks = 'down'
    for i in range(3):
        world.tick(TUN_FAIL, 1000 + 60 * i)
    assert world.tunnel_restarts == [] and world.service_restarts == ['sslocal-rust']
    assert world.state()['last_action'] == 'service:sslocal-rust'


def test_socks_step_failing_nothing_local_waits_without_using_cap(world):
    world.socks = 'down'
    world.service = ('', 'proxy 203.0.113.9 is not on this router')
    for i in range(3):
        world.tick(TUN_FAIL, 1000 + 60 * i)
    s = world.state()
    assert world.tunnel_restarts == [] and world.service_restarts == []
    assert s['restarts'] == [] and s['last_result'] == 'upstream_down' and s['next_allowed'] == 1120 + 120


def test_unprobeable_proxy_type_restarts_tun2socks(world):
    world.socks = 'unknown'
    for i in range(3):
        world.tick(TUN_FAIL, 1000 + 60 * i)
    assert world.tunnel_restarts == [False]


def test_backup_active_restarts_on_backup(world):
    for i in range(3):
        world.tick(TUN_FAIL, 1000 + 60 * i, failover={'active_proxy': 'backup'})
    assert world.tunnel_restarts == [True]


def test_unverified_probe_is_neither_success_nor_failure(world):
    """Bug 2: a nat_leak probe used to count as a healthy tunnel."""
    world.tick(TUN_FAIL, 1000)
    world.tick(TUN_FAIL, 1060)
    for i in range(5):
        world.tick(UNVERIFIED, 1100 + i)
    assert world.state()['tunnel_failures'] == 2 and world.tunnel_restarts == []
    assert sum('did not traverse the tunnel' in m for _, m in world.syslog.lines) == 1
    world.tick(TUN_FAIL, 1200)
    assert world.tunnel_restarts == [False]


def test_success_resets_counter(world):
    world.tick(TUN_FAIL, 1000)
    world.tick(TUN_FAIL, 1060)
    world.tick(TUN_OK, 1120)
    world.tick(TUN_FAIL, 1180)
    assert world.state()['tunnel_failures'] == 1 and world.tunnel_restarts == []


def test_missing_interface_counts_as_tunnel_failure():
    assert watchdog.tunnel_verdict({'ok': False, 'reason': 'no_interface', 'mode': ''}) == 'failed'
    assert watchdog.tunnel_verdict({'ok': False, 'reason': 'process_dead', 'mode': ''}) == 'unverified'
    assert watchdog.tunnel_verdict(UNVERIFIED) == 'unverified'
    assert watchdog.tunnel_verdict(TUN_OK) == 'ok' and watchdog.tunnel_verdict(TUN_FAIL) == 'failed'


def test_repair_steps_go_to_syslog_at_notice_or_higher(world):
    for i in range(3):
        world.tick(TUN_FAIL, 1000 + 60 * i)
    msgs = [m for _, m in world.syslog.lines]
    assert any('starting repair' in m for m in msgs)
    assert any('SOCKS step' in m and ': up' in m for m in msgs)
    assert any('restarting tun2socks' in m for m in msgs)
    assert any('repair tun2socks done' in m for m in msgs)
    assert all(p <= FakeSyslog.LOG_NOTICE for p, _ in world.syslog.lines)
    assert all(m.startswith('watchdog: China: ') for m in msgs)


def test_failed_restart_is_recorded(world, monkeypatch):
    monkeypatch.setattr(watchdog, 'restart_tunnel', lambda *a: False)
    for i in range(3):
        world.tick(TUN_FAIL, 1000 + 60 * i)
    assert world.state()['last_result'] == 'failed'
    assert any(p == FakeSyslog.LOG_ERR and 'FAILED' in m for p, m in world.syslog.lines)


def test_dry_run_repair_changes_nothing(world, monkeypatch):
    monkeypatch.setattr(watchdog, 'DRY_RUN', True)
    for i in range(5):
        world.tick(TUN_FAIL, 1000 + 60 * i)
    assert world.tunnel_restarts == [] and not (world.dir / 'China.repair').exists()
    assert world.syslog.lines == []


def test_active_proxy_conf_never_leaks_into_logs():
    conn = dict(CONN, authEnabled='1', authUser='u', authPass='p@ss')
    backup, server, port, conf = watchdog.active_proxy_conf(conn, None)
    assert not backup and server == '192.168.70.1' and port == '1080'
    assert conf['PROXY_URL'] == 'socks5h://u:p%40ss@192.168.70.1:1080'
    conn.update(backupProxyType='http', backupProxyServer='10.0.0.2', backupProxyPort='3128')
    backup, server, _, conf = watchdog.active_proxy_conf(conn, {'active_proxy': 'backup'})
    assert backup and server == '10.0.0.2' and conf['PROXY_URL'] == 'http://10.0.0.2:3128'


def test_main_skips_repair_when_failover_switched(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(watchdog, 'RUNDIR', str(tmp_path))
    monkeypatch.setattr(watchdog, 'setup_logging', lambda *a: None)
    monkeypatch.setattr(watchdog, 'get_enabled_connections', lambda: {'China': dict(CONN, backupEnabled='1')})
    monkeypatch.setattr(watchdog, 'check_connection', lambda n: True)
    monkeypatch.setattr(watchdog, 'run_healthcheck', lambda n: TUN_FAIL)

    def fake_failover(name, conn, ok):
        calls.append('failover')
        return dict(watchdog.load_failover_state(name), switch_count=1)
    monkeypatch.setattr(watchdog, 'check_failover', fake_failover)
    monkeypatch.setattr(watchdog, 'check_repair', lambda *a, **k: calls.append('repair'))
    watchdog.main([])
    assert calls == ['failover']
    monkeypatch.setattr(watchdog, 'check_failover', lambda n, c, ok: watchdog.load_failover_state(n))
    watchdog.main([])
    assert calls == ['failover', 'repair']


# ---------------------------------------------------------------- local proxy service

SOCKSTAT = """USER     COMMAND    PID   FD  PROTO  LOCAL ADDRESS         FOREIGN ADDRESS
root     sslocal    76031 13  tcp4   *:1080                *:*
"""


def fake_runner(sockstat=SOCKSTAT, binary='/usr/local/bin/sslocal -c /usr/local/etc/shadowsocks-rust/local.json'):
    def run(argv, **kw):
        if argv[0] == pgwrepair.SOCKSTAT:
            return types.SimpleNamespace(returncode=0, stdout=sockstat)
        if argv[0] == pgwrepair.PS:
            assert argv[1:3] == ['-p', '76031']
            return types.SimpleNamespace(returncode=0, stdout=binary + '\n')
        raise AssertionError(argv)
    return run


@pytest.fixture
def rcdir(tmp_path):
    d = tmp_path / 'rc.d'
    d.mkdir()
    (d / 'sslocal-rust').write_text('name="sslocal_rust"\nprocname=/usr/local/bin/sslocal\n'
                                    'command="/usr/sbin/daemon"\n')
    (d / 'openssh').write_text('name="openssh"\ncommand="/usr/local/sbin/sshd"\n')
    return str(d)


def test_local_proxy_service_found(rcdir):
    svc, detail = pgwrepair.local_proxy_service('192.168.70.1', '1080', fake_runner(), (rcdir,),
                                                is_local=lambda a: True)
    assert svc == 'sslocal-rust' and 'sslocal' in detail


def test_local_proxy_service_refusals(rcdir):
    lp = pgwrepair.local_proxy_service
    assert lp('203.0.113.9', '1080', fake_runner(), (rcdir,), is_local=lambda a: False)[0] == ''
    assert lp('192.168.70.1', '1080', fake_runner(sockstat=''), (rcdir,), is_local=lambda a: True)[0] == ''
    # sshd -D on the port: not a proxy daemon we may restart
    ss = SOCKSTAT.replace('sslocal', 'sshd   ')
    assert lp('192.168.70.1', '1080', fake_runner(sockstat=ss, binary='/usr/local/sbin/sshd'), (rcdir,),
              is_local=lambda a: True)[0] == ''
    # listener on another address
    ss = SOCKSTAT.replace('*:1080', '127.0.0.1:1080')
    assert lp('192.168.70.1', '1080', fake_runner(sockstat=ss), (rcdir,), is_local=lambda a: True)[0] == ''
    # no rc script
    assert lp('192.168.70.1', '1080', fake_runner(), (rcdir + '/none',), is_local=lambda a: True)[0] == ''


def test_restart_service_validates_name():
    seen = []
    run = lambda argv, **kw: seen.append(argv) or types.SimpleNamespace(returncode=0)
    assert pgwrepair.restart_service('sslocal-rust', run)
    assert seen == [[pgwrepair.SERVICE, 'sslocal-rust', 'restart']]
    assert not pgwrepair.restart_service('x; reboot', run) and len(seen) == 1


def test_is_local_address():
    assert pgwrepair.is_local_address('127.0.0.1')
    assert not pgwrepair.is_local_address('')
    assert not pgwrepair.is_local_address('192.0.2.77')      # TEST-NET, never local


def test_state_file_roundtrip_and_garbage(tmp_path):
    (tmp_path / 'China.repair').write_text('{garbage')
    assert pgwrepair.load_state('China', str(tmp_path)) == pgwrepair.default_state()
    s = pgwrepair.default_state()
    pgwrepair.note_restart(s, 100, 'tun2socks', True)
    pgwrepair.save_state('China', s, str(tmp_path))
    assert pgwrepair.load_state('China', str(tmp_path))['restarts'] == [100]


# ---------------------------------------------------------------- restartconn action

def test_restartconn_action_and_wrapper():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ACTIONS)
    a = cp['restartconn']
    assert a['command'].endswith('/restartconn.sh') and a['parameters'] == '%s'
    assert a['type'] == 'script_output'
    sh = open(os.path.join(SCRIPTS, 'restartconn.sh')).read()
    assert 'pgw_valid_name "$1"' in sh
    assert '/usr/bin/lockf -k -s -t 60 "$PGW_LOCKFILE"' in sh and '--restart "$1"' in sh
    code = '\n'.join(l for l in sh.splitlines() if not l.lstrip().startswith('#'))
    for bad in ('config.xml', 'forcedown', 'teardown.sh', 'setup.sh'):
        assert bad not in code


def test_manual_restart(monkeypatch, capsys):
    restarted = []
    monkeypatch.setattr(watchdog, 'DRY_RUN', False)
    monkeypatch.setattr(watchdog, 'get_enabled_connections', lambda: {'China': CONN})
    monkeypatch.setattr(watchdog, 'restart_connection', lambda c: restarted.append(c['name']) or True)
    monkeypatch.setattr(pgwrepair, 'syslog', FakeSyslog())
    state = {'alive': True, 'ifc': 'pgw_China: flags=1008043<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500\n'}
    monkeypatch.setattr(watchdog, 'check_connection', lambda n: state['alive'])
    cmds = []

    def run(argv, **kw):
        cmds.append(argv)
        if argv[0] == '/sbin/ifconfig':
            return subprocess.CompletedProcess(argv, 0 if state['ifc'] else 1, state['ifc'], '')
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(watchdog.subprocess, 'run', run)

    assert watchdog.manual_restart('bad;name') == 1
    assert watchdog.manual_restart('Nope') == 1
    assert watchdog.manual_restart('China') == 0           # running: no-op
    assert restarted == []
    state['alive'] = False
    assert watchdog.manual_restart('China') == 0
    assert restarted == ['China']
    assert ['/usr/local/sbin/configctl', 'interface', 'routes', 'reconfigure'] in cmds
    state.update(alive=True, ifc='')                       # interface missing
    assert watchdog.manual_restart('China') == 0 and restarted == ['China', 'China']
    out = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert [o['status'] for o in out] == ['error', 'error', 'ok', 'ok', 'ok']
    assert out[2]['action'] == 'none' and out[3]['action'] == 'restart'


# ---------------------------------------------------------------- healthcheck fix / unverified / repair

CONFIG = """<opnsense><OPNsense><ProxyGateway><general><enabled>1</enabled></general><connections>
<connection uuid="1"><enabled>1</enabled><name>China</name><healthCheckEnabled>1</healthCheckEnabled></connection>
</connections></ProxyGateway></OPNsense></opnsense>"""
NOW = 1795300000
UP = 'pgw_China: flags=1008043<UP,BROADCAST,RUNNING,MULTICAST,LOWER_UP> metric 0 mtu 1500\n'


def health(tmp_path, ifaces=None, pid=True, status=None, repair=None):
    (tmp_path / 'config.xml').write_text(CONFIG)
    run = tmp_path / 'run'
    run.mkdir()
    if pid:
        (run / 'China.pid').write_text(str(os.getpid()))
    if status is not None:
        (run / 'China.status').write_text(status)
    if repair is not None:
        (run / 'China.repair').write_text(json.dumps(repair))
    ifaces = {'pgw_China': UP} if ifaces is None else ifaces

    def runner(argv, **kw):
        if argv[0] == plugin_health.IFCONFIG:
            out = ifaces.get(argv[1])
            return types.SimpleNamespace(returncode=0 if out else 1, stdout=out or '')
        return types.SimpleNamespace(returncode=0, stdout=json.dumps({'gateways': GWS}))
    out = plugin_health.build(str(tmp_path / 'config.xml'), str(run), runner, now=NOW)
    return {c['name']: c for c in out['checks']}


def test_fix_on_dead_tun2socks_and_missing_interface(tmp_path):
    c = health(tmp_path, ifaces={}, pid=False)
    fix = {'action': 'proxygateway restart_conn China', 'title': 'Restart the China tunnel (tun2socks)'}
    assert c['China: tun2socks']['fix'] == fix and c['China: interface']['fix'] == fix
    assert c['China: gateway']['detail'] == 'FRP_GW online'


def test_no_fix_when_healthy(tmp_path):
    c = health(tmp_path, status='status=up\nlatency_ms=500\nmode=tun\ntun_path=nat_leak\nverified=1\n'
                                'pinned=110.242.68.66\ntimestamp=%d\n' % (NOW - 60))
    assert all('fix' not in x for x in c.values())
    assert c['China: connectivity']['ok'] is True and 'pinned' in c['China: connectivity']['detail']


def test_fix_action_names_an_existing_connection_and_action():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ACTIONS)
    action = plugin_health.restart_fix('China')['action'].split()
    assert action[0] == 'proxygateway' and action[1] in cp and action[2] == 'China'
    assert plugin_health.REPAIR_MAX_PER_HOUR == pgwrepair.REPAIR_MAX_PER_HOUR


def test_unverified_probe_is_not_reported_as_ok(tmp_path):
    c = health(tmp_path, status='status=up\nlatency_ms=800\nmode=proxy\ntun_path=nat_leak\nverified=0\n'
                                'pin_error=route add failed\ntimestamp=%d\n' % (NOW - 60))
    conn = c['China: connectivity']
    assert conn['ok'] is False and conn['severity'] == 'low' and 'unverified' in conn['detail']
    assert 'route add failed' in conn['detail']
    # status file from 1.4.0 (no verified key): mode=proxy + nat_leak is unverified too
    (tmp_path / 'b').mkdir()
    c = health(tmp_path / 'b', status='status=up\nlatency_ms=800\nmode=proxy\ntun_path=nat_leak\n'
                                      'timestamp=%d\n' % (NOW - 60))
    assert c['China: connectivity']['ok'] is False


def test_repair_state_checks(tmp_path):
    c = health(tmp_path, repair={'restarts': [NOW - 100, NOW - 500, NOW - 900], 'tunnel_failures': 2,
                                 'last_action': 'tun2socks', 'last_result': 'ok', 'last_at': NOW - 100})
    assert c['China: auto-repair']['ok'] is False and 'capped' in c['China: auto-repair']['detail']
    (tmp_path / 'b').mkdir()
    c = health(tmp_path / 'b', repair={'restarts': [NOW - 100], 'last_action': 'tun2socks',
                                       'last_result': 'failed', 'last_at': NOW - 100})
    assert c['China: auto-repair']['ok'] is False and 'failed' in c['China: auto-repair']['detail']
    (tmp_path / 'c').mkdir()
    c = health(tmp_path / 'c', repair={'restarts': [NOW - 100], 'last_action': 'tun2socks',
                                       'last_result': 'ok', 'last_at': NOW - 100, 'tunnel_failures': 0})
    assert c['China: auto-repair']['ok'] is True and c['China: auto-repair']['severity'] == 'info'
    (tmp_path / 'd').mkdir()
    c = health(tmp_path / 'd', repair={'restarts': [NOW - 7200], 'last_result': 'ok', 'last_at': NOW - 7200})
    assert 'China: auto-repair' not in c
