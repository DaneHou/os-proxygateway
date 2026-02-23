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

                if (data.data && data.data.connections && data.data.connections.length > 0) {
                    // Populate log filter dropdown with connection names
                    var select = $('#log-filter-name');
                    var currentVal = select.val();
                    select.find('option:not(:first)').remove();
                    $.each(data.data.connections, function(idx, conn) {
                        if (select.find('option[value="' + conn.name + '"]').length === 0) {
                            select.append('<option value="' + conn.name + '">' + conn.name + '</option>');
                        }
                    });
                    select.val(currentVal);
                    if (select.hasClass('selectpicker')) {
                        select.selectpicker('refresh');
                    }

                    $.each(data.data.connections, function(idx, conn) {
                        var statusIcon, statusText;
                        if (conn.status === 'up') {
                            statusIcon = '<span class="fa fa-fw fa-check-circle text-success"></span>';
                            statusText = 'Online';
                        } else if (conn.status === 'down') {
                            statusIcon = '<span class="fa fa-fw fa-times-circle text-danger"></span>';
                            statusText = 'Down';
                        } else if (conn.status === 'disabled') {
                            statusIcon = '<span class="fa fa-fw fa-minus-circle text-muted"></span>';
                            statusText = 'Disabled';
                        } else {
                            statusIcon = '<span class="fa fa-fw fa-question-circle text-warning"></span>';
                            statusText = 'Not Running';
                        }

                        var latency = '-';
                        if (conn.health && conn.health.latency_ms && conn.health.latency_ms !== '-1') {
                            latency = conn.health.latency_ms + ' ms';
                        }

                        var tunnel = (conn.tun_local && conn.tun_local !== '-')
                            ? conn.tun_local + ' &lt;-&gt; ' + conn.tun_peer
                            : '-';

                        var actions = '';
                        if (conn.status === 'up' || conn.status === 'down') {
                            actions = '<button class="btn btn-xs btn-default btn-test" data-name="' + conn.name + '">' +
                                '<span class="fa fa-fw fa-heartbeat"></span> Test</button>';
                        } else if (conn.status === 'not_running') {
                            actions = '<span class="text-muted">Apply to start</span>';
                        }

                        var row = '<tr>' +
                            '<td>' + conn.name + '</td>' +
                            '<td>' + conn.interface + '</td>' +
                            '<td>' + conn.proxy_type.toUpperCase() + '://' + conn.proxy_addr + ':' + conn.proxy_port + '</td>' +
                            '<td>' + statusIcon + ' ' + statusText + '</td>' +
                            '<td>' + latency + '</td>' +
                            '<td>' + tunnel + '</td>' +
                            '<td>' + (conn.pid || '-') + '</td>' +
                            '<td>' + actions + '</td>' +
                            '</tr>';
                        tbody.append(row);
                    });
                } else {
                    tbody.append('<tr><td colspan="8" class="text-center text-muted">{{ lang._("No connections configured. Add connections in the Connections page.") }}</td></tr>');
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
                        message: '<pre>' + $('<div/>').text(data.result).html() + '</pre>',
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
                if (data.lines && data.lines.length > 0) {
                    $('#log-output').text(data.lines.join('\n'));
                } else {
                    $('#log-output').text('{{ lang._("No logs available. Logs are created when connections are started.") }}');
                }
            });
        }

        // Refresh button
        $('#btn-refresh-status').click(function() {
            refreshStatus();
            refreshLogs();
        });
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
