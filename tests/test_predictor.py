"""predict_tun_path() against pf rule text (taken from the live router)."""

from pgwhealth import predict_tun_path

IFACE = 'pgw_China'
LOCAL = '172.31.175.169'

FILTER = """\
block drop in log on ! pgw_China inet from 172.31.175.169 to any
pass in quick on igc2 route-to (pgw_China 172.31.175.170) inet from <approuter_clients_a6a42fca> to <approuter_video_iqiyi> flags S/SA keep state label "x"
pass out log all flags S/SA keep state allow-opts label "fae5"
pass out log route-to (pgw_China 172.31.175.170) inet from (pgw_China) to ! (pgw_China:network) flags S/SA keep state allow-opts label "e277"
pass out log route-to (igc0 198.18.0.1) inet from (igc0) to ! (igc0:network) flags S/SA keep state allow-opts label "43dd"
"""

NAT = """\
nat on pgw_China inet from 10.0.0.0/8 to any -> (pgw_China:0) port 1024:65535 round-robin
nat on pgw_China inet from 172.16.0.0/12 to any -> (pgw_China:0) port 1024:65535 round-robin
nat on igc0 inet from 10.10.0.0/24 to any -> (igc0:0) port 1024:65535
nat on igc0 inet from (pgw_China:network) to any port = isakmp -> (igc0:0) static-port
nat on igc0 inet from (wg0:network) to any port = isakmp -> (igc0:0) static-port
nat on igc0 inet from (pgw_China:network) to any -> (igc0:0) port 1024:65535
nat on igc0 inet from (wg0:network) to any -> (igc0:0) port 1024:65535
"""


def test_router_today_leaks():
    assert predict_tun_path(IFACE, LOCAL, NAT, FILTER) == 'nat_leak'


def test_no_nat_rule_first_makes_path_ok():
    nat = 'no nat on igc0 inet from 172.31.175.169 to any\n' + NAT
    assert predict_tun_path(IFACE, LOCAL, nat, FILTER) == 'ok'


def test_no_nat_for_interface_network_ok():
    nat = 'no nat on igc0 inet from (pgw_China:network) to any\n' + NAT
    assert predict_tun_path(IFACE, LOCAL, nat, FILTER) == 'ok'


def test_missing_route_to():
    filt = '\n'.join(l for l in FILTER.splitlines() if 'route-to (pgw_China' not in l or 'pass in' in l)
    assert predict_tun_path(IFACE, LOCAL, NAT, filt) == 'no_route_to'


def test_inbound_route_to_alone_is_not_enough():
    filt = 'pass in quick on igc2 route-to (pgw_China 172.31.175.170) inet from (pgw_China) to any\n'
    assert predict_tun_path(IFACE, LOCAL, '', filt) == 'no_route_to'


def test_table_source_is_unknown():
    nat = 'nat on igc0 inet from <some_table> to any -> (igc0:0)\n' + NAT
    assert predict_tun_path(IFACE, LOCAL, nat, FILTER) == 'unknown'


def test_isakmp_port_rule_is_skipped():
    # only the port-qualified rule covers the tunnel: TCP probe is not NATed
    nat = 'nat on igc0 inet from (pgw_China:network) to any port = isakmp -> (igc0:0) static-port\n'
    assert predict_tun_path(IFACE, LOCAL, nat, FILTER) == 'ok'


def test_cidr_source_covering_tunnel_leaks():
    nat = 'nat on igc0 inet from 172.16.0.0/12 to any -> (igc0:0) port 1024:65535\n'
    assert predict_tun_path(IFACE, LOCAL, nat, FILTER) == 'nat_leak'


def test_other_networks_and_tun_own_nat_ignored():
    nat = '\n'.join(l for l in NAT.splitlines() if 'from (pgw_China:network) to any ->' not in l)
    assert predict_tun_path(IFACE, LOCAL, nat, FILTER) == 'ok'


def test_udp_only_rule_skipped_and_specific_destination_skipped():
    nat = ('nat on igc0 inet proto udp from any to any -> (igc0:0)\n'
           'nat on igc0 inet from any to 10.1.0.0/16 -> (igc0:0)\n')
    assert predict_tun_path(IFACE, LOCAL, nat, FILTER) == 'ok'


def test_any_source_leaks():
    assert predict_tun_path(IFACE, LOCAL, 'nat on igc0 inet from any to any -> (igc0:0)\n', FILTER) == 'nat_leak'


def test_unreadable_rules_unknown():
    assert predict_tun_path(IFACE, LOCAL, '', '') == 'unknown'
    assert predict_tun_path(IFACE, '', NAT, FILTER) == 'unknown'
