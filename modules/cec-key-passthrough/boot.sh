#!/bin/sh
# tvroot module: cec-key-passthrough
#
# Symptom fixed: with a Fire TV / streaming stick on HDMI, every Samsung
# remote press took ~3 seconds to reach the stick, while the TV's own UI was
# responsive. Root cause is the vendor applet layer consuming CEC keys:
#   memory/applite/HDMICEC_consume_keys = true
# Setting it false forwards presses to the active HDMI-CEC device normally.
# (Found 2026-10-30 from live testing; libapp-context-manager.so contains
# cec_check_remocon_key and reads this vconf key.)
#
# The key lives in the "memory" vconf layer, so it is re-asserted at boot and
# kept pinned by a supervised loop (a later service can set it back to true).
# This is a runtime setting only - no firmware, no ro-partition writes.
#
# Disabled state: touch <module dir>/disabled or toggle in the manager.
MODULE_DIR=${MODULE_DIR:-/opt/usr/share/selfroot/modules/cec-key-passthrough}
UIDIS="/home/owner/share/tmp/sdk_tools/selfroot-ui/modules/disabled/cec-key-passthrough"

if [ -f "$MODULE_DIR/disabled" ] || [ -s "$UIDIS" ]; then
    systemctl stop tvroot-cec-keys.service >/dev/null 2>&1
    exit 0
fi

vconftool set -f -t bool memory/applite/HDMICEC_consume_keys 0 >/dev/null 2>&1
printf 'HDMICEC_consume_keys -> %s\n' "$(vconftool get memory/applite/HDMICEC_consume_keys 2>&1)"

RD=/run/systemd/system
cat > $RD/tvroot-cec-keys.service <<EOF
[Unit]
Description=TVRoot HDMI-CEC key passthrough
DefaultDependencies=false
[Service]
Type=simple
ExecStart=/bin/sh -c 'while true; do vconftool set -f -t bool memory/applite/HDMICEC_consume_keys 0 >/dev/null 2>&1; sleep 15; done'
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3
EOF
systemctl daemon-reload 2>/dev/null
systemctl restart tvroot-cec-keys.service 2>/dev/null
systemctl is-active tvroot-cec-keys.service 2>&1
exit 0
