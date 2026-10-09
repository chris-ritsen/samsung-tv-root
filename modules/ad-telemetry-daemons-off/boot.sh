#!/bin/sh
# tvroot module: ad-telemetry-daemons-off
# Masks and stops Samsung's ad/telemetry daemons at every boot.
#
# Why mask --runtime: the units live on the read-only root image with
# Restart=always, and /run/systemd/system is tmpfs, so a plain stop just
# respawns and a persistent mask has nowhere to live. The boot-time module
# runner re-applies this every boot, right after the root chain lands —
# the daemons get ~60-90s of life per power cycle and nothing else.
#
# Disabled state: touch <module dir>/disabled
# Undo (run once as root): systemctl unmask --runtime <unit>; systemctl start <unit>
for u in adagent-service \
         pisa-service \
         canalysis-service \
         slive-provider-daemon \
         contents-recognition-service \
         com.samsung.tv.context-aware-agent \
         com.samsung.tv.context-aware-service \
         com.samsung.tv.cis-api-service-app; do
    systemctl mask --runtime "$u.service" >/dev/null 2>&1
    systemctl stop "$u.service" >/dev/null 2>&1
    printf '%s -> %s\n' "$u" "$(systemctl is-active "$u.service" 2>&1)"
done
exit 0