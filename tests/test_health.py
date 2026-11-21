"""pgwhealth.check()/record() with mocked curl, pfctl and ifconfig."""

import json
import os
import subprocess

import pytest

import pgwconf
import pgwhealth
from test_predictor import FILTER, NAT


class FakeRun:
    """Records commands; answers curl with a given http code."""

    def __init__(self, http_code='200', iface_ok=True):
        self.calls = []
        self.http_code = http_code
        self.iface_ok = iface_ok

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw.get('input')))
        if cmd[0] == pgwhealth.IFCONFIG:
            return subprocess.CompletedProcess(cmd, 0 if self.iface_ok else 1, '', '')
        if cmd[0] == pgwhealth.CURL:
            rc = 0 if self.http_code != '000' else 7
            return subprocess.CompletedProcess(cmd, rc, self.http_code, '' if rc == 0 else 'curl: (7) Failed')
        raise AssertionError(cmd)

    def curl(self):
        return [c for c in self.calls if c[0][0] == pgwhealth.CURL]


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
                           pf_reader=lambda: pf, **kw)


def test_leak_predicted_probes_proxy_not_tunnel(rundir):
    run = FakeRun()
    r = run_check(rundir(), run)
    assert r['ok'] and r['mode'] == 'proxy' and r['tun_path'] == 'nat_leak'
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
    assert r['ok'] and r['mode'] == 'tun' and r['tun_path'] == 'ok'
    (cmd, cfg), = run.curl()
    assert cmd[cmd.index('--interface') + 1] == 'pgw_China'
    assert cmd[-1] == 'https://www.iqiyi.com/'
    assert cfg == ''


def test_ss_keeps_interface_probe_but_flags_leak(rundir):
    run = FakeRun()
    r = run_check(rundir(proxy_type='ss', url='ss://aes:pw@1.2.3.4:8388'), run)
    assert r['mode'] == 'tun' and r['tun_path'] == 'nat_leak'
    assert '--interface' in run.curl()[0][0]


def test_failed_probe(rundir):
    r = run_check(rundir(), FakeRun(http_code='000'))
    assert not r['ok'] and r['status'] == 'down' and r['reason'] == 'proxy_unreachable'


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
    r = run_check(d, FakeRun())
    line = pgwhealth.record('China', r, 1795253581, rundir=d, logdir=str(logdir))
    status = dict(l.split('=', 1) for l in open(os.path.join(d, 'China.status')).read().splitlines())
    assert status['status'] == 'up' and status['mode'] == 'proxy' and status['tun_path'] == 'nat_leak'
    assert status['timestamp'] == '1795253581' and 'latency_ms' in status
    assert 'p%40ss' not in status['probe']
    hist = json.loads((logdir / 'China_health.log').read_text().splitlines()[-1])
    assert hist == {'timestamp': 1795253581, 'name': 'China', 'status': 'up',
                    'latency_ms': r['latency_ms'], 'http_code': '200', 'mode': 'proxy'}
    assert '[healthcheck]' in line and 'Healthy' in line and 'p%40ss' not in line
    assert (logdir / 'China.log').read_text().strip() == line


def test_record_failure_has_curl_exit(rundir, tmp_path):
    d = rundir()
    r = run_check(d, FakeRun(http_code='000'))
    pgwhealth.record('China', r, 1, rundir=d, logdir=str(tmp_path))
    status = open(os.path.join(d, 'China.status')).read()
    assert 'status=down' in status and 'reason=proxy_unreachable' in status and 'curl_exit=7' in status
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
