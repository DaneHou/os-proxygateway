PLUGIN_NAME=	os-proxygateway
PLUGIN_VERSION=	0.1.0
PLUGIN_ARCH?=	freebsd-amd64

TUN2SOCKS_VERSION=	2.6.0
TUN2SOCKS_URL=		https://github.com/xjasonlyu/tun2socks/releases/download/v$(TUN2SOCKS_VERSION)/tun2socks-$(PLUGIN_ARCH).zip

PREFIX?=	/usr/local
DESTDIR?=

SCRIPTS_DIR=	$(DESTDIR)$(PREFIX)/opnsense/scripts/OPNsense/ProxyGateway
MVC_DIR=	$(DESTDIR)$(PREFIX)/opnsense/mvc/app
ACTIONS_DIR=	$(DESTDIR)$(PREFIX)/opnsense/service/conf/actions.d
PLUGINS_DIR=	$(DESTDIR)$(PREFIX)/etc/inc/plugins.inc.d
RCD_DIR=	$(DESTDIR)$(PREFIX)/etc/rc.d
BIN_DIR=	$(DESTDIR)$(PREFIX)/bin

.PHONY: all install install-tun2socks uninstall clean fetch-tun2socks

all:
	@echo ""
	@echo "os-proxygateway — Multi-Proxy Gateway for OPNsense"
	@echo ""
	@echo "Targets:"
	@echo "  make install          Install plugin + download tun2socks"
	@echo "  make install-plugin   Install plugin files only (no tun2socks)"
	@echo "  make install-tun2socks Download and install tun2socks binary"
	@echo "  make uninstall        Remove all plugin files"
	@echo "  make package          Create a .pkg file (requires pkg tools)"
	@echo ""
	@echo "Quick start on OPNsense:"
	@echo "  make install && configctl configd actions"
	@echo ""

install: install-plugin install-tun2socks activate
	@echo ""
	@echo "=== Installation complete ==="
	@echo "Go to: Services → Proxy Gateway → Connections"
	@echo ""

install-plugin:
	@echo ">>> Installing plugin files..."
	# Plugin hooks
	@mkdir -p $(PLUGINS_DIR)
	@cp src/etc/inc/plugins.inc.d/proxygateway.inc $(PLUGINS_DIR)/

	# MVC controllers
	@mkdir -p $(MVC_DIR)/controllers/OPNsense/ProxyGateway/Api
	@mkdir -p $(MVC_DIR)/controllers/OPNsense/ProxyGateway/forms
	@cp src/opnsense/mvc/app/controllers/OPNsense/ProxyGateway/IndexController.php \
		$(MVC_DIR)/controllers/OPNsense/ProxyGateway/
	@cp src/opnsense/mvc/app/controllers/OPNsense/ProxyGateway/Api/*.php \
		$(MVC_DIR)/controllers/OPNsense/ProxyGateway/Api/
	@cp src/opnsense/mvc/app/controllers/OPNsense/ProxyGateway/forms/*.xml \
		$(MVC_DIR)/controllers/OPNsense/ProxyGateway/forms/

	# MVC models
	@mkdir -p $(MVC_DIR)/models/OPNsense/ProxyGateway/ACL
	@mkdir -p $(MVC_DIR)/models/OPNsense/ProxyGateway/Menu
	@cp src/opnsense/mvc/app/models/OPNsense/ProxyGateway/ProxyGateway.php \
		$(MVC_DIR)/models/OPNsense/ProxyGateway/
	@cp src/opnsense/mvc/app/models/OPNsense/ProxyGateway/ProxyGateway.xml \
		$(MVC_DIR)/models/OPNsense/ProxyGateway/
	@cp src/opnsense/mvc/app/models/OPNsense/ProxyGateway/ACL/ACL.xml \
		$(MVC_DIR)/models/OPNsense/ProxyGateway/ACL/
	@cp src/opnsense/mvc/app/models/OPNsense/ProxyGateway/Menu/Menu.xml \
		$(MVC_DIR)/models/OPNsense/ProxyGateway/Menu/

	# MVC views
	@mkdir -p $(MVC_DIR)/views/OPNsense/ProxyGateway
	@cp src/opnsense/mvc/app/views/OPNsense/ProxyGateway/*.volt \
		$(MVC_DIR)/views/OPNsense/ProxyGateway/

	# Backend scripts
	@mkdir -p $(SCRIPTS_DIR)
	@cp src/opnsense/scripts/OPNsense/ProxyGateway/*.sh $(SCRIPTS_DIR)/
	@cp src/opnsense/scripts/OPNsense/ProxyGateway/*.py $(SCRIPTS_DIR)/
	@chmod +x $(SCRIPTS_DIR)/*.sh $(SCRIPTS_DIR)/*.py

	# configd actions
	@mkdir -p $(ACTIONS_DIR)
	@cp src/opnsense/service/conf/actions.d/actions_proxygateway.conf $(ACTIONS_DIR)/

	# rc.d service script
	@mkdir -p $(RCD_DIR)
	@cp src/usr/local/etc/rc.d/opnsense-proxygateway $(RCD_DIR)/
	@chmod +x $(RCD_DIR)/opnsense-proxygateway

	# Runtime directories
	@mkdir -p /var/run/proxygateway /var/log/proxygateway
	@echo ">>> Plugin files installed."

install-tun2socks:
	@echo ">>> Downloading tun2socks v$(TUN2SOCKS_VERSION) for $(PLUGIN_ARCH)..."
	@mkdir -p $(BIN_DIR)
	@if [ ! -x $(BIN_DIR)/tun2socks ]; then \
		fetch -o /tmp/tun2socks.zip $(TUN2SOCKS_URL) && \
		unzip -o /tmp/tun2socks.zip -d /tmp/ && \
		mv /tmp/tun2socks-$(PLUGIN_ARCH) $(BIN_DIR)/tun2socks && \
		chmod +x $(BIN_DIR)/tun2socks && \
		rm -f /tmp/tun2socks.zip && \
		echo ">>> tun2socks installed: $$($(BIN_DIR)/tun2socks --version 2>&1 | head -1)"; \
	else \
		echo ">>> tun2socks already installed: $$($(BIN_DIR)/tun2socks --version 2>&1 | head -1)"; \
	fi

activate:
	@echo ">>> Activating plugin..."
	@sysrc proxygateway_enable=YES 2>/dev/null || true
	# Flush menu cache (MenuSystem.php caches to this file)
	@rm -f /tmp/opnsense_menu_cache.xml 2>/dev/null || true
	# Flush Volt template cache and PHP opcache
	@rm -f $(DESTDIR)$(PREFIX)/opnsense/mvc/app/cache/*.php 2>/dev/null || true
	# Verify plugin hooks load without PHP errors
	@echo ">>> Checking plugin for PHP errors..."
	@php -l $(PLUGINS_DIR)/proxygateway.inc 2>&1 || true
	@php -l $(MVC_DIR)/models/OPNsense/ProxyGateway/ProxyGateway.php 2>&1 || true
	# Restart configd to pick up new actions
	@service configd restart 2>/dev/null || true
	# Restart web GUI to flush opcache and pick up new menu/controllers
	@service php-fpm restart 2>/dev/null || true
	# Verify plugin registration
	@echo ">>> Verifying plugin registration..."
	@pluginctl -c 2>/dev/null || true
	@echo ""
	@echo ">>> Plugin activated."
	@echo ">>> Hard-refresh your browser (Ctrl+Shift+R) to see the menu."
	@echo ""
	@echo ">>> If menu still missing, check: cat /tmp/PHP_errors.log"
	@echo ">>> Debug hooks: pluginctl (list all plugin hooks)"

uninstall:
	@echo ">>> Stopping service..."
	@$(PREFIX)/etc/rc.d/opnsense-proxygateway stop 2>/dev/null || true
	@echo ">>> Removing plugin files..."
	@rm -rf $(MVC_DIR)/controllers/OPNsense/ProxyGateway
	@rm -rf $(MVC_DIR)/models/OPNsense/ProxyGateway
	@rm -rf $(MVC_DIR)/views/OPNsense/ProxyGateway
	@rm -rf $(SCRIPTS_DIR)
	@rm -f $(ACTIONS_DIR)/actions_proxygateway.conf
	@rm -f $(PLUGINS_DIR)/proxygateway.inc
	@rm -f $(RCD_DIR)/opnsense-proxygateway
	@rm -rf /var/run/proxygateway
	@rm -f /tmp/opnsense_menu_cache.xml 2>/dev/null || true
	@rm -f $(DESTDIR)$(PREFIX)/opnsense/mvc/app/cache/*.php 2>/dev/null || true
	@sysrc -x proxygateway_enable 2>/dev/null || true
	@$(PREFIX)/sbin/configctl configd actions 2>/dev/null || true
	@echo ">>> Plugin removed. tun2socks binary left in place."
	@echo ">>> To also remove tun2socks: rm $(BIN_DIR)/tun2socks"

clean:
	@rm -f /tmp/tun2socks.zip
	@rm -rf work/
