{#
  OPNsense Proxy Gateway — Main Configuration Page
  Services → Proxy Gateway → Connections
#}

<script>
    $( document ).ready(function() {
        // Load general settings
        mapDataToFormUI({'frm_GeneralSettings': "/api/proxygateway/settings/get"}).done(function(){
            formatTokenizersUI();
            $('.selectpicker').selectpicker('refresh');
        });

        // Connection grid
        $("#grid-connections").UIBootgrid({
            search: '/api/proxygateway/connection/searchItem',
            get: '/api/proxygateway/connection/getItem/',
            set: '/api/proxygateway/connection/setItem/',
            add: '/api/proxygateway/connection/addItem/',
            del: '/api/proxygateway/connection/delItem/',
            toggle: '/api/proxygateway/connection/toggleItem/',
            options: {
                formatters: {
                    "commands": function(column, row) {
                        return '<button type="button" class="btn btn-xs btn-default command-edit bootgrid-tooltip" ' +
                            'data-row-id="' + row.uuid + '"><span class="fa fa-fw fa-pencil"></span></button> ' +
                            '<button type="button" class="btn btn-xs btn-default command-copy bootgrid-tooltip" ' +
                            'data-row-id="' + row.uuid + '"><span class="fa fa-fw fa-clone"></span></button> ' +
                            '<button type="button" class="btn btn-xs btn-default command-delete bootgrid-tooltip" ' +
                            'data-row-id="' + row.uuid + '"><span class="fa fa-fw fa-trash-o"></span></button>';
                    },
                    "status": function(column, row) {
                        if (row.enabled == "1") {
                            return '<span class="fa fa-fw fa-check-circle text-success"></span>';
                        } else {
                            return '<span class="fa fa-fw fa-times-circle text-danger"></span>';
                        }
                    },
                    "connectionStatus": function(column, row) {
                        if (row.connectionStatus === 'up') {
                            return '<span class="fa fa-fw fa-plug text-success" title="Connected"></span> Connected';
                        } else if (row.connectionStatus === 'down') {
                            return '<span class="fa fa-fw fa-plug text-danger" title="Down"></span> Down';
                        } else if (row.connectionStatus === 'disabled') {
                            return '<span class="fa fa-fw fa-minus-circle text-muted" title="Disabled"></span> Disabled';
                        } else {
                            return '<span class="fa fa-fw fa-question-circle text-warning" title="Not Running"></span> Not Running';
                        }
                    },
                    "proxyInfo": function(column, row) {
                        return row.proxyType.toUpperCase() + '://' + row.proxyServer + ':' + row.proxyPort;
                    }
                }
            }
        });

        // Reconfigure (apply changes)
        $("#reconfigureAct").SimpleActionButton({
            onPreAction: function() {
                const dfObj = new $.Deferred();
                saveFormToEndpoint("/api/proxygateway/settings/set", 'frm_GeneralSettings',
                    function() { dfObj.resolve(); },
                    true,
                    function() { dfObj.reject(); }
                );
                return dfObj;
            },
            onAction: function(data, status) {
                updateServiceControlUI('proxygateway');
                // Reload grid to update connection status
                $('#grid-connections').bootgrid('reload');
                // Show reconfigure output so the user can see errors
                if (data && data.response) {
                    var escaped = $('<div/>').text(data.response).html();
                    var hasError = data.response.toLowerCase().indexOf('error') >= 0 ||
                                   data.response.toLowerCase().indexOf('fail') >= 0;
                    BootstrapDialog.show({
                        title: hasError ? '{{ lang._("Reconfigure Errors") }}' : '{{ lang._("Reconfigure Result") }}',
                        message: '<pre style="max-height:400px;overflow:auto;">' + escaped + '</pre>',
                        type: hasError ? BootstrapDialog.TYPE_WARNING : BootstrapDialog.TYPE_SUCCESS
                    });
                }
            }
        });

        // Service control buttons
        updateServiceControlUI('proxygateway');

        // Toggle auth fields visibility
        function toggleAuthFields() {
            if ($('#connection\\.authEnabled').is(':checked')) {
                $('.auth_fields').closest('tr').show();
            } else {
                $('.auth_fields').closest('tr').hide();
            }
        }
        $(document).on('change', '#connection\\.authEnabled', toggleAuthFields);

        // Toggle DNS fields visibility
        function toggleDnsFields() {
            if ($('#connection\\.dnsMode').val() === 'custom') {
                $('.dns_custom_fields').closest('tr').show();
            } else {
                $('.dns_custom_fields').closest('tr').hide();
            }
        }
        $(document).on('change', '#connection\\.dnsMode', toggleDnsFields);

        // Toggle health check fields visibility
        function toggleHealthFields() {
            if ($('#connection\\.healthCheckEnabled').is(':checked')) {
                $('.health_fields').closest('tr').show();
            } else {
                $('.health_fields').closest('tr').hide();
            }
        }
        $(document).on('change', '#connection\\.healthCheckEnabled', toggleHealthFields);
    });
</script>

<div class="tab-content content-box">
    <!-- General Settings Tab -->
    <div id="general" class="tab-pane fade in active">
        <div class="content-box" style="padding-bottom: 1.5em;">
            {{ partial("layout_partials/base_form",['fields':generalForm,'id':'frm_GeneralSettings'])}}
        </div>
    </div>
</div>

<!-- Connections Grid -->
<div class="tab-content content-box">
    <table id="grid-connections" class="table table-condensed table-hover table-striped"
           data-editDialog="DialogConnection"
           data-editAlert="ConnectionChangeMessage">
        <thead>
            <tr>
                <th data-column-id="uuid" data-type="string" data-identifier="true" data-visible="false">ID</th>
                <th data-column-id="enabled" data-width="5em" data-type="string" data-formatter="status">{{ lang._('Enabled') }}</th>
                <th data-column-id="name" data-type="string">{{ lang._('Name') }}</th>
                <th data-column-id="connectionStatus" data-width="9em" data-type="string" data-formatter="connectionStatus" data-sortable="false">{{ lang._('Connection') }}</th>
                <th data-column-id="description" data-type="string">{{ lang._('Description') }}</th>
                <th data-column-id="proxyType" data-type="string" data-formatter="proxyInfo" data-visible="false">{{ lang._('Proxy') }}</th>
                <th data-column-id="proxyServer" data-type="string">{{ lang._('Server') }}</th>
                <th data-column-id="proxyPort" data-type="string" data-width="6em">{{ lang._('Port') }}</th>
                <th data-column-id="commands" data-width="10em" data-formatter="commands"
                    data-sortable="false">{{ lang._('Commands') }}</th>
            </tr>
        </thead>
        <tbody>
        </tbody>
        <tfoot>
            <tr>
                <td></td>
                <td>
                    <button data-action="add" type="button" class="btn btn-xs btn-primary">
                        <span class="fa fa-fw fa-plus"></span>
                    </button>
                    <button data-action="deleteSelected" type="button" class="btn btn-xs btn-default">
                        <span class="fa fa-fw fa-trash-o"></span>
                    </button>
                </td>
            </tr>
        </tfoot>
    </table>
</div>

<div class="col-md-12">
    <div id="ConnectionChangeMessage" class="alert alert-info" style="display: none" role="alert">
        {{ lang._('After changing settings, please remember to apply them.') }}
    </div>
    <hr/>
    <button class="btn btn-primary" id="reconfigureAct"
            data-endpoint='/api/proxygateway/service/reconfigure'
            data-label="{{ lang._('Apply') }}"
            data-error-title="{{ lang._('Error reconfiguring Proxy Gateway') }}"
            type="button">
    </button>
</div>

{# Connection Edit Dialog #}
{{ partial("layout_partials/base_dialog",['fields':connectionForm,'id':'DialogConnection','label':lang._('Edit Connection')]) }}
