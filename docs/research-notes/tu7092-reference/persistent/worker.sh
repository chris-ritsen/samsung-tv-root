#!/bin/bash
# Boot-owned supervisor. All execution files are root-owned verified copies.
set -u
umask 077
BASE=${VETRO_BOOT_BASE:-/opt/vetro-tu7092-root}
RUN=${VETRO_BOOT_RUN:-/run/vetro-tu7092-root}
ASSETS=${VETRO_BOOT_ASSETS:?verified assets required}
STAGE=${VETRO_BOOT_STAGE:-/home/owner/share/tmp/sdk_tools}
STOP=${VETRO_BOOT_STOP:-/opt/data/DeviceTracker/tizenpwn.stop}
ATTR=${VETRO_BOOT_ATTR:-/proc/self/attr/current}
CAPFILE=${VETRO_BOOT_CAPFILE:-/proc/self/status}
CONFIG_UID=${VETRO_BOOT_CONFIG_UID:-5001}
agent_pid=
last_state=
stopped() { [ -e "$STOP" ] || [ -e "$BASE/disabled" ]; }
status() {
    [ "$last_state" = "$1" ] && return
    last_state=$1
    { printf 'state=%s\nuid=%s\ngid=%s\n' "$1" "$(id -u)" "$(id -g)"
      printf 'context=%s\n' "$(cat "$ATTR")"
      sed -n '/^CapEff:/p' "$CAPFILE"
      printf 'boot_id='; cat /proc/sys/kernel/random/boot_id
    } > "$RUN/status.new"
    chmod 644 "$RUN/status.new"
    chsmack -a _ "$RUN/status.new" 2>/dev/null
    mv "$RUN/status.new" "$RUN/status.txt"
}
stop_agent() {
    if [ -n "$agent_pid" ]; then
        kill -TERM "$agent_pid" 2>/dev/null || :
        wait "$agent_pid" 2>/dev/null || :
        agent_pid=
    fi
}
cleanup() { trap - EXIT TERM INT HUP; stop_agent; status stopped; }
trap 'cleanup; exit 0' TERM INT HUP
trap cleanup EXIT
[ "$(id -u)" = 0 ] && [ "$(id -g)" = 0 ] || exit 1
# Change only this worker's label, never the global SMACK policy.
for ((attempt=0; attempt<60; attempt++)); do
    stopped && exit 0
    [ "$(cat "$ATTR")" = System::Privileged ] && break
    printf '%s' System::Privileged > "$ATTR" 2>/dev/null || :
    [ "$(cat "$ATTR")" = System::Privileged ] && break
    sleep 2
done
[ "$(cat "$ATTR")" = System::Privileged ] || { status context-failed; trap - EXIT; exit 1; }
[ "$(sed -n 's/^CapEff:[[:space:]]*//p' "$CAPFILE")" = 0000003fffffffff ] || { status capabilities-failed; trap - EXIT; exit 1; }

pick_config() {
    local file parent suffix m newest= newest_m=-1
    for file in "$STAGE"/vetro-external-*/agent.json; do
        [ -f "$file" ] && [ ! -L "$file" ] || continue
        parent=${file%/agent.json}
        [ ! -L "$parent" ] || continue
        suffix=${parent##*/vetro-external-}
        [[ "$suffix" =~ ^[a-f0-9]{24}$ ]] || continue
        [ "$(stat -c '%u %a' "$parent" 2>/dev/null)" = "$CONFIG_UID 700" ] || continue
        [ "$(stat -c '%u %a' "$file" 2>/dev/null)" = "$CONFIG_UID 600" ] || continue
        m=$(stat -c %Y "$file" 2>/dev/null) || continue
        if [ "$m" -gt "$newest_m" ]; then newest=$file; newest_m=$m; fi
    done
    printf '%s' "$newest"
}

while ! stopped; do
    config=$(pick_config)
    if [ -z "$config" ]; then status waiting-for-vetro; sleep 3; continue; fi
    session=$RUN/session
    mkdir -p -m 700 "$session" || exit 1
    for name in agent-node4.js executor.sh supervisor.sh; do
        cp "$ASSETS/$name" "$session/$name" || exit 1
        chmod 600 "$session/$name" || exit 1
    done
    # A previous supervisor has already exited and cleaned its children.
    rm -f "$session/in.fifo" "$session/out.fifo"
    VETRO_AGENT_RUNTIME=$session VETRO_AGENT_CONFIG=$config VETRO_CONFIG_UID=$CONFIG_UID \
        setsid /bin/bash -c "$(cat "$session/supervisor.sh")" </dev/null >"$session/supervisor.log" 2>&1 &
    agent_pid=$!
    status agent-running
    while kill -0 "$agent_pid" 2>/dev/null; do
        stopped && break
        # A service restart can replace the private configuration directory.
        [ "$(pick_config)" = "$config" ] || break
        sleep 1
    done
    stop_agent
    stopped && break
    status reconnecting
    sleep 3
done
