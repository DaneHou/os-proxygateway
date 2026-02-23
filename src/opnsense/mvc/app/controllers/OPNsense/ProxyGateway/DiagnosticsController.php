<?php

/*
 * Copyright (c) 2024-2026 DaneBA
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
 */

namespace OPNsense\ProxyGateway;

/**
 * UI controller for the Proxy Gateway diagnostics page.
 *
 * OPNsense routes /ui/proxygateway/diagnostics to
 * DiagnosticsController::indexAction(), NOT IndexController::diagnosticsAction().
 */
class DiagnosticsController extends \OPNsense\Base\IndexController
{
    /**
     * Diagnostics page.
     */
    public function indexAction()
    {
        $this->view->pick('OPNsense/ProxyGateway/diagnostics');
    }
}
