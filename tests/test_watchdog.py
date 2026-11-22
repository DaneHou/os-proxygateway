"""Failover state machine of watchdog.check_failover() with mocked probes."""

import json
import os

import pytest

import watchdog

CONN = {
    'name': 'China', 'enabled': '1', 'proxyType': 'socks5', 'proxyServer': '192.168.70.1',
    'proxyPort': '1080', 'backupEnabled': '1', 'backupProxyType': 'socks5',
    'backupProxyServer': '192.168.70.87', 'backupProxyPort': '1055',
    'failoverThreshold': '3', 'failbackThreshold': '3', 'failbackEnabled': '1', 'autoForceDown': '1',
}


class World:
    def __init__(self, monkeypatch, tmp_path):
        self.backup = 'up'
        self.primary = 'up'
        self.switches = []
        self.force = []
        self.backup_probes = 0
        monkeypatch.setattr(watchdog, 'RUNDIR', str(tmp_path))
        monkeypatch.setattr(watchdog, 'DRY_RUN', False)
        monkeypatch.setattr(watchdog, 'probe_backup', self._probe_backup)
        monkeypatch.setattr(watchdog, 'probe_primary', lambda conn: self.primary)
        monkeypatch.setattr(watchdog, 'switch_proxy', self._switch)
        monkeypatch.setattr(watchdog, 'force_down_gateway', self._force)
        # the plugin's own gateway exists on pgw_China (force-down allowed)
        monkeypatch.setattr(watchdog.pgwrepair, 'load_gateways', lambda: [
            {'name': 'PROXYGW_CHINA', 'device': 'pgw_China', 'disabled': False}])
        self.dir = tmp_path

    def _probe_backup(self, conn):
        self.backup_probes += 1
        return self.backup

    def _switch(self, name, conn, to_backup):
        self.switches.append('backup' if to_backup else 'primary')
        return True

    def _force(self, name, down):
        self.force.append(down)
        return True

    def tick(self, ok, now, conn=CONN):
        return watchdog.check_failover('China', conn, ok, now=now)

    def state(self):
        return json.loads((self.dir / 'China.failover').read_text())


@pytest.fixture
def world(monkeypatch, tmp_path):
    return World(monkeypatch, tmp_path)


def test_switch_after_n_failures_when_backup_probes_ok(world):
    world.tick(False, 1000)
    world.tick(False, 1060)
    assert world.switches == []
    world.tick(False, 1120)
    assert world.switches == ['backup']
    s = world.state()
    assert s['active_proxy'] == 'backup' and s['backup_status'] == 'up' and s['consecutive_failures'] == 0
    assert world.force == []


def test_dead_backup_is_not_switched_to_and_gateway_forced_down(world):
    world.backup = 'down'
    for i in range(5):
        world.tick(False, 1000 + 60 * i)
    assert world.switches == []
    assert world.force == [True]          # once, not every minute
    s = world.state()
    assert s['active_proxy'] == 'primary' and s['backup_status'] == 'down' and s['forced_down']
    assert s['backup_reason']
    # primary recovers: force-down cleared
    world.tick(True, 2000)
    assert world.force == [True, False] and not world.state()['forced_down']


def test_unprobeable_backup_is_not_used(world):
    world.backup = 'unknown'
    for i in range(3):
        world.tick(False, 1000 + 60 * i)
    assert world.switches == [] and world.state()['backup_status'] == 'unknown'


def test_single_failures_never_switch(world):
    for i in range(20):
        world.tick(i % 3 != 0, 1000 + 60 * i)   # one failure, two successes, repeat
    assert world.switches == [] and world.force == []
    assert world.state()['consecutive_failures'] == 0


def test_idle_backup_probed_at_most_every_interval(world):
    world.backup = 'down'
    for i in range(10):                         # 10 healthy minutes
        world.tick(True, 1000 + 60 * i)
    assert world.backup_probes == 2             # t=1000 and t=1300
    assert world.state()['backup_status'] == 'down'


def test_failback_needs_m_successes_after_cooldown(world):
    for i in range(3):
        world.tick(False, 1000 + 60 * i)        # switch at t=1120
    assert world.switches == ['backup']
    world.primary = 'up'
    world.tick(True, 1180)                      # in cooldown: no probe counted
    assert world.state()['primary_probe_ok_count'] == 0
    world.tick(True, 1500)
    world.tick(True, 1560)
    assert world.switches == ['backup']
    world.primary = 'down'                      # a miss resets the count
    world.tick(True, 1620)
    assert world.state()['primary_probe_ok_count'] == 0
    world.primary = 'up'
    for i in range(3):
        world.tick(True, 1680 + 60 * i)
    assert world.switches == ['backup', 'primary']
    assert world.state()['active_proxy'] == 'primary'


def test_failback_threshold_from_config(world):
    conn = dict(CONN, failbackThreshold='1')
    for i in range(3):
        world.tick(False, 1000 + 60 * i, conn)
    world.tick(True, 1500, conn)
    assert world.switches == ['backup', 'primary']


def test_backup_failing_with_primary_dead_stays_and_forces_down(world):
    for i in range(3):
        world.tick(False, 1000 + 60 * i)
    world.primary = 'down'
    for i in range(4):
        world.tick(False, 2000 + 60 * i)
    assert world.switches == ['backup']
    assert world.force == [True]
    s = world.state()
    assert s['active_proxy'] == 'backup' and s['backup_status'] == 'down' and s['forced_down']


def test_backup_failing_with_primary_ok_goes_back(world):
    for i in range(3):
        world.tick(False, 1000 + 60 * i)
    world.primary = 'up'
    for i in range(3):
        world.tick(False, 2000 + 60 * i)
    assert world.switches == ['backup', 'primary']
    assert world.force == []


def test_old_state_file_loads(world):
    (world.dir / 'China.failover').write_text(json.dumps({
        'active_proxy': 'primary', 'consecutive_failures': 2, 'switched_at': None,
        'switch_count': 0, 'primary_probe_ok_count': 0, 'forced_down': False}))
    world.tick(False, 1000)
    assert world.switches == ['backup']


def test_dry_run_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, 'RUNDIR', str(tmp_path))
    monkeypatch.setattr(watchdog, 'DRY_RUN', True)
    monkeypatch.setattr(watchdog, 'probe_backup', lambda c: 'up')
    monkeypatch.setattr(watchdog, 'probe_primary', lambda c: 'up')

    def boom(*a, **kw):
        raise AssertionError('subprocess called in dry-run: %r' % (a,))
    monkeypatch.setattr(watchdog.subprocess, 'run', boom)
    (tmp_path / 'China.failover').write_text(json.dumps({'active_proxy': 'primary', 'consecutive_failures': 2}))
    before = (tmp_path / 'China.failover').read_text()
    state = watchdog.check_failover('China', CONN, False, now=1000)
    assert state['active_proxy'] == 'backup'          # decision is still made...
    assert (tmp_path / 'China.failover').read_text() == before   # ...but not saved
    assert watchdog.restart_connection(CONN) is False
    assert sorted(os.listdir(tmp_path)) == ['China.failover']


def test_dry_run_health_check_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, 'DRY_RUN', True)
    result = {'ok': True, 'status': 'up', 'reason': '', 'mode': 'proxy', 'tun_path': 'nat_leak',
              'http_code': '200', 'curl_exit': 0, 'curl_err': '', 'latency_ms': 5,
              'target': 't', 'via': 'v'}
    monkeypatch.setattr(watchdog.pgwhealth, 'check', lambda name: result)

    def no_record(*a, **kw):
        raise AssertionError('record() called in dry-run')
    monkeypatch.setattr(watchdog.pgwhealth, 'record', no_record)
    assert watchdog.run_healthcheck('China') is result
