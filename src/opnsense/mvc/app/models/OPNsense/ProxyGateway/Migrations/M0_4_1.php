<?php

namespace OPNsense\ProxyGateway\Migrations;

use OPNsense\Base\BaseModelMigration;

class M0_4_1 extends BaseModelMigration
{
    /**
     * Migrate from 0.4.0 to 0.4.1.
     *
     * tun2socks has no TLS transport to the proxy and no SSH support, so the
     * "SOCKS5 + TLS", "HTTPS CONNECT" and "SSH" proxy types were removed:
     * - socks5tls -> socks5, https -> http. These already connected in
     *   plaintext, so runtime behaviour does not change; only the label
     *   stops claiming encryption.
     * - ssh never worked (tun2socks refuses the scheme). It becomes socks5
     *   and the connection (or its backup) is disabled so it cannot start
     *   against an SSH server by accident.
     * - connection.sshKeyFile / backupSshKeyFile were removed.
     * - Unused general.speedTestSize and connection.speedTestUrlDomestic
     *   were removed (the UI dropped them earlier).
     */
    public function run($model)
    {
        $map = ['socks5tls' => 'socks5', 'https' => 'http'];

        foreach ($model->connections->connection->iterateItems() as $conn) {
            $type = (string)$conn->proxyType;
            if (isset($map[$type])) {
                $conn->proxyType = $map[$type];
            } elseif ($type === 'ssh') {
                $conn->proxyType = 'socks5';
                $conn->enabled = '0';
            }

            $backupType = (string)$conn->backupProxyType;
            if (isset($map[$backupType])) {
                $conn->backupProxyType = $map[$backupType];
            } elseif ($backupType === 'ssh') {
                $conn->backupProxyType = 'socks5';
                $conn->backupEnabled = '0';
            }
        }

        parent::run($model);
    }
}
