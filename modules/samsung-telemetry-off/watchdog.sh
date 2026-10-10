#!/bin/sh
# tvroot watchdog loop: reaps telemetry respawns every 30s. Run supervised
# (tvroot-watchdog.service runs this via cat|bash - never as a script-file
# argument, UEP forbids that). Goes dormant while the module is disabled
# (never exits - supervision would hot-loop restarts).
# Env: MODULE_DIR, EVIDENCE (set by the unit file).
PATTERNS="acr-service-app|org.tizen.voice-app|ondevice-voice|voice-client|voice-interaction|bixbycapsuleviewer|bixby-prov|ssoservice|bms-service|voice-instant-app|voiceassistant-music|mybixby|wakeup-engine-bixby|iacr|cis-api-service-app"
POOL=$(ps -ef | grep "launchpad-process-pool" | grep -v grep | tr -s " " | cut -d" " -f2 | head -1)
UIDIS="/home/owner/share/tmp/sdk_tools/selfroot-ui/modules/disabled/samsung-telemetry-off"
while true; do
    if [ -f "$MODULE_DIR/disabled" ] || [ -s "$UIDIS" ]; then sleep 30; continue; fi
    PIDS=$(ps -ef | grep -E "$PATTERNS" | grep -v grep | tr -s " " | cut -d" " -f2)
    for pid in $PIDS; do
        if [ "$pid" != "$$" ] && [ "$pid" != "1" ] && [ "$pid" != "$POOL" ]; then
            cmd=$(tr '\0' ' ' </proc/$pid/cmdline 2>/dev/null | cut -c1-60)
            kill -9 "$pid" >/dev/null 2>&1 && echo "$(date '+%T') watchdog killed $pid $cmd" >> "$EVIDENCE/module-samsung-telemetry-off-watchdog.log"
        fi
    done
    sleep 30
done
