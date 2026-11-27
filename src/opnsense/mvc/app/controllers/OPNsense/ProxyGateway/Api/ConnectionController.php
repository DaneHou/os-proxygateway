<?php

/*
 * Copyright (c) 2024-2026 os-proxygateway contributors
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

require_once '/usr/local/etc/inc/plugins.inc.d/proxygateway.inc';

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
     * Enriches model data with runtime connection status from the backend.
     * @return array search results
     */
    public function searchItemAction()
    {
        $result = $this->searchBase(
            'connections.connection',
            ['enabled', 'name', 'description', 'proxyType', 'proxyServer', 'proxyPort'],
            'name'
        );

        // Fetch runtime status and merge into results
        $backend = new \OPNsense\Core\Backend();
        $response = $backend->configdRun('proxygateway status');
        $runtimeData = json_decode($response, true);
        $statusMap = [];
        if (!empty($runtimeData['connections'])) {
            foreach ($runtimeData['connections'] as $conn) {
                $statusMap[$conn['name']] = $conn;
            }
        }

        if (!empty($result['rows'])) {
            foreach ($result['rows'] as &$row) {
                $name = $row['name'] ?? '';
                if (isset($statusMap[$name])) {
                    $row['connectionStatus'] = $statusMap[$name]['status'];
                } elseif (($row['enabled'] ?? '') !== '1') {
                    $row['connectionStatus'] = 'disabled';
                } else {
                    $row['connectionStatus'] = 'not_running';
                }
            }
        }

        return $result;
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
        $name = $this->connectionName($uuid);
        $result = $this->delBase('connections.connection', $uuid);
        return $this->withReferenceWarning($result, $name, 'deleted');
    }

    /**
     * Toggle a proxy connection enabled/disabled.
     * @param string $uuid item UUID
     * @param string $enabled '0' or '1'
     * @return array result
     */
    public function toggleItemAction($uuid, $enabled = null)
    {
        $name = $this->connectionName($uuid);
        $result = $this->toggleBase('connections.connection', $uuid, $enabled);
        if (($result['result'] ?? '') === 'Disabled') {
            $result = $this->withReferenceWarning($result, $name, 'disabled');
        }
        return $result;
    }

    /**
     * @param string $uuid connection uuid
     * @return string|null connection name
     */
    private function connectionName($uuid)
    {
        $node = $this->getModel()->getNodeByReference('connections.connection.' . $uuid);
        return $node !== null ? (string)$node->name : null;
    }

    /**
     * Tell the caller when the connection's interface is still used elsewhere
     * (it stays assigned but disabled after Apply, see proxygateway_sync_interfaces()).
     */
    private function withReferenceWarning(array $result, $name, $what)
    {
        if (empty($name)) {
            return $result;
        }
        [$ifkey, $refs] = proxygateway_connection_references($name);
        if ($ifkey !== null && !empty($refs)) {
            $result['warning'] = sprintf(
                gettext('Connection %s %s: its interface %s is still used by %s. After Apply it stays assigned but disabled, and nothing can leave through it.'),
                $name,
                $what === 'deleted' ? gettext('deleted') : gettext('disabled'),
                $ifkey,
                implode('; ', $refs)
            );
        }
        return $result;
    }
}
