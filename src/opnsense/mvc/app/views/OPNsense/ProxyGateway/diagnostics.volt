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

        // Refresh buttons
        $('#btn-refresh-all').click(function() {
            refreshSystemChecks();
            refreshStatus();
            refreshLogs();
        });
        $('#btn-refresh-logs').click(refreshLogs);

        // Auto-refresh every 10 seconds
        setInterval(refreshStatus, 10000);

        // Initial load
        refreshSystemChecks();
        refreshStatus();
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
            <div class="pull-right">
                <select id="log-filter-name" class="selectpicker" data-width="200px">
                    <option value="">{{ lang._('All connections') }}</option>
                    <option value="reconfigure">{{ lang._('Reconfigure log') }}</option>
                </select>
                <button id="btn-refresh-logs" class="btn btn-xs btn-default">
                    <span class="fa fa-fw fa-refresh"></span> {{ lang._('Refresh') }}
                </button>
            </div>
        </h3>
    </div>
    <pre id="log-output" style="max-height: 400px; overflow-y: auto; font-size: 12px;">{{ lang._('Loading...') }}</pre>
</div>
