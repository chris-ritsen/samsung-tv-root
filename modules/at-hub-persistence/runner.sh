#!/bin/sh
# tvroot boot runner (module at-hub-persistence). Invoked as root by the
# /opt/etc/parseinfo.sh gawk hook at every boot (AT-HUB.service), and safe
# to run manually. The hook already did the vendor target_version write.
# UEP: run via stdin (cat runner.sh | bash), never as a script-file argument.
#
# This replaces the module-runner role of the old ghservice boot agent
# chain (build.py LAUNCH_SH): proof write, SMACK labels on the evidence
# dir, UI override snapshot, then every enabled module's boot.sh.
MOD=/opt/usr/share/selfroot/modules/at-hub-persistence
EV=${EVIDENCE:-/home/owner/share/tmp/sdk_tools/selfroot-evidence}
UI_MODS=/home/owner/share/tmp/sdk_tools/selfroot-ui/modules
UI_STATE=/tmp/selfroot-module-state
BOOT_TS=$(date '+%Y-%m-%d %H:%M:%S')

# self-disable: the module's own disabled flag skips tvroot management for
# this boot (the hook's vendor write is unconditional and unaffected).
if [ -f "$MOD/disabled" ]; then
    mkdir -p "$EV" 2>/dev/null
    echo "$BOOT_TS at-hub-persistence disabled - runner skipped" >> "$EV/modules.log" 2>/dev/null
    exit 0
fi

# proof + evidence dir (AT-HUB context is already uid 0 - no chain needed)
mkdir -p "$EV" 2>/dev/null
chmod 0777 "$EV" 2>/dev/null
chsmack -a _ "$EV" 2>/dev/null
{
    echo "SELFROOT-PROOF uid=$(id -u) gid=$(id -g) via=at-hub-$(cat /proc/self/attr/current 2>/dev/null | tr -d '\n')"
    echo "$BOOT_TS boot runner start (uptime $(cut -d. -f1 /proc/uptime 2>/dev/null)s)"
} > /tmp/selfroot-proof.txt
chsmack -a _ /tmp/selfroot-proof.txt 2>/dev/null
cp /tmp/selfroot-proof.txt "$EV/selfroot-proof.txt" 2>/dev/null
chmod 666 "$EV/selfroot-proof.txt" 2>/dev/null
chsmack -a _ "$EV/selfroot-proof.txt" 2>/dev/null
# manager-app compat: agent.log keeps the User::App::Shared label (the
# manager app can append to it but cannot create or relabel files).
touch "$EV/agent.log" 2>/dev/null
chmod 666 "$EV/agent.log" 2>/dev/null
chsmack -a 'User::App::Shared' "$EV/agent.log" 2>/dev/null
echo "$BOOT_TS at-hub runner: uid=$(id -u) ctx=$(cat /proc/self/attr/current 2>/dev/null | tr -d '\n')" >> "$EV/at-hub.log"

# UI override snapshot (same semantics as the old launch.sh runner):
# non-empty markers only; explicit enable beats a module's disabled flag.
mkdir -p "$UI_MODS/enabled" "$UI_MODS/disabled" 2>/dev/null
chmod 0777 "$UI_MODS" "$UI_MODS/enabled" "$UI_MODS/disabled" 2>/dev/null
chsmack -r -a _ "$UI_MODS" 2>/dev/null
rm -rf "$UI_STATE"
mkdir -p "$UI_STATE/enabled" "$UI_STATE/disabled"
for state in enabled disabled; do
    for marker in "$UI_MODS/$state/"*; do
        [ -s "$marker" ] || continue
        touch "$UI_STATE/$state/$(basename "$marker")"
    done
done

# Boot-settle gate: AT-HUB fires at starter.target while activation jobs
# are still queued; `systemctl stop` on a mid-activation unit BLOCKS until
# that job drains (obs live: module loop stretched to ~2.5 min on 1720.7).
# Proof/labels/bridge above are safe early; unit-touching modules wait for
# the systemd job queue to empty (or a 150s cap) first.
i=0
while [ "$i" -lt 30 ] && [ "$(systemctl list-jobs --no-pager 2>/dev/null | wc -l)" -gt 1 ]; do
    sleep 5
    i=$((i + 1))
done
if [ "$i" -gt 0 ]; then
    echo "$(date "+%Y-%m-%d %H:%M:%S") runner: waited $((i * 5))s for boot jobs to drain" >> "$EV/at-hub.log"
fi

# module loop. bridge-service/boot.sh rewrites the (tmpfs) bridge unit and
# restarts the relay; telemetry modules mask their units - all idempotent.
# Skip this module: boot.sh here is an installer, not a per-boot action.
MODS=/opt/usr/share/selfroot/modules
if [ -d "$MODS" ]; then
    for m in "$MODS"/*/; do
        [ -d "$m" ] || continue
        mid=$(basename "$m")
        [ "$mid" = "at-hub-persistence" ] && continue
        if [ -f "$UI_STATE/disabled/$mid" ] || { [ -f "$m/disabled" ] && [ ! -f "$UI_STATE/enabled/$mid" ]; }; then
            echo "$(date) skip $mid (disabled)" >> "$EV/modules.log"
            continue
        fi
        [ -f "$m/boot.sh" ] || continue
        echo "$(date) run $mid (at-hub)" >> "$EV/modules.log"
        ( cd "$m" && cat "$m/boot.sh" | MODULE_DIR="$m" EVIDENCE="$EV" bash ) > "$EV/module-$mid.log" 2>&1
        echo "$(date) $mid exit=$?" >> "$EV/modules.log"
    done
fi
sync
exit 0
