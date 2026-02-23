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
 * API controller for managing proxy gateway connections.
 *
 * Provides CRUD operations for proxy connections:
 *   GET    /api/proxygateway/connection/searchItem
 *   GET    /api/proxygateway/connection/getItem/{uuid}
 *   POST   /api/proxygateway/connection/addItem
 *   POST   /api/proxygateway/connection/setItem/{uuid}
 *   POST   /api/proxygateway/connection/delItem/{uuid}
 */
class ConnectionController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'ProxyGateway';
    protected static $internalModelClass = 'OPNsense\ProxyGateway\ProxyGateway';

    /**
     * Search proxy connections.
     * @return array search results
     */
    public function searchItemAction()
    {
        return $this->searchBase(
            'connections.connection',
            ['enabled', 'name', 'description', 'proxyType', 'proxyServer', 'proxyPort'],
            'name'
        );
    }

    /**
     * Get a single proxy connection by UUID.
     * @param string $uuid item UUID
     * @return array connection data
     */
    public function getItemAction($uuid = null)
    {
        return $this->getBase('connection', 'connections.connection', $uuid);
    }

    /**
     * Add a new proxy connection.
     * @return array save result
     */
    public function addItemAction()
    {
        return $this->addBase('connection', 'connections.connection');
    }

    /**
     * Update an existing proxy connection.
     * @param string $uuid item UUID
     * @return array save result
     */
    public function setItemAction($uuid)
    {
        return $this->setBase('connection', 'connections.connection', $uuid);
    }

    /**
     * Delete a proxy connection.
     * @param string $uuid item UUID
     * @return array delete result
     */
    public function delItemAction($uuid)
    {
        return $this->delBase('connections.connection', $uuid);
    }

    /**
     * Toggle a proxy connection enabled/disabled.
     * @param string $uuid item UUID
     * @param string $enabled '0' or '1'
     * @return array result
     */
    public function toggleItemAction($uuid, $enabled = null)
    {
        return $this->toggleBase('connections.connection', $uuid, $enabled);
    }
}
