#!/bin/sh
# tvroot module: sw-update-off
# Kills Samsung's update machinery at every boot: firmware OTA
# (SWUAutoUpgrade, fw-update-service, USB update path) and app background
# updates (was_background_update). Owner policy: no updates, ever — an OTA
# would wipe the root (squatted app, DB rows, renamed binaries, preload).
#
# Layers (all re-applied every boot; nothing here touches ro partitions):
# - vendor opt-out: /mnt/backup/OS_UPGRADE_FLAG gates swu-auto-upgrade
#   via negated ConditionPathExists (persistent file on the backup volume;
#   delete it to revert this layer).
# - runtime mask + stop of the services and their .path watchers
#   (masks live in tmpfs /run, hence re-applied here).
# - kill sweep for stragglers (same self-exclusion discipline as the
#   telemetry module: PIDs first, skip $$, 1 and the launchpad pool).
#
# Disabled state: touch <module dir>/disabled
# Undo (run once as root): rm /mnt/backup/OS_UPGRADE_FLAG;
#   systemctl unmask --runtime <unit>; systemctl start <unit>
touch /mnt/backup/OS_UPGRADE_FLAG 2>/dev/null
for u in swu-auto-upgrade.service \
         swu-auto-upgrade.path \
         fw-update-service.service \
         fw-update-service.path \
         fw-usb-update-service.service \
         fw-usb-update-service.path \
         was-background-update.service \
         was-background-update.path; do
    systemctl mask --runtime "$u" >/dev/null 2>&1
    systemctl stop "$u" >/dev/null 2>&1
    systemctl reset-failed "$u" >/dev/null 2>&1
done
for u in swu-auto-upgrade fw-update-service was-background-update; do
    printf '%s -> %s\n' "$u" "$(systemctl is-active "$u.service" 2>&1 | head -1)"
done
POOL=$(ps -ef | grep "launchpad-process-pool" | grep -v grep | tr -s " " | cut -d" " -f2 | head -1)
PIDS=$(ps -ef | grep -E "SWUAutoUpgrade|fw-update-service|was_background_update" | grep -v grep | tr -s " " | cut -d" " -f2)
for pid in $PIDS; do
    if [ "$pid" != "$$" ] && [ "$pid" != "1" ] && [ "$pid" != "$POOL" ]; then
        kill -9 "$pid" >/dev/null 2>&1 && echo "killed $pid"
    fi
done
exit 0
