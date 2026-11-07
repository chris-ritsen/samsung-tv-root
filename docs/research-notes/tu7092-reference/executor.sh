#!/bin/bash
# Content is passed to signed bash, not installed as a boot hook.
umask 077
cd "$VETRO_AGENT_RUNTIME" || exit 1
exec 8<>in.fifo
exec 9<>out.fifo
cpid= wpid=
cleanup() {
    if [ -n "$cpid" ]; then kill -9 -- "-$cpid" 2>/dev/null; fi
    if [ -n "$wpid" ]; then kill "$wpid" 2>/dev/null; fi
    rm -f stdout stderr timed
}
trap 'cleanup; exit 0' TERM INT HUP
trap cleanup EXIT
while IFS=$'\t' read -r seq tms b64 <&8; do
    case "$seq:$tms" in *[!0-9:]*|:*) exit 2;; esac
    [ "$tms" -ge 1 ] && [ "$tms" -le 120000 ] || exit 2
    cmd=$(printf '%s' "$b64" | base64 -d) || exit 2
    rm -f stdout stderr timed
    # Limit each output file to 1 MiB. Every command has its own process group.
    setsid /bin/bash -c 'ulimit -f 2048; eval "$1"' vetro-exec "$cmd" 8>&- 9>&- >stdout 2>stderr &
    cpid=$!
    ( exec 8>&- 9>&-; sleep $(( (tms + 999) / 1000 )); touch timed; kill -9 -- "-$cpid" 2>/dev/null ) &
    wpid=$!
    wait "$cpid" 2>/dev/null; code=$?
    kill "$wpid" 2>/dev/null; wait "$wpid" 2>/dev/null
    kill -9 -- "-$cpid" 2>/dev/null
    cpid= wpid=
    timedout=0; [ -f timed ] && timedout=1
    ob64=$(base64 stdout | tr -d '\n'); eb64=$(base64 stderr | tr -d '\n')
    printf '%s\t%s\t%s\t%s\t%s\n' "$seq" "$code" "$timedout" "$ob64" "$eb64" >&9
    rm -f stdout stderr timed
done
