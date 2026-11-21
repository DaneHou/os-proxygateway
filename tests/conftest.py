import os
import sys

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'opnsense',
                                       'scripts', 'OPNsense', 'ProxyGateway'))
sys.path.insert(0, SCRIPTS)
