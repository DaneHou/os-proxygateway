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
                            '<td>' + conn.interface + '</td>' +
                            '<td>' + conn.proxy_type.toUpperCase() + '://' + conn.proxy_addr + ':' + conn.proxy_port + '</td>' +
                            '<td>' + statusIcon + '</td>' +
                            '<td>' + latency + '</td>' +
                            '<td>' + conn.tun_local + ' &lt;-&gt; ' + conn.tun_peer + '</td>' +
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

        // Refresh logs
        function refreshLogs() {
            var name = $('#log-filter-name').val();
            ajaxGet('/api/proxygateway/diagnostics/getLogs', {name: name, lines: 100}, function(data, status) {
                if (data.lines) {
                    $('#log-output').text(data.lines.join('\n'));
                } else {
                    $('#log-output').text('No logs available.');
                }
            });
        }

        // Refresh button
        $('#btn-refresh-status').click(refreshStatus);
        $('#btn-refresh-logs').click(refreshLogs);

        // Auto-refresh every 10 seconds
        setInterval(refreshStatus, 10000);

        // Initial load
        refreshStatus();
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
            <div class="pull-right">
                <select id="log-filter-name" class="selectpicker" data-width="200px">
                    <option value="">{{ lang._('All connections') }}</option>
                </select>
                <button id="btn-refresh-logs" class="btn btn-xs btn-default">
                    <span class="fa fa-fw fa-refresh"></span> {{ lang._('Refresh') }}
                </button>
            </div>
        </h3>
    </div>
    <pre id="log-output" style="max-height: 400px; overflow-y: auto; font-size: 12px;">{{ lang._('Loading...') }}</pre>
</div>
