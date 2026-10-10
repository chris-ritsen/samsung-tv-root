#!/bin/sh
# tvroot module: samsung-telemetry-off
# Masks Samsung's telemetry/account/update units and kills the ACR service
# app, the Bixby/voice stack, SSO, csfs and CIS processes at every boot,
# then leaves a watchdog to keep them dead.
#
# Two kill classes (learned live 2026-10-10):
# - systemd units (data-service, pushd, bms, appbinary-manager): mask
#   --runtime + stop, same pattern as ad-telemetry-daemons-off.
# - Tizen apps (acr-service-app, voice-*, bixby-*, ssoservice, csfs, CIS):
#   children of launchpad-process-pool; aul relaunches them within ~20s of
#   a plain kill, and de-preloading (.all_preload_rw_list edit) does NOT
#   stop it (verified: list stayed edited, apps still launched). So a
#   background watchdog reaps stragglers every 30s until the module is
#   disabled. The watchdog exits on its own when disabled (own flag file
#   or the live UI override); revival of killed apps needs a reboot.
#   NEVER match our own shell: collect PIDs first, then kill excluding $$,
#   PID 1 and the launchpad pool. (pkill -f once matched the runner's own
#   sh -c cmdline and cut its own transport mid-run.)
#
# Disabled state: touch <module dir>/disabled (watchdog exits <30s;
# revival needs a reboot) — or toggle in the on-TV manager.
# Undo units (run once as root): systemctl unmask --runtime <unit>
# Manager visibility: the agent (SMACK User::Pkg::*) can only read files
# labeled User::App::Shared here (root-created files land as User and are
# invisible to it — "No module directories found" with no error). Re-apply
# the readable label every boot in case anything relabels the tree.
chsmack -r -a 'User::App::Shared' /opt/usr/share/selfroot/modules 2>/dev/null
# Vendor opt-out switches: the bms / voice-app / ondevice-voice starter
# units skip when the matching path exists under
# /opt/usr/share/systemd/system (negated ConditionPathExists) — persistent
# boot-gating, reverted by deleting the file. (Also found, unused: bms
# honors /run/user/5001/bms_block, creatable even without root.)
OPTOUT=/opt/usr/share/systemd/system
mkdir -p $OPTOUT 2>/dev/null
for o in bms org.tizen.voice-app com.samsung.tv.ondevice-voice; do
    touch $OPTOUT/$o 2>/dev/null
done
# Binary rename (the floor that always works): aul relaunches killed apps
# within ~20s no matter the autorestart flags, and de-preloading does not
# stop it — so the voice binaries live renamed and launches fail cleanly.
# Idempotent; revert by moving back (sha256 list in TV backups). The 30s
# watchdog below stays as backstop (e.g. after an OTA restores binaries).
for b in /opt/usr/apps/org.tizen.voice-app/bin/voice-app \
         /opt/usr/apps/com.samsung.tv.ondevice-voice/bin/ondevice-voice \
         /opt/usr/apps/org.tizen.voice-client/bin/stt-client \
         /opt/usr/apps/org.tizen.voice-client/bin/voice-client \
         /opt/usr/apps/com.samsung.tv.vif/bin/voice-interaction-framework \
         /opt/usr/apps/com.samsung.tv.bixbycapsuleviewer/bin/bixbycapsuleviewer; do
    [ -f "$b" ] && mv "$b" "$b.tvroot-disabled" 2>/dev/null && echo "renamed $b"
done
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
PATTERNS="acr-service-app|org.tizen.voice-app|ondevice-voice|voice-client|voice-interaction|bixbycapsuleviewer|bixby-prov|ssoservice|/csfs|bms-service|voice-instant-app|voiceassistant-music|mybixby|wakeup-engine-bixby|iacr|cis-api-service-app"
POOL=$(ps -ef | grep "launchpad-process-pool" | grep -v grep | tr -s " " | cut -d" " -f2 | head -1)
sweep() {
    PIDS=$(ps -ef | grep -E "$PATTERNS" | grep -v grep | tr -s " " | cut -d" " -f2)
    for pid in $PIDS; do
        if [ "$pid" != "$$" ] && [ "$pid" != "1" ] && [ "$pid" != "$POOL" ]; then
            kill -9 "$pid" >/dev/null 2>&1 && echo "killed $pid"
        fi
    done
}
sweep
# persistent watchdog (see header): reaps aul respawns every 30s.
UIDIS="/home/owner/share/tmp/sdk_tools/selfroot-ui/modules/disabled/samsung-telemetry-off"
( while true; do
    if [ -f "$MODULE_DIR/disabled" ] || [ -f "$UIDIS" ]; then exit 0; fi
    PIDS=$(ps -ef | grep -E "$PATTERNS" | grep -v grep | tr -s " " | cut -d" " -f2)
    for pid in $PIDS; do
        if [ "$pid" != "$$" ] && [ "$pid" != "1" ] && [ "$pid" != "$POOL" ]; then
            kill -9 "$pid" >/dev/null 2>&1 && echo "$(date '+%T') watchdog killed $pid" >> "$EVIDENCE/module-samsung-telemetry-off-watchdog.log"
        fi
    done
    sleep 30
  done ) >/dev/null 2>&1 < /dev/null &
echo "watchdog started"
exit 0
