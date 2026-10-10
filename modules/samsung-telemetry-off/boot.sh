#!/bin/sh
# tvroot module: samsung-telemetry-off
# Masks Samsung's telemetry/account/update units and kills the ACR service
# app, the Bixby/voice stack, SSO and CIS processes at every boot, then
# supervises two loops via systemd (see below).
#
# WHY SYSTEMD SUPERVISION (learned live 2026-10-10): background shell loops
# spawned from the boot chain die young - orphaned grandchildren of the
# short-lived tarlauncher/sdb shells get reaped (session/cgroup cleanup),
# so PID-file singletons kept vanishing. systemd owns these instead:
# unit files live in /run/systemd/system (tmpfs, rewritten every boot),
# Restart=always with burst limits, and the loops stay dormant (not exit)
# while the module is disabled so supervision never hot-loops.
#
# Two kill classes:
# - systemd units (data-service, pushd, bms, appbinary-manager): mask
#   --runtime + stop. Matching .path watchers stopped too.
# - Tizen apps (acr-service-app, voice-*, bixby-*, ssoservice, CIS):
#   children of launchpad-process-pool; aul relaunches kills within ~20s
#   and de-preloading does not stop it, so voice binaries live renamed
#   and a 30s watchdog reaps the rest. csfs is EXCLUDED (SmartHub home UI
#   framework, demand-launched legitimately - decompiled to confirm).
# NEVER match our own shell: collect PIDs first, then kill excluding $$,
# PID 1 and the launchpad pool. (pkill -f once matched the runner's own
# sh -c cmdline and cut its own transport mid-run.)
#
# TVPlus-button hijack: the button's binding cannot be rewritten, so the
# hijack loop resolves presses into our hands - tvplus stays enabled (no
# system toast), and on any tvplus/deeplinker sighting (button presses
# only, no autostart) it kills them and foregrounds the manager.
#
# Manager visibility: the agent (SMACK User::Pkg::*) only reads
# User::App::Shared files here; the readable label is re-applied below.
# UEP: interpreters may only run scripts via stdin (cat file | bash),
# never as script-file arguments - the unit files use sh -c 'cat | bash'.
#
# Disabled state: touch <module dir>/disabled (loops go dormant <30s,
# services stopped; revival needs a reboot) - or toggle in the manager.
# Undo units (run once as root): systemctl unmask --runtime <unit>
MODULE_DIR=${MODULE_DIR:-/opt/usr/share/selfroot/modules/samsung-telemetry-off}
EVIDENCE=${EVIDENCE:-/home/owner/share/tmp/sdk_tools/selfroot-evidence}
UIDIS="/home/owner/share/tmp/sdk_tools/selfroot-ui/modules/disabled/samsung-telemetry-off"
chsmack -r -a 'User::App::Shared' /opt/usr/share/selfroot/modules 2>/dev/null

if [ -f "$MODULE_DIR/disabled" ] || [ -f "$UIDIS" ]; then
    systemctl stop tvroot-watchdog.service tvroot-hijack.service >/dev/null 2>&1
    exit 0
fi

# vendor opt-out switches (negated ConditionPathExists - persistent).
OPTOUT=/opt/usr/share/systemd/system
mkdir -p $OPTOUT 2>/dev/null
for o in bms org.tizen.voice-app com.samsung.tv.ondevice-voice; do
    touch $OPTOUT/$o 2>/dev/null
done
# (Also found, unused: bms honors /run/user/5001/bms_block, creatable
# even without root.)
for u in data-service \
         pushd \
         bms \
         appbinary-manager; do
    systemctl mask --runtime "$u.service" >/dev/null 2>&1
    systemctl stop "$u.service" >/dev/null 2>&1
    printf '%s -> %s\n' "$u" "$(systemctl is-active "$u.service" 2>&1)"
done
for p in bms.path \
         com.samsung.tv.ondevice-voice.path \
         org.tizen.voice-app.path \
         slive-provider-daemon.path; do
    systemctl mask --runtime "$p" >/dev/null 2>&1
    systemctl stop "$p" >/dev/null 2>&1
done
# binary rename floor: voice binaries stay renamed so aul launches fail.
for b in /opt/usr/apps/org.tizen.voice-app/bin/voice-app \
         /opt/usr/apps/com.samsung.tv.ondevice-voice/bin/ondevice-voice \
         /opt/usr/apps/org.tizen.voice-client/bin/stt-client \
         /opt/usr/apps/org.tizen.voice-client/bin/voice-client \
         /opt/usr/apps/com.samsung.tv.vif/bin/voice-interaction-framework \
         /opt/usr/apps/com.samsung.tv.bixbycapsuleviewer/bin/bixbycapsuleviewer; do
    [ -f "$b" ] && mv "$b" "$b.tvroot-disabled" 2>/dev/null && echo "renamed $b"
done
PATTERNS="acr-service-app|org.tizen.voice-app|ondevice-voice|voice-client|voice-interaction|bixbycapsuleviewer|bixby-prov|ssoservice|bms-service|voice-instant-app|voiceassistant-music|mybixby|wakeup-engine-bixby|iacr|cis-api-service-app"
POOL=$(ps -ef | grep "launchpad-process-pool" | grep -v grep | tr -s " " | cut -d" " -f2 | head -1)
sweep() {
    PIDS=$(ps -ef | grep -E "$PATTERNS" | grep -v grep | tr -s " " | cut -d" " -f2)
    for pid in $PIDS; do
        if [ "$pid" != "$$" ] && [ "$pid" != "1" ] && [ "$pid" != "$POOL" ]; then
            cmd=$(tr '\0' ' ' </proc/$pid/cmdline 2>/dev/null | cut -c1-60)
            kill -9 "$pid" >/dev/null 2>&1 && echo "killed $pid $cmd"
        fi
    done
}
sweep
# supervised loops (unit files below run these via cat|bash for UEP).
WD=/opt/usr/share/selfroot/modules/samsung-telemetry-off/watchdog.sh
HJ=/opt/usr/share/selfroot/modules/samsung-telemetry-off/hijack.sh
RD=/run/systemd/system
cat > $RD/tvroot-watchdog.service <<EOF
[Unit]
Description=TVRoot telemetry watchdog
DefaultDependencies=false
[Service]
Type=simple
ExecStart=/bin/sh -c 'cat $WD | MODULE_DIR=$MODULE_DIR EVIDENCE=$EVIDENCE bash'
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3
EOF
cat > $RD/tvroot-hijack.service <<EOF
[Unit]
Description=TVRoot TVPlus-button hijack
DefaultDependencies=false
[Service]
Type=simple
ExecStart=/bin/sh -c 'cat $HJ | MODULE_DIR=$MODULE_DIR EVIDENCE=$EVIDENCE bash'
Restart=always
RestartSec=2
StartLimitIntervalSec=60
StartLimitBurst=3
EOF
systemctl daemon-reload 2>/dev/null
systemctl restart tvroot-watchdog.service 2>/dev/null
systemctl restart tvroot-hijack.service 2>/dev/null
systemctl is-active tvroot-watchdog.service tvroot-hijack.service 2>&1
exit 0
