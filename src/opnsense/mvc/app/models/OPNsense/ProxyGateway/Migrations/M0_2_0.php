<?php

namespace OPNsense\ProxyGateway\Migrations;

use OPNsense\Base\BaseModelMigration;

class M0_2_0 extends BaseModelMigration
{
    /**
     * Migrate from 0.1.0 to 0.2.0.
     *
     * Changes:
     * - Added general.startOnBoot (default: 1)
     * - Removed connection.dnsMode, dnsServer, healthCheckInterval, killSwitch
     * - Added input validation masks for description and healthCheckTarget
     *
     * The parent run() applies defaults for new fields. Removed fields are
     * silently ignored by the MVC framework.
     */
    public function run($model)
    {
        parent::run($model);
    }
}
