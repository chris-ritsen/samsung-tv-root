#!/bin/sh
# tvroot module: at-hub-persistence — installer/updater.
#
# Replaces /opt/etc/parseinfo.sh (executed as root by the vendor
# AT-HUB.service at every boot via starter.target.wants) with this
# module's gawk hook (hook.awk). The stock file is backed up before the
# first replacement and verified against the pinned stock sha256. The
# hook preserves the vendor __REPO__MODEL__ > /proc/target_version write
# and starts runner.sh (bridge + modules) as root at every boot.
#
# This moves boot-time root off the squatted com.samsung.tv.ghservice
# agent: once this is proven at a cold boot, ghservice can be restored to
# stock and Developer Mode is no longer part of the boot chain (the
# bridge and the host CLI still use it while it is available).
#
# UEP: this script must run via stdin (cat boot.sh | bash) from a root
# context (manager module loop or manual), never as a script-file arg.
# Idempotent: re-running with the hook already installed is a no-op.
#
# Uninstall: cp /opt/usr/share/selfroot/backups/parseinfo.sh.stock
# /opt/etc/parseinfo.sh (root), then reboot.
MODULE_DIR=${MODULE_DIR:-/opt/usr/share/selfroot/modules/at-hub-persistence}
EVIDENCE=${EVIDENCE:-/home/owner/share/tmp/sdk_tools/selfroot-evidence}
H=/opt/etc/parseinfo.sh
B=/opt/usr/share/selfroot/backups/parseinfo.sh.stock
HOOK_SHA=419d45be701ec9b61044372621d0be3ac892f21f7b139470f30415a2fb664c3c
STOCK_SHA=c6369e7dec69408e176daa252d436acf6f8e265f560504d8bd831c8023c71d61

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$EVIDENCE/module-at-hub-persistence.log" 2>/dev/null; }
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

mkdir -p "$EVIDENCE" /opt/usr/share/selfroot/backups 2>/dev/null

cur=$(sha "$H")
if [ -z "$cur" ]; then
    log "FATAL: cannot read $H"
    echo "at-hub-persistence: cannot read $H"
    exit 1
fi

if [ "$cur" = "$HOOK_SHA" ]; then
    log "hook already installed (sha match) - no-op"
    echo "at-hub-persistence: already installed"
    exit 0
fi

if [ "$cur" != "$STOCK_SHA" ]; then
    if [ "${FORCE:-0}" = "1" ]; then
        log "WARN: FORCE=1 over non-stock $H (sha $cur)"
    else
        log "REFUSED: $H is neither stock nor our hook (sha $cur); FORCE=1 to override"
        echo "at-hub-persistence: REFUSED - $H unexpected (sha $cur)."
        echo "  Inspect it first; FORCE=1 to override. Stock sha: $STOCK_SHA"
        exit 1
    fi
fi

# first-time backup of the stock bytes
if [ ! -f "$B" ]; then
    if ! cp "$H" "$B"; then
        log "FATAL: backup copy to $B failed"
        echo "at-hub-persistence: backup failed"
        exit 1
    fi
    chmod 666 "$B" 2>/dev/null
    log "stock parseinfo.sh backed up -> $B (sha $(sha "$B"))"
fi

# install the hook (stock file mode was 777 owner=uid0; keep both)
if ! cat "$MODULE_DIR/hook.awk" > "$H"; then
    log "FATAL: hook install failed (write to $H)"
    echo "at-hub-persistence: install failed"
    exit 1
fi
chmod 777 "$H" 2>/dev/null
chown 0:0 "$H" 2>/dev/null
sync
after=$(sha "$H")
if [ "$after" != "$HOOK_SHA" ]; then
    log "FATAL: post-install sha mismatch ($after != $HOOK_SHA), restoring stock"
    cat "$B" > "$H"
    echo "at-hub-persistence: post-install verify failed, rolled back"
    exit 1
fi
log "hook installed over $H (sha $after); AT-HUB runs it at every boot as root"
echo "at-hub-persistence: hook installed."
echo "  test: systemctl start AT-HUB.service   (then check $EVIDENCE/at-hub.log)"
echo "  rollback: cp $B $H"
exit 0
