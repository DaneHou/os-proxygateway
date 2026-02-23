{#
  OPNsense Proxy Gateway — Diagnostics Page
  Services → Proxy Gateway → Diagnostics
#}

<script>
    $( document ).ready(function() {

        // Refresh status
        function refreshStatus() {
            ajaxGet('/api/proxygateway/diagnostics/getStatus', {}, function(data, status) {
                var tbody = $('#status-table tbody');
                tbody.empty();

                if (data.data && data.data.connections) {
                    $.each(data.data.connections, function(idx, conn) {
                        var statusIcon = conn.status === 'up'
                            ? '<span class="fa fa-fw fa-check-circle text-success"></span> Online'
                            : '<span class="fa fa-fw fa-times-circle text-danger"></span> Offline';

                        var latency = '-';
                        if (conn.health && conn.health.latency_ms && conn.health.latency_ms !== '-1') {
                            latency = conn.health.latency_ms + ' ms';
                        }

                        var row = '<tr>' +
                            '<td>' + conn.name + '</td>' +
                            '<td><code>' + conn.interface + '</code></td>' +
                            '<td>' + conn.proxy_type.toUpperCase() + '://' + conn.proxy_addr + ':' + conn.proxy_port + '</td>' +
                            '<td>' + statusIcon + '</td>' +
                            '<td>' + latency + '</td>' +
                            '<td><code>' + conn.tun_local + '</code> &harr; <code>' + conn.tun_peer + '</code></td>' +
                            '<td>' + (conn.pid || '-') + '</td>' +
                            '<td>' +
                                '<button class="btn btn-xs btn-default btn-test" data-name="' + conn.name + '">' +
                                    '<span class="fa fa-fw fa-heartbeat"></span> Test' +
                                '</button>' +
                            '</td>' +
                            '</tr>';
                        tbody.append(row);
                    });
                }

                if (!data.data || !data.data.connections || data.data.connections.length === 0) {
                    tbody.append('<tr><td colspan="8" class="text-center text-muted">{{ lang._("No active connections") }}</td></tr>');
                }
            });
        }

        // Test connection button
        $(document).on('click', '.btn-test', function() {
            var name = $(this).data('name');
            var btn = $(this);
            btn.prop('disabled', true).html('<span class="fa fa-fw fa-spinner fa-spin"></span> Testing...');

            ajaxCall('/api/proxygateway/diagnostics/testConnection', {name: name}, function(data, status) {
                btn.prop('disabled', false).html('<span class="fa fa-fw fa-heartbeat"></span> Test');
                if (data.result) {
                    BootstrapDialog.show({
                        title: 'Health Check: ' + name,
                        message: '<pre>' + data.result + '</pre>',
                        type: data.result.indexOf('OK') >= 0 ? BootstrapDialog.TYPE_SUCCESS : BootstrapDialog.TYPE_DANGER
                    });
                }
                refreshStatus();
            });
        });

        // Populate the log filter dropdown from available log files
        function populateLogFilter() {
            ajaxGet('/api/proxygateway/diagnostics/getLogConnections', {}, function(data, status) {
                var select = $('#log-filter-name');
                var currentVal = select.val();
                select.find('option:not(:first)').remove();
                if (data.connections) {
                    $.each(data.connections, function(idx, name) {
                        select.append('<option value="' + name + '">' + name + '</option>');
                    });
                }
                // Restore previous selection if still exists
                if (currentVal) {
                    select.val(currentVal);
                }
                select.selectpicker('refresh');
            });
        }

        // Refresh logs
        var autoScroll = true;
        function refreshLogs() {
            var name = $('#log-filter-name').val();
            ajaxGet('/api/proxygateway/diagnostics/getLogs', {name: name, lines: 200}, function(data, status) {
                var logOutput = $('#log-output');
                if (data.lines && data.lines.length > 0) {
                    logOutput.text(data.lines.join('\n'));
                } else {
                    logOutput.text('No logs available.');
                }
                // Auto-scroll to bottom if enabled
                if (autoScroll) {
                    logOutput.scrollTop(logOutput[0].scrollHeight);
                }
            });
        }

        // Clear logs
        $('#btn-clear-logs').click(function() {
            var name = $('#log-filter-name').val();
            var target = name ? ('connection "' + name + '"') : 'all connections';

            BootstrapDialog.confirm({
                title: '{{ lang._("Clear Logs") }}',
                message: '{{ lang._("Are you sure you want to clear logs for") }} ' + target + '?',
                type: BootstrapDialog.TYPE_WARNING,
                btnOKLabel: '{{ lang._("Clear") }}',
                btnOKClass: 'btn-warning',
                callback: function(result) {
                    if (result) {
                        ajaxCall('/api/proxygateway/diagnostics/clearLogs', {name: name}, function(data, status) {
                            refreshLogs();
                        });
                    }
                }
            });
        });

        // Toggle auto-scroll
        $('#btn-auto-scroll').click(function() {
            autoScroll = !autoScroll;
            $(this).toggleClass('btn-primary btn-default');
            if (autoScroll) {
                var logOutput = $('#log-output');
                logOutput.scrollTop(logOutput[0].scrollHeight);
            }
        });

        // Refresh when filter changes
        $('#log-filter-name').change(function() {
            refreshLogs();
        });

        // Refresh buttons
        $('#btn-refresh-status').click(refreshStatus);
        $('#btn-refresh-logs').click(refreshLogs);

        // Auto-refresh every 10 seconds
        setInterval(function() {
            refreshStatus();
            refreshLogs();
        }, 10000);

        // Initial load
        refreshStatus();
        populateLogFilter();
        refreshLogs();
    });
</script>

<div class="content-box">
    <div class="content-box-header">
        <h3>{{ lang._('Connection Status') }}
            <button id="btn-refresh-status" class="btn btn-xs btn-default pull-right">
                <span class="fa fa-fw fa-refresh"></span> {{ lang._('Refresh') }}
            </button>
        </h3>
    </div>

    <table id="status-table" class="table table-condensed table-hover table-striped">
        <thead>
            <tr>
                <th>{{ lang._('Name') }}</th>
                <th>{{ lang._('Interface') }}</th>
                <th>{{ lang._('Proxy') }}</th>
                <th>{{ lang._('Status') }}</th>
                <th>{{ lang._('Latency') }}</th>
                <th>{{ lang._('Tunnel') }}</th>
                <th>{{ lang._('PID') }}</th>
                <th>{{ lang._('Actions') }}</th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="8" class="text-center text-muted">{{ lang._('Loading...') }}</td></tr>
        </tbody>
    </table>
</div>

<div class="content-box" style="margin-top: 1em;">
    <div class="content-box-header">
        <h3>{{ lang._('Logs') }}
            <div class="pull-right" style="display: flex; gap: 5px; align-items: center;">
                <select id="log-filter-name" class="selectpicker" data-width="200px">
                    <option value="">{{ lang._('All connections') }}</option>
                </select>
                <button id="btn-auto-scroll" class="btn btn-xs btn-primary" title="{{ lang._('Auto-scroll to latest') }}">
                    <span class="fa fa-fw fa-arrow-down"></span>
                </button>
                <button id="btn-refresh-logs" class="btn btn-xs btn-default">
                    <span class="fa fa-fw fa-refresh"></span> {{ lang._('Refresh') }}
                </button>
                <button id="btn-clear-logs" class="btn btn-xs btn-warning">
                    <span class="fa fa-fw fa-eraser"></span> {{ lang._('Clear Logs') }}
                </button>
            </div>
        </h3>
    </div>
    <pre id="log-output" style="max-height: 500px; overflow-y: auto; font-size: 12px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; line-height: 1.4;">{{ lang._('Loading...') }}</pre>
</div>
