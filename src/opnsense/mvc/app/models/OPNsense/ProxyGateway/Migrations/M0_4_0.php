<?php

namespace OPNsense\ProxyGateway\Migrations;

use OPNsense\Base\BaseModelMigration;

class M0_4_0 extends BaseModelMigration
{
    /**
     * Migrate from 0.3.0 to 0.4.0.
     *
     * Changes:
     * - Added general.speedTestEnabled (default: 0)
     * - Added general.speedTestInterval (default: m15)
     * - Added general.speedTestSize (default: s10m)
     * - Added general.autoForceDown (default: 1)
     * - Added connection.speedTestUrl (optional URL)
     * - Added connection.speedTestUrlDomestic (optional URL)
     * - Added connection.backupEnabled (default: 0)
     * - Added connection.backupProxyType (default: socks5)
     * - Added connection.backupProxyServer (optional)
     * - Added connection.backupProxyPort (default: 1080)
     * - Added connection.backupAuthEnabled (default: 0)
     * - Added connection.backupAuthUser (optional)
     * - Added connection.backupAuthPass (optional)
     * - Added connection.failoverThreshold (default: 3)
     * - Added connection.failbackEnabled (default: 1)
     * - Added connection.ssMethod (default: aes-256-gcm)
     * - Added connection.ssPassword (optional)
     * - Added connection.ssObfs (optional)
     * - Added connection.ssObfsHost (optional)
     * - Added connection.sshKeyFile (optional)
     * - Added connection.backupSsMethod (default: aes-256-gcm)
     * - Added connection.backupSsPassword (optional)
     * - Added connection.backupSshKeyFile (optional)
     *
     * The parent run() applies defaults for new fields.
     */
    public function run($model)
    {
        parent::run($model);
    }
}
