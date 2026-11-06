# at-hub-persistence

Boot-time root through the vendor `AT-HUB.service` hook, replacing the
`com.samsung.tv.ghservice` squat. Proven on QN55Q60BAFXZC /
T-NKLBAKUC-1720.7 (Tizen 6.5, armv7l), 2026-11-06.

## Why

The old untethered chain squatted the preinstalled `com.samsung.tv.ghservice`
app (uiapp, `on-boot=true`) to self-root at every boot. Two problems:

- the platform surfaces the squatted window whenever it expects Gaming Hub —
  the manager popped up over HDMI sources;
- squatting a preinstalled app means package-DB edits, manifest surgery and a
  messy uninstall.

`AT-HUB.service` is a vendor unit (`/usr/lib/systemd/system/`,
`starter.target.wants` symlink) with `ExecStart=/opt/etc/parseinfo.sh &` and no
`User=`, so it runs as root at every boot. `/opt/etc/parseinfo.sh` lives on the
persistent rw `/opt` vdfs — replaceable in place, no raw-block patching, and
it survives rootfs wipes/reinstalls (only a `/opt` reformat kills it).

## How it works

```
starter.target
 └─ AT-HUB.service (vendor unit, as root)
     └─ /opt/etc/parseinfo.sh            ← ours: #!/usr/bin/gawk -f (hook.awk)
         ├─ vendor __REPO__MODEL__ > /proc/target_version write (ported 1:1)
         └─ system("cat runner.sh | bash")  (UEP-safe stdin form)
             ├─ proof write + SMACK labels on the evidence dir
             ├─ boot-settle gate (waits for the systemd job queue to drain —
             │  `systemctl stop` on a mid-activation unit blocks otherwise)
             └─ module loop: every enabled module's boot.sh (bridge unit,
                telemetry masks, watchdog, …), same semantics as the old
                agent chain runner
```

UEP facts this relies on (live-verified on 1720.7):

- kernel UEP excludes `#!` scripts from its target types, so systemd can exec
  the hook directly;
- `/bin/bash` and `/bin/sh` refuse unsigned script *files* (the stock
  parseinfo.sh carries a `##UEP` signature trailer for exactly that reason —
  an unsigned `#!/bin/sh` replacement execs but exits 1 with no body run);
- `/usr/bin/gawk` is signed and not linked against `libkUEPUser.so`, so it
  loads the hook as plain data; `system()` shells out without script-file
  arguments;
- AT-HUB passes the vendor's trailing `&` through as argv; `exit` inside
  `BEGIN` stops gawk from ever opening it as a data file.

The hook runs with SMACK `System::Privileged` — a better label than the old
exploit chain's `User`.

## Install

From a root session (manager module loop, or `archive-root root --command`):

```sh
( cd "$M" && cat "$M/boot.sh" | MODULE_DIR="$M" EVIDENCE="$EV" bash )
```

`boot.sh` is idempotent: it backs up the stock file once to
`/opt/usr/share/selfroot/backups/parseinfo.sh.stock`, verifies the pinned
sha256 before overwriting, verifies the installed sha256 after, and rolls
back on mismatch. It refuses to touch a `/opt/etc/parseinfo.sh` that is
neither stock nor our hook unless `FORCE=1`.

Test without rebooting: `systemctl start AT-HUB.service` — the stock unit
execs the hook, then check `$EV/at-hub.log` and `$EV/modules.log`.

## Deploying files through the host CLI

The root agent's `QuoteArgument` doubles every backslash in `--command`
(`\n` arrives as `\\n`), so heredoc-pasted scripts do NOT transfer
byte-exact. Always deploy module payloads base64-encoded:

```sh
echo <base64> | base64 -d > "$M/<file>"     # no backslashes in base64
```

## Uninstall / rollback

```sh
cp /opt/usr/share/selfroot/backups/parseinfo.sh.stock /opt/etc/parseinfo.sh
```

…then reboot. Disabling the module (`touch $M/disabled`) keeps the vendor
write but skips the runner for that boot.

## Retiring the ghservice squat (post-verification)

Once the hook is proven at a cold boot, restore ghservice to stock so the
manager never runs again (this also kills the HDMI popup for good):

1. `update package_app_info set app_component='svcapp', app_onboot='false',
   app_nodisplay='true' where app_id='com.samsung.tv.ghservice'` in
   `/opt/dbspace/.pkgmgr_parser.db`;
2. kill the running manager pid (exact match, uid 5001 dotnet);
3. restore `bin/*.dll` and `bin/*.runtimeconfig.json` from their `.tvbk`
   siblings (sha256 must match the pre-squat tarball), restore the stock
   `tizen-manifest.xml` (owner 201:root, modes 755/755/644);
4. `rm -rf $APP/res/selfroot` (chain staging);
5. power-cycle. ghdaemon will still launch ghservice headlessly each boot
   (`UpdateSupportedApps` deeplink, nodisplay svcapp) — that is stock
   behavior and shows nothing.

## Files

- `hook.awk` — becomes `/opt/etc/parseinfo.sh`; gawk BEGIN block with the
  vendor write ported 1:1 plus the runner invocation
- `runner.sh` — proof, SMACK labels, UI override snapshot, boot-settle gate,
  module loop (skips this module)
- `boot.sh` — idempotent installer with backup/verify/rollback
- `module.json` — module metadata
- `parseinfo.sh.stock` — pristine vendor bytes (805, sha256 `c6369e7de…61d61`).
  NOT tracked in this repo (Samsung firmware content — repo policy); stage it
  from `~/tv-preserve/1720.7/parseinfo.sh.stock` when deploying.