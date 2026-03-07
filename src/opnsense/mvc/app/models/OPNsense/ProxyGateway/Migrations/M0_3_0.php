<?php

namespace OPNsense\ProxyGateway\Migrations;

use OPNsense\Base\BaseModelMigration;

class M0_3_0 extends BaseModelMigration
{
    /**
     * Migrate from 0.2.0 to 0.3.0.
     *
     * Changes:
     * - Added general.watchdogEnabled (default: 1)
     *   Auto-restarts crashed tun2socks connections.
     *
     * The parent run() applies defaults for new fields.
     */
    public function run($model)
    {
        parent::run($model);
    }
}
