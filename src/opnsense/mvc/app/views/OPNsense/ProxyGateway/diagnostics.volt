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

        // --- Helper: format bytes ---
        function formatBytes(bytes) {
            if (!bytes || bytes === '0') return '0 B';
            bytes = parseInt(bytes);
            if (isNaN(bytes)) return '-';
            var units = ['B', 'KB', 'MB', 'GB', 'TB'];
            var i = 0;
            while (bytes >= 1024 && i < units.length - 1) {
                bytes /= 1024;
                i++;
            }
            return bytes.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
        }

        // --- Helper: format uptime ---
        function formatUptime(seconds) {
            if (!seconds || seconds <= 0) return '-';
            seconds = parseInt(seconds);
            var d = Math.floor(seconds / 86400);
            var h = Math.floor((seconds % 86400) / 3600);
            var m = Math.floor((seconds % 3600) / 60);
            var parts = [];
            if (d > 0) parts.push(d + 'd');
            if (h > 0) parts.push(h + 'h');
            parts.push(m + 'm');
            return parts.join(' ');
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

                        var latencyText = '-';
                        if (conn.health && conn.health.latency_ms && conn.health.latency_ms !== '-1') {
                            latencyText = conn.health.latency_ms + ' ms';
                        }

                        var tunnel = (conn.tun_local && conn.tun_local !== '-')
                            ? conn.tun_local + ' <-> ' + conn.tun_peer
                            : '-';

                        var row = $('<tr>');
                        row.append($('<td>').text(conn.name));
                        row.append($('<td>').html($('<code>').text(conn.interface)));
                        var proxyCell = $('<td>');
                        var proxyText = conn.proxy_type.toUpperCase() + '://' + conn.proxy_addr + ':' + conn.proxy_port;
                        proxyCell.text(proxyText);
                        if (conn.active_proxy === 'backup') {
                            proxyCell.append(' ');
                            proxyCell.append($('<span class="label label-warning">').text('BACKUP'));
                        }
                        row.append(proxyCell);
                        row.append($('<td>').html(statusIcon + ' ' + statusText));
                        var latencyCell = $('<td>');
                        latencyCell.text(latencyText + ' ');
                        // Add health history button for active connections
                        if (conn.status === 'up' || conn.status === 'degraded') {
                            latencyCell.append(
                                $('<button class="btn btn-xs btn-default btn-health-history">').attr('data-name', conn.name)
                                    .html('<span class="fa fa-fw fa-history"></span>')
                                    .attr('title', 'Health History')
                            );
                        }
                        row.append(latencyCell);
                        row.append($('<td>').text(tunnel));

                        var trafficIn = formatBytes(conn.traffic_in);
                        var trafficOut = formatBytes(conn.traffic_out);
                        row.append($('<td>').text(trafficIn + ' / ' + trafficOut));

                        var uptime = formatUptime(conn.uptime_seconds);
                        row.append($('<td>').text(uptime));

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
                    tbody.append('<tr><td colspan="10" class="text-center text-muted">{{ lang._("No connections configured. Add connections in the Connections page.") }}</td></tr>');
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

        // Health history button
        $(document).on('click', '.btn-health-history', function() {
            var name = $(this).data('name');
            ajaxGet('/api/proxygateway/diagnostics/getHealthHistory', {name: name, limit: 50}, function(data, status) {
                if (!data || !data.history) return;
                var html = '<table class="table table-condensed table-striped"><thead><tr>';
                html += '<th>Time</th><th>Status</th><th>Latency</th><th>HTTP</th>';
                html += '</tr></thead><tbody>';
                // Show most recent first
                var history = data.history.reverse();
                $.each(history, function(i, entry) {
                    var d = new Date(entry.timestamp * 1000);
                    var statusIcon = entry.status === 'up'
                        ? '<span class="fa fa-circle text-success"></span>'
                        : '<span class="fa fa-circle text-danger"></span>';
                    html += '<tr>';
                    html += '<td>' + d.toLocaleString() + '</td>';
                    html += '<td>' + statusIcon + ' ' + entry.status + '</td>';
                    html += '<td>' + (entry.latency_ms > 0 ? entry.latency_ms + ' ms' : '-') + '</td>';
                    html += '<td>' + (entry.http_code || '-') + '</td>';
                    html += '</tr>';
                });
                html += '</tbody></table>';
                BootstrapDialog.show({
                    title: 'Health History: ' + name,
                    message: html,
                    size: BootstrapDialog.SIZE_WIDE
                });
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

        // --- Speed Test Results ---
        function refreshSpeedTests() {
            ajaxGet('/api/proxygateway/diagnostics/getSpeedTestResults', {}, function(data, status) {
                var tbody = $('#speedtest-table tbody');
                tbody.empty();

                if (!data || !data.data || data.data.length === 0) {
                    tbody.append('<tr><td colspan="5" class="text-center text-muted">{{ lang._("No speed test results. Enable speed tests in General Settings and apply.") }}</td></tr>');
                    return;
                }

                $.each(data.data, function(idx, item) {
                    var row = $('<tr>');
                    row.append($('<td>').text(item.name));

                    // Speed
                    row.append($('<td>').html(formatSpeedCell(item.result)));

                    // Last tested
                    var lastTested = '-';
                    if (item.result && item.result.timestamp) {
                        var d = new Date(parseInt(item.result.timestamp) * 1000);
                        lastTested = d.toLocaleTimeString();
                    }
                    row.append($('<td>').text(lastTested));

                    // Test URL
                    var testUrl = '-';
                    if (item.result && item.result.test_url) {
                        testUrl = item.result.test_url;
                    }
                    row.append($('<td>').html($('<span>').css('font-size', '11px').text(testUrl)));

                    // Actions
                    var actionsCell = $('<td>');
                    actionsCell.append(
                        $('<button class="btn btn-xs btn-default btn-speedtest">').attr('data-name', item.name)
                            .html('<span class="fa fa-fw fa-tachometer"></span> Run')
                    );
                    row.append(actionsCell);

                    tbody.append(row);
                });
            });
        }

        function formatSpeedCell(result) {
            if (!result) {
                return '<span class="text-muted">-</span>';
            }
            if (result.status === 'error') {
                return '<span class="text-danger"><span class="fa fa-fw fa-times-circle"></span> Error</span>';
            }
            var mbps = parseFloat(result.speed_mbps || 0);
            var colorClass = 'text-danger';
            if (mbps >= 10) {
                colorClass = 'text-success';
            } else if (mbps >= 1) {
                colorClass = 'text-warning';
            }
            var label = mbps.toFixed(2) + ' Mbps';
            if (result.status === 'timeout') {
                label += ' (partial)';
            }
            return '<span class="' + colorClass + '">' + label + '</span>';
        }

        // Run speed test button
        $(document).on('click', '.btn-speedtest', function() {
            var name = $(this).data('name');
            var btn = $(this);
            btn.prop('disabled', true).html('<span class="fa fa-fw fa-spinner fa-spin"></span>');

            ajaxCall('/api/proxygateway/diagnostics/runSpeedTest', {name: name}, function(data, status) {
                btn.prop('disabled', false).html('<span class="fa fa-fw fa-tachometer"></span> Run');
                if (data.result) {
                    BootstrapDialog.show({
                        title: 'Speed Test: ' + name,
                        message: '<pre>' + $('<div/>').text(data.result).html() + '</pre>',
                        type: data.result.indexOf('OK') >= 0 ? BootstrapDialog.TYPE_SUCCESS : BootstrapDialog.TYPE_DANGER
                    });
                }
                refreshSpeedTests();
            });
        });

        // Auto-refresh every 10 seconds
        setInterval(function() {
            refreshStatus();
            refreshLogs();
        }, 10000);

        // Refresh speed tests every 30 seconds
        setInterval(refreshSpeedTests, 30000);

        // Initial load
        refreshSystemChecks();
        refreshStatus();
        refreshSpeedTests();
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
                <th>{{ lang._('Traffic In/Out') }}</th>
                <th>{{ lang._('Uptime') }}</th>
                <th>{{ lang._('PID') }}</th>
                <th>{{ lang._('Actions') }}</th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="10" class="text-center text-muted">{{ lang._('Loading...') }}</td></tr>
        </tbody>
    </table>
</div>

<!-- Speed Test Results -->
<div class="content-box" style="margin-top: 1em;">
    <div class="content-box-header">
        <h3>{{ lang._('Speed Test Results') }}
            <button id="btn-refresh-speedtest" class="btn btn-xs btn-default pull-right" onclick="refreshSpeedTests && refreshSpeedTests()">
                <span class="fa fa-fw fa-refresh"></span> {{ lang._('Refresh') }}
            </button>
        </h3>
    </div>
    <table id="speedtest-table" class="table table-condensed table-hover table-striped">
        <thead>
            <tr>
                <th>{{ lang._('Connection') }}</th>
                <th>{{ lang._('Speed') }}</th>
                <th>{{ lang._('Last Tested') }}</th>
                <th>{{ lang._('Test URL') }}</th>
                <th>{{ lang._('Actions') }}</th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="5" class="text-center text-muted">{{ lang._('Loading...') }}</td></tr>
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
