#!/bin/sh
# tvroot TVPlus-button hijack loop: tvplus stays enabled (no system toast),
# and on any tvplus/deeplinker sighting (button presses only, no autostart)
# kills them and foregrounds the manager. Run supervised
# (tvroot-hijack.service runs this via cat|bash). Dormant while disabled.
# Env: MODULE_DIR, EVIDENCE (set by the unit file).
POOL=$(ps -ef | grep "launchpad-process-pool" | grep -v grep | tr -s " " | cut -d" " -f2 | head -1)
UIDIS="/home/owner/share/tmp/sdk_tools/selfroot-ui/modules/disabled/samsung-telemetry-off"
while true; do
    if [ -f "$MODULE_DIR/disabled" ] || [ -s "$UIDIS" ]; then sleep 30; continue; fi
    HIT=$(ps -ef | grep -iE "tvplus|deeplink|disney" | grep -v grep | tr -s " " | cut -d" " -f2)
    if [ -n "$HIT" ]; then
        for pid in $HIT; do
            if [ "$pid" != "$$" ] && [ "$pid" != "1" ] && [ "$pid" != "$POOL" ]; then
                kill -9 "$pid" 2>/dev/null
            fi
        done
        /usr/bin/app_launcher -f com.samsung.tv.ghservice -u 5001 entry_point cold_booting ICULoadDisable ICULoadDisable __NO_LOADING_LAUNCH enable >/dev/null 2>&1
        echo "$(date '+%T') tvplus hijack: killed [$HIT], manager foregrounded" >> "$EVIDENCE/module-samsung-telemetry-off-watchdog.log"
        sleep 5
    else
        sleep 2
    fi
done
