#!/bin/sh
# tvroot module: bridge-service
# Owns the management bridge permanently. The relay used to live inside the
# manager UI process, so closing the manager (or the platform reaping it on
# input switch) killed management access. This runs the same relay logic as
# headless managed IL under a supervised systemd service instead: no window,
# no app lifecycle, Restart=always. The manager keeps only a port probe.
# Relay needs no root, but starting it here keeps one owner + one log.
MODULE_DIR=${MODULE_DIR:-/opt/usr/share/selfroot/modules/bridge-service}
EVIDENCE=${EVIDENCE:-/home/owner/share/tmp/sdk_tools/selfroot-evidence}
UIDIS="/home/owner/share/tmp/sdk_tools/selfroot-ui/modules/disabled/bridge-service"
if [ -f "$MODULE_DIR/disabled" ] || [ -s "$UIDIS" ]; then
    systemctl stop tvroot-bridge.service >/dev/null 2>&1
    exit 0
fi
RD=/run/systemd/system
cat > $RD/tvroot-bridge.service <<EOF
[Unit]
Description=TVRoot management bridge (token-gated sdb relay)
DefaultDependencies=false
[Service]
Type=simple
ExecStart=/usr/bin/dotnet $MODULE_DIR/TvRootBridgeRelay.dll
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3
EOF
systemctl daemon-reload 2>/dev/null
systemctl restart tvroot-bridge.service 2>/dev/null
systemctl is-active tvroot-bridge.service 2>&1
exit 0
