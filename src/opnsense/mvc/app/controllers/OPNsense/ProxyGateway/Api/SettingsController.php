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

namespace OPNsense\ProxyGateway\Api;

use OPNsense\Base\ApiMutableModelControllerBase;

/**
 * API controller for general Proxy Gateway settings.
 *
 * Endpoints:
 *   GET  /api/proxygateway/settings/get
 *   POST /api/proxygateway/settings/set
 */
class SettingsController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'ProxyGateway';
    protected static $internalModelClass = 'OPNsense\ProxyGateway\ProxyGateway';

    /**
     * Get general settings.
     * @return array general settings
     */
    public function getAction()
    {
        return $this->getBase('general', 'general');
    }

    /**
     * Set general settings.
     * @return array save result
     */
    public function setAction()
    {
        return $this->setBase('general', 'general');
    }
}
