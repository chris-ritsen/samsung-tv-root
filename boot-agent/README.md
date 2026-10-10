# boot-agent — untethered boot-time self-root

A `dotnet-inhouse` app that Tizen boots for us, which re-acquires root **on the
TV, at every boot, with no host computer involved anywhere in the chain**. The
event-driven host controller in this repo stops being load-bearing on models
where this works: root comes back by itself after every power cycle, and the
controller becomes a convenience (remote access, events) rather than a
requirement.

Proven working on QN55Q60BAFXZC / `T-NKLBAKUC-REL-202602250226` (Tizen 6.5.0,
kernel 5.4.77 armv7l) — see **Proof** below.

## The chain

```
boot
  -> app-boot-manager -> aul -> our IL        (uid 5001, label User::Pkg::,
                                                empty CapEff, full CapBnd,
                                                NoNewPrivs: 0)
  -> TCP 127.0.0.1:26101 -> sdbd               (adb framing; verbatim CNXN
                                                replay + OPEN shell service)
  -> SVE-2025-50109 appinstall injection      (runs as uid 901(sdk),
                                                label System)
  -> cat <staging>/selfroot-launch.sh | bash  (UEP-safe: stdin, not a file)
  -> /usr/bin/dotnet                           (cap_setgid,cap_sys_admin+ei)
       SamsungTvArchiveRoot.dll <pkg> <staging> <on-demand>
  -> unshare(CLONE_NEWNS) + bind passwd/public.pem views
  -> sdbd-tarlauncher --package_name <pkg> -xzf <signed tar.gz>
       --to-command=/bin/sh                   (cap_setgid,cap_setuid+eip)
  -> uid 0 root shell
```

Everything from `boot` down runs on the TV. The host is only needed to install
the agent once.

After a fresh root proof, the boot chain starts an authenticated SDB TCP
bridge as a supervised headless service (`tvroot-bridge.service`, running
`TvRootBridgeRelay.dll` under the system dotnet — no window, no app
lifecycle, so closing the manager or switching inputs can no longer kill
management access). It reads a 32-character lowercase hex token from
`/opt/usr/share/selfroot/bridge.conf`, requires those exact 32 bytes at the
start of each connection, then relays to `127.0.0.1:26101`. The default port is
`26103`; an optional `/opt/usr/share/selfroot/bridge-port.conf` selects another
port from `1024` through `65535`. Connection attempts
are recorded in
`/home/owner/share/tmp/sdk_tools/selfroot-evidence/bridge.log`.
The manager keeps only a port probe for its status page. (Before v5.12 the
relay lived inside the manager process and died with it.)

The bridge token is sent in cleartext on the local network. Use a random token,
keep it private, and use the bridge only on a trusted LAN.

## The three pieces

1. **The boot trigger** — `package_app_info.app_onboot` in
   `/opt/dbspace/.pkgmgr_parser.db` (plain SQLite on rw `/opt`) plus the
   matching `on-boot="true"` manifest attribute. `app-boot-manager.service`
   launches the app through `aul` into the launchpad .NET pool at every boot.
   Both `svcapp` and `uiapp` components boot this way; the agent here is a
   `uiapp` so it can show a status window (banner, version stamp with its own
   dll's SHA256, progress bar, log lines) — `svcapp` works identically and
   shows nothing.

2. **The sdb-localhost client** — ~80 lines of C# in `Program.cs`. Raw TCP to
   `127.0.0.1:26101`, replay of the captured desktop-CLI `CNXN` frame, the
   `capability:` handshake, then `OPEN` carrying the repo's own
   `build_shell_injection`-shape `appinstall` injection (195 chars, under the
   510-byte cap). The injected command stages and runs the launch script via
   `cat <script> | bash` — **not** `bash <script>` (see gotcha 3).

3. **The payload** — the repo's existing `SamsungTvArchiveRoot` route, in its
   explicit `[staging on-demand]` argument form, so the agent can place staged
   artifacts in paths the injected context can write and the payload can
   read. Private mount namespace, bind views over `/etc/passwd` and
   `sdbd/public.pem`, then the signed-archive tarlauncher with `cap_setuid` →
   uid 0.

## Build

From the TV (any root shell, e.g. the archive-root route), pull the framework
assemblies the agent compiles against — they are not redistributable:

```
tar czf - -C /usr/share dotnet.tizen > /path/for/dotnet-tizen.tgz
```

Then on the host:

```
python3 boot-agent/staging/build.py          # keypair + signed launch.sh tarball
TV_FRAMEWORK_DIR=/path/to/dotnet.tizen/framework \
  dotnet build boot-agent/boot-agent.csproj -c Release
```

## Deploy (one time)

The agent squats a real preinstalled service app, `com.samsung.tv.ghservice`
(Gaming Hub service) — back it up first, and see **TODO** for the clean
dedicated-appid design.

```
# over sdb, from a root shell (archive-root route):
APP=/opt/usr/apps/com.samsung.tv.ghservice
cp -a $APP /path/to/backup/

# stage the chain artifacts into the app's res dir (root-created files):
mkdir -p $APP/res/selfroot
cp out/{SamsungTvArchiveRoot.dll,SamsungTvArchiveRoot.runtimeconfig.json, \
        public.pem,passwd,<PKG>.tar.gz,<PKG>.tar.gz.signature} $APP/res/selfroot/

# the agent IL itself:
cp <build>/com.samsung.tv.ghservice.dll $APP/bin/
cp <build>/com.samsung.tv.ghservice.runtimeconfig.json $APP/bin/

# boot trigger — DB row and manifest attribute:
sqlite3 /opt/dbspace/.pkgmgr_parser.db \
  "UPDATE package_app_info SET app_onboot='true', app_nodisplay='false', \
   app_component='uiapp' WHERE app_id='com.samsung.tv.ghservice';"
sed -i 's/<service-application/<ui-application/; s|</service-application>|</ui-application>|' \
  $APP/tizen-manifest.xml   # keep on-boot="true", type="dotnet-inhouse"

# On the host, while the TV still accepts this desktop as Developer Mode host:
BRIDGE_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
printf '%s\n' "$BRIDGE_TOKEN" > /tmp/tvroot-bridge.conf
SDB="$HOME/tizen-studio/tools/sdb"
"$SDB" push /tmp/tvroot-bridge.conf /home/owner/share/tmp/sdk_tools/bridge.conf

# In the TV root shell, install the staged token:
mkdir -p /opt/usr/share/selfroot
chmod 755 /opt/usr/share/selfroot
chsmack -a _ /opt/usr/share/selfroot
cp /home/owner/share/tmp/sdk_tools/bridge.conf /opt/usr/share/selfroot/bridge.conf
chmod 644 /opt/usr/share/selfroot/bridge.conf
chsmack -a _ /opt/usr/share/selfroot/bridge.conf

# Optional: create this file to use a port other than 26103.
# printf '26104\n' > /opt/usr/share/selfroot/bridge-port.conf
# chmod 644 /opt/usr/share/selfroot/bridge-port.conf
# chsmack -a _ /opt/usr/share/selfroot/bridge-port.conf

# Back on the host, keep the token in a private password manager or environment.
printf 'Save this token on the manager: %s\n' "$BRIDGE_TOKEN"
```

Then set **Developer Mode Host PC IP to `127.0.0.1`** (Apps → Settings →
`12345`) and reboot. The agent boots, self-roots, and shows its green status
screen. Once rooted, it listens on port `26103`.

### Connect the existing desktop CLI through the bridge

The CLI starts a loopback proxy that prepends the bridge token, so Tizen Studio's
`sdb` executable remains unchanged. Set `TVROOT_BRIDGE_TOKEN` to the token
recorded during installation:

```
TVROOT_BRIDGE_TOKEN=<32-character-token> \
  python -m samsung_tv_root archive-root root <tv-ip> --command 'id'
```

Use `--bridge-port` if the TV has a `bridge-port.conf` with a different port.
The TV callback still connects directly to the desktop over the LAN, so allow
the selected callback port through the desktop firewall as usual.

## Operating model

| Developer Mode Host PC IP **at boot** | Result |
| --- | --- |
| `127.0.0.1` | agent boots → self-roots → green status screen, evidence written |
| the host PC's address | agent boots → chain fails quietly → TV behaves stock, host has sdb access |

The flip **in the Dev Mode menu + a reboot** is the only toggle. The agent
runs its chain once at boot; there is no steady-state polling.

## Platform gotchas (each cost a debug cycle)

1. **sdbd applies the developer-mode host-IP check to TV-local clients.** A
   raw socket from the TV itself is TCP-accepted but the `CNXN` gets no reply
   while devIP points at the host. Setting Host PC IP to `127.0.0.1` — the
   same trick TizenBrew documents for its installer — makes the TV the
   authorized host.
2. **sdbd caches the host IP at startup; a live flip does nothing.** Flipping
   devIP while the TV is up never unblocked the running agent; the flip only
   takes effect after a reboot. A boot-time chain is therefore the right
   shape, not a workaround.
3. **UEP blocks `bash <script-file>` from disk** —
   `[uep][bash] the file is NOT signed!!` — including in the root context.
   Feeding the script via stdin (`cat script | bash`) passes. The injection
   wraps its launch script accordingly.
4. **SELP is path-based, not content-based.** A byte-identical
   `setcap`-carrying copy of `/usr/bin/dotnet` (same SHA256, floor SMACK
   label) refuses to exec with `Operation not permitted` from any path other
   than Samsung's own. A "no-sdbd" escalation route via a self-staged dotnet
   copy is dead on this firmware — the sdb-localhost route is the way.

Related SMACK facts: pooled apps run as `User::Pkg::<appid>` with empty
CapEff but full CapBnd and `NoNewPrivs: 0`; the loaded policy in
`smackfs/load` grants `x` on `System::Tools` (the dotnet label) to `System`,
`User`, `_`, `User::Shell`, `System::TEF`, `System::Privileged` — **not** to
`User::Pkg::*`, and `relabel-self` is empty. So a boot app cannot exec the
capped dotnet directly (EACCES, confirmed) — another reason the sdbd route
(whose injected commands run as label `System`) is the correct untethered
path.

## Proof

From a boot run with devIP `127.0.0.1` and no host computer connected to
anything (persistent evidence dir, written by the injection context):

```
$ cat outer.log
Fri Oct  9 11:49:30 EDT 2026
uid=901(sdk) ... context="System"
Systempayload-exit=0

$ cat payload.log
exit=0

$ cat selfroot-proof.txt
SELFROOT-PROOF uid=0 gid=0
Uid:    0    0    0    0
CapEff: 0000003fffffffff
---PASSWD-VIEW---
owner:x:0:0:owner:/home/owner:/bin/sh     <- our bind-mounted passwd view
```

## On-TV manager UI (M4)

The v5.4 build is a four-page manager: `STATUS`, `MODULES`, `LOGS`, `PAIRING`.
Left/Right switch pages (one press = one page — key releases are ignored, so
a single press can never skip two pages); Up/Down select a module or scroll
logs; OK toggles; Back/Exit closes. The status page reports root proof time,
bridge state/port, token hint, safe-mode state, and module counts; Up on the
status page toggles safe mode for the next boot (marker in the app-writable
`selfroot-ui/` dir, honored like the flag file; undo by toggling again or
`rm` over the bridge). The pairing page shows a plain-text `tvroot://` URI;
the bearer token is only shown on that page. A QR renderer is not included
in this pass (generate the QR on the manager host from the pairing URI and
push the PNG later — `ImageView` is available).

Reopening the manager from the launcher (`TVRoot` tile — the squatted
`com.samsung.tv.ghservice` manifest label was renamed from GHService) is
instant: if this boot already has fresh proof the agent skips the injection
entirely, goes green, and restarts the bridge (reopen fast-path). A full
chain only runs at boot. Closing the manager stops its process and with it
the bridge; reopening restores both in seconds.

Module toggles apply on the next boot because the root runner snapshots
overrides before executing any module. The UI writes overrides under
`/home/owner/share/tmp/sdk_tools/selfroot-ui/modules/{enabled,disabled}/`;
the root runner checks those overrides along with each module's `disabled`
flag under `/opt/usr/share/selfroot/modules/<id>/`. An explicit UI enable
override takes precedence over a module's default disabled flag.

Platform note (cost a debug cycle): the agent (SMACK `User::Pkg::*`) can
append to `User::App::Shared`-labeled files in the evidence dir but can
neither create files nor write floor-labeled (`_`) ones there. `launch.sh`
therefore pre-creates `agent.log` (touch + chmod 666 + chsmack to
`User::App::Shared`) at every boot; the LOGS page tails it (persistent)
plus the in-memory session events. `module.json` files are staged alongside
`boot.sh` so the UI shows real module names/versions.

## Remaining work

- **Dedicated appid.** A fresh `package_app_info` row + manifest dir +
  `on-boot=true` instead of squatting `com.samsung.tv.ghservice`: no
  collateral damage, clean uninstall. The SQL INSERT remains untested.
- QR pairing and the desktop/Android wizard remain part of the companion-app
  milestone.

## Safety

Nothing here touches ro partitions, the boot chain, or the firmware image.
Worst case is a dead app plus a stock restore from the backup. Dev mode
survives reboots, so the sdb path remains a recovery lifeline. An OTA update
can reinstall the squatted app (resetting the agent) — auto-update off, and
treat the on-boot flip as version-pinned.
