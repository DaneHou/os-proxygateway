{#
  OPNsense Proxy Gateway — Diagnostics Page
  Services → Proxy Gateway → Diagnostics
#}

<script>
    $( document ).ready(function() {

        // --- System Checks ---
        function refreshSystemChecks() {
            ajaxGet('/api/proxygateway/diagnostics/getSystemCheck', {}, function(data, status) {
                if (!data || !data.checks) {
                    $('#system-checks-body').html('<tr><td colspan="3" class="text-danger">Failed to load system checks. Check /tmp/PHP_errors.log</td></tr>');
                    return;
                }
                var c = data.checks;
                var rows = '';

                // tun2socks binary
                var t = c.tun2socks || {};
                var tIcon = (t.exists && t.executable)
                    ? '<span class="fa fa-fw fa-check-circle text-success"></span>'
                    : '<span class="fa fa-fw fa-times-circle text-danger"></span>';
                var tDetail = t.exists
                    ? (t.executable ? (t.version || 'OK') : 'Not executable')
                    : 'Not found at ' + (t.path || '/usr/local/bin/tun2socks') + ' — run: make install-tun2socks';
                rows += '<tr><td>' + tIcon + '</td><td>tun2socks binary</td><td>' + $('<span/>').text(tDetail).html() + '</td></tr>';

                // Plugin enabled
                var pe = c.plugin_enabled || {};
                var peIcon = pe.value
                    ? '<span class="fa fa-fw fa-check-circle text-success"></span>'
                    : '<span class="fa fa-fw fa-times-circle text-danger"></span>';
                rows += '<tr><td>' + peIcon + '</td><td>Plugin enabled</td><td>' + (pe.value ? 'Yes' : 'No — enable in General Settings') + '</td></tr>';

                // Desired config
                var dc = c.desired_config || {};
                var dcIcon = (dc.exists && dc.enabled > 0)
                    ? '<span class="fa fa-fw fa-check-circle text-success"></span>'
                    : '<span class="fa fa-fw fa-exclamation-circle text-warning"></span>';
                var dcDetail = dc.exists
                    ? dc.connections + ' connections (' + dc.enabled + ' enabled)'
                    : 'Not found — click Apply on the Connections page';
                rows += '<tr><td>' + dcIcon + '</td><td>Desired config</td><td>' + $('<span/>').text(dcDetail).html() + '</td></tr>';

                // configd actions
                var ca = c.configd_actions || {};
                var caIcon = ca.responsive
                    ? '<span class="fa fa-fw fa-check-circle text-success"></span>'
                    : '<span class="fa fa-fw fa-times-circle text-danger"></span>';
                rows += '<tr><td>' + caIcon + '</td><td>configd status action</td><td>' + (ca.responsive ? 'Responsive' : 'Not responding — try: service configd restart') + '</td></tr>';

                // Runtime/log dirs
                var rd = c.rundir || {};
                var ld = c.logdir || {};
                var dirsOk = rd.exists && ld.exists;
                var dirsIcon = dirsOk
                    ? '<span class="fa fa-fw fa-check-circle text-success"></span>'
                    : '<span class="fa fa-fw fa-times-circle text-danger"></span>';
                rows += '<tr><td>' + dirsIcon + '</td><td>Runtime directories</td><td>' +
                    (rd.exists ? '/var/run/proxygateway OK' : '/var/run/proxygateway MISSING') + ', ' +
                    (ld.exists ? '/var/log/proxygateway OK' : '/var/log/proxygateway MISSING') + '</td></tr>';

                $('#system-checks-body').html(rows);

                // Last reconfigure output
                var lr = c.last_reconfigure || {};
                if (lr.log) {
                    $('#reconfigure-output').text(lr.log);
                } else {
                    $('#reconfigure-output').text('No reconfigure output yet. Click Apply on the Connections page.');
                }
            });
        }

        // --- Connection Status ---
        function refreshStatus() {
            ajaxGet('/api/proxygateway/diagnostics/getStatus', {}, function(data, status) {
                var tbody = $('#status-table tbody');
                tbody.empty();

                if (data.data && data.data.connections && data.data.connections.length > 0) {
                    // Populate log filter dropdown with connection names
                    var select = $('#log-filter-name');
                    var currentVal = select.val();
                    select.find('option:not(:first,:nth-child(2))').remove();
                    $.each(data.data.connections, function(idx, conn) {
                        if (select.find('option[value="' + conn.name + '"]').length === 0) {
                            select.append($('<option>').val(conn.name).text(conn.name));
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
                        } else if (conn.status === 'degraded') {
                            statusIcon = '<span class="fa fa-fw fa-exclamation-circle text-warning"></span>';
                            statusText = 'Unreachable';
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
                            ? conn.tun_local + ' <-> ' + conn.tun_peer
                            : '-';

                        var row = $('<tr>');
                        row.append($('<td>').text(conn.name));
                        row.append($('<td>').html($('<code>').text(conn.interface)));
                        row.append($('<td>').text(conn.proxy_type.toUpperCase() + '://' + conn.proxy_addr + ':' + conn.proxy_port));
                        row.append($('<td>').html(statusIcon + ' ' + statusText));
                        row.append($('<td>').text(latency));
                        row.append($('<td>').text(tunnel));
                        row.append($('<td>').text(conn.pid || '-'));

                        var actionsCell = $('<td>');
                        if (conn.status === 'up' || conn.status === 'down' || conn.status === 'degraded') {
                            actionsCell.append(
                                $('<button class="btn btn-xs btn-default btn-test">').attr('data-name', conn.name)
                                    .html('<span class="fa fa-fw fa-heartbeat"></span> Test')
                            );
                        } else if (conn.status === 'not_running') {
                            actionsCell.append($('<span class="text-muted">').text('Apply to start'));
                        }
                        row.append(actionsCell);

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

        // Populate the log filter dropdown from available log files
        function populateLogFilter() {
            ajaxGet('/api/proxygateway/diagnostics/getLogConnections', {}, function(data, status) {
                var select = $('#log-filter-name');
                var currentVal = select.val();
                select.find('option:not(:first)').remove();
                if (data.connections) {
                    $.each(data.connections, function(idx, name) {
                        select.append($('<option>').val(name).text(name));
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
        $('#btn-refresh-all').click(function() {
            refreshSystemChecks();
            refreshStatus();
            refreshLogs();
        });
        $('#btn-refresh-logs').click(refreshLogs);

        // Auto-refresh every 10 seconds
        setInterval(function() {
            refreshStatus();
            refreshLogs();
        }, 10000);

        // Initial load
        refreshSystemChecks();
        refreshStatus();
        populateLogFilter();
        refreshLogs();
    });
</script>

<!-- System Checks -->
<div class="content-box">
    <div class="content-box-header">
        <h3>{{ lang._('System Checks') }}
            <button id="btn-refresh-all" class="btn btn-xs btn-default pull-right">
                <span class="fa fa-fw fa-refresh"></span> {{ lang._('Refresh All') }}
            </button>
        </h3>
    </div>
    <table class="table table-condensed table-hover">
        <thead>
            <tr>
                <th style="width:2em;"></th>
                <th style="width:12em;">{{ lang._('Check') }}</th>
                <th>{{ lang._('Details') }}</th>
            </tr>
        </thead>
        <tbody id="system-checks-body">
            <tr><td colspan="3" class="text-center text-muted">{{ lang._('Loading...') }}</td></tr>
        </tbody>
    </table>
</div>

<!-- Last Reconfigure Output -->
<div class="content-box" style="margin-top: 1em;">
    <div class="content-box-header">
        <h3>{{ lang._('Last Apply / Reconfigure Output') }}</h3>
    </div>
    <pre id="reconfigure-output" style="max-height: 300px; overflow-y: auto; font-size: 12px;">{{ lang._('Loading...') }}</pre>
</div>

<!-- Connection Status -->
<div class="content-box" style="margin-top: 1em;">
    <div class="content-box-header">
        <h3>{{ lang._('Connection Status') }}</h3>
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

<!-- Logs -->
<div class="content-box" style="margin-top: 1em;">
    <div class="content-box-header">
        <h3>{{ lang._('Logs') }}
            <div class="pull-right" style="display: flex; gap: 5px; align-items: center;">
                <select id="log-filter-name" class="selectpicker" data-width="200px">
                    <option value="">{{ lang._('All connections') }}</option>
                    <option value="reconfigure">{{ lang._('Reconfigure log') }}</option>
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
