#!/bin/bash
# One manual session only. Nothing registers this script for boot.
umask 077
cd "$VETRO_AGENT_RUNTIME" || exit 1
epid= npid=
cleanup() {
    trap - EXIT TERM INT HUP
    [ -z "$npid" ] || kill "$npid" 2>/dev/null
    [ -z "$epid" ] || kill -TERM -- "-$epid" 2>/dev/null
    [ -z "$epid" ] || wait "$epid" 2>/dev/null
    rm -f in.fifo out.fifo supervisor.pid agent.pid executor.pid
}
trap 'cleanup; exit 0' TERM INT HUP
trap cleanup EXIT
printf '%s\n' "$$" > supervisor.pid
mkfifo -m 600 in.fifo out.fifo || exit 1
setsid /bin/bash -c "$(cat executor.sh)" </dev/null &
epid=$!; printf '%s\n' "$epid" > executor.pid
# In node -e mode require.main is undefined, so invoke the exported entrypoint.
/usr/bin/node -e "$(cat agent-node4.js)"$'\nmodule.exports.run();' </dev/null &
npid=$!; printf '%s\n' "$npid" > agent.pid
wait "$npid"
