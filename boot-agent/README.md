# boot-agent — untethered boot-time self-root

**BLUF:** An optional `dotnet-inhouse` app starts the archive-launcher root
chain on the TV at boot, without a host initiating it. The token-authenticated
headless bridge then provides desktop SDB access. This is source for a manual
installation against the TV's framework, not a general installer or a promise
of repeated-cycle reliability.

The boot agent, bridge and module design originated in
[levkropp's fork](https://github.com/levkropp/samsung-tv-root-untethered).
[kninetimmy's fork](https://github.com/kninetimmy/samsung-tv-root-untethered)
adds runtime targeting, integration fixes and the QN90B/U8000 results below.

The original fork reports QN55Q60BAFXZC / `T-NKLBAKUC-REL-202602250226`
(Tizen 6.5.0, kernel 5.4.77 armv7l); see **Inherited Q60B proof** below.

The development fork also verified one automatic-root boot on QN55QN90BAFXZA /
`T-PTMAKUC-REL-202602250225` with manager v5.13 and .NET 3.1.3. Remote activation
and kernel reboot required no TV interaction after initial setup. Fresh full
UID/GID and boot-ID proof was retrieved twice as SDK before any post-boot host
root. Its diagnostic bridge works; the headless bridge is still blocked by a
deployed CRLF shell script. See the [QN90B result and method](../docs/research-notes/QN90B_BOOT_ROOT.md)
for the tested boundary; the inherited proof below is a separate device result.

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
`26103`. The supplied bridge module uses this default; the manager's optional
`bridge-port.conf` does not reconfigure that service. Connection attempts
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
dotnet build boot-agent/bridge-relay/bridge-relay.csproj -c Release
```

The default target is .NET Core 3.1 for the earlier Tizen 6.5 TVs. Match the
target to the actual TV runtime. The U8000's Tizen 9 framework builds with:

```console
python3 boot-agent/staging/build.py --output boot-agent/staging/out
TV_FRAMEWORK_DIR=/path/to/tv/framework \
  dotnet build boot-agent/boot-agent.csproj -c Release -p:TvTargetFramework=net6.0
dotnet build boot-agent/bridge-relay/bridge-relay.csproj \
  -c Release -p:TvTargetFramework=net6.0
```

Use the generated .NET 6 runtime configurations for the manager and relay,
and the shared .NET 6 archive payload and runtime configuration. Keep the TV
framework assemblies, signing private keys, bridge token, backups and live
evidence local; they are not release source. The staging builder pins its key
inside the selected output directory and restricts private key files to mode
`0600` on POSIX hosts.

CI builds the headless relay for both targets and checks missing, short and
wrong tokens plus authenticated traffic in both directions using loopback.
The same host-only check can run after a .NET 6 relay build:

```console
python tools/verify_bridge_relay.py boot-agent/bridge-relay/bin/Release/net6.0/TvRootBridgeRelay.dll
```

The manager's Tizen NUI dependencies are not redistributable, so its build
requires local TV framework assemblies and is not part of public CI.

## Deploy (one time)

Keep every deployed shell script LF-only. The root `.gitattributes` enforces
this for Windows checkouts too; `core.autocrlf=true` must not turn module
scripts into CRLF. On the QN90B, a CRLF `bridge-service/boot.sh` failed Bash
parsing with `unexpected end of file` and never created the headless service.

An existing checkout or TV copy may still contain CRLF. Preserve local edits
before refreshing the host copy, and run `python -m pytest tests/test_shell_scripts.py`
before staging it. Back up the installed script and its metadata, then replace
only the affected module script with the checked LF bytes, retaining its
ownership, mode and SMACK labels. Verify the deployed hash and parse the actual
bytes without executing them: `cat /path/to/boot.sh | bash -n`. A module/service
start is a separate live operation; changing the source does not repair an
installed TV copy or establish bridge availability.

The agent squats a real preinstalled service app, `com.samsung.tv.ghservice`
(Gaming Hub service) — back it up first, and see **Remaining work** for the clean
dedicated-appid design.

```
# over sdb, from a root shell (archive-root route):
APP=/opt/usr/apps/com.samsung.tv.ghservice
cp -a $APP /path/to/backup/

# stage the chain artifacts into the app's res dir (root-created files):
# CHAIN_SOURCE is the directory where these checked host-built files were uploaded.
CHAIN_SOURCE=/path/to/staged-chain
mkdir -p $APP/res/selfroot
for name in SamsungTvArchiveRoot.dll SamsungTvArchiveRoot.runtimeconfig.json \
    public.pem passwd archive-root-00b0000000000001.tar.gz \
    archive-root-00b0000000000001.tar.gz.signature; do
    cp "$CHAIN_SOURCE/$name" "$APP/res/selfroot/$name" || exit 1
done

# the agent IL itself:
MANAGER_SOURCE=/path/to/staged-manager
cp "$MANAGER_SOURCE/com.samsung.tv.ghservice.dll" "$APP/bin/" || exit 1
cp "$MANAGER_SOURCE/com.samsung.tv.ghservice.runtimeconfig.json" "$APP/bin/" || exit 1

# boot trigger — DB row and manifest attribute:
sqlite3 /opt/dbspace/.pkgmgr_parser.db \
  "UPDATE package_app_info SET app_onboot='true', app_nodisplay='false', \
   app_component='uiapp' WHERE app_id='com.samsung.tv.ghservice';"
sed -i 's/<service-application/<ui-application/; s|</service-application>|</ui-application>|' \
  $APP/tizen-manifest.xml   # keep on-boot="true", type="dotnet-inhouse"

# On the host, while the TV still accepts this desktop as Developer Mode host:
umask 077
BRIDGE_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
printf '%s\n' "$BRIDGE_TOKEN" > /tmp/tvroot-bridge.conf
SDB="$HOME/tizen-studio/tools/sdb"
"$SDB" push /tmp/tvroot-bridge.conf /home/owner/share/tmp/sdk_tools/bridge.conf

# In the TV root shell, install the staged token:
mkdir -p /opt/usr/share/selfroot
chmod 755 /opt/usr/share/selfroot
chsmack -a 'User::App::Shared' /opt/usr/share/selfroot
cp /home/owner/share/tmp/sdk_tools/bridge.conf /opt/usr/share/selfroot/bridge.conf
chmod 644 /opt/usr/share/selfroot/bridge.conf
chsmack -a _ /opt/usr/share/selfroot/bridge.conf

# Back on the host, keep the token in a private password manager or environment.
printf 'Save this token on the manager: %s\n' "$BRIDGE_TOKEN"
```

Inspect the original manifest first. On the U8000 its service has
`on-boot="false"` and `nodisplay="true"`; explicitly change those attributes to
`on-boot="true"` and `nodisplay="false"` when converting it to a UI app. Preserve
the original file ownership, modes and SMACK labels, and change only the three
startup columns shown above. Back up the complete original application with
metadata and use SQLite's online backup for the package database before any
replacement. Keep a verified host copy and a stock restore script as well.
Preserve the existing SDB `on-demand` upload directory's ownership and shared
SMACK label. Relabeling it to `_` blocked later SDB uploads during the U8000
installation, even though TCP/SDB connectivity remained healthy.

The bridge is a separate deployment. Stage `modules/bridge-service/boot.sh`
and `module.json` together with the matching-runtime `TvRootBridgeRelay.dll`
and its generated `TvRootBridgeRelay.runtimeconfig.json` under
`/opt/usr/share/selfroot/modules/bridge-service/`. Preserve the intended file
ownership/modes/SMACK labels and check every deployed hash. The agent's signed
launch archive discovers modules there. This contribution includes only the
bridge module; telemetry/debloat/CEC modules are not part of this installation.

Before starting the manager or the first localhost boot, prepare its persistent
evidence directory as root. The manager runs as UID 5001, but its injected
launcher runs as SDK UID 901. If the diagnostic bridge creates this directory
first, it is owned by 5001 with mode `0755`; SDK cannot open `outer.log`, so the
root-launch block never runs. The shared directory must belong to SDK so the
launcher's existing permission and SMACK setup can also succeed.

Inspect an existing directory before changing it; preserve its logs and refuse
symlinks or an unexpected canonical path. Then prepare only this directory:

```sh
EVIDENCE=/home/owner/share/tmp/sdk_tools/selfroot-evidence
(
  test "$(readlink -f /home/owner/share/tmp/sdk_tools)" = /opt/usr/home/owner/share/tmp/sdk_tools &&
    test ! -L "$EVIDENCE" && mkdir -p "$EVIDENCE" && cd -P "$EVIDENCE" &&
    test "$(readlink -f .)" = /opt/usr/home/owner/share/tmp/sdk_tools/selfroot-evidence &&
    chown 901:901 . && chmod 777 . && chsmack -a 'User::App::Shared' .
) || exit 1
```

Before reboot, verify mode `777`, UID/GID `901:901`, and the shared SMACK label.
Through the SDK connection, exclusively create a temporary file there, read it
back, and remove only that file. A diagnostic bridge connection alone does not
verify that the boot launcher can write its evidence.

On the U8000, also pre-create the fixed SDK staging files as root so SDK copies
retain labels readable by the capped runtime. Run this after populating
`$APP/res/selfroot` and before the first localhost reboot:

```sh
ROOT_PKG=archive-root-00b0000000000001
ROOT_STAGE=/home/owner/share/tmp/sdk_tools/$ROOT_PKG
mkdir -p "$ROOT_STAGE"
chmod 777 "$ROOT_STAGE"
chsmack -a 'User::App::Shared' "$ROOT_STAGE"
for name in SamsungTvArchiveRoot.dll SamsungTvArchiveRoot.runtimeconfig.json public.pem passwd; do
  cp "$APP/res/selfroot/$name" "$ROOT_STAGE/$name"
  chown 901:901 "$ROOT_STAGE/$name"
  chmod 666 "$ROOT_STAGE/$name"
  chsmack -a 'User::App::Shared' "$ROOT_STAGE/$name"
done
touch "$ROOT_STAGE/launcher.log"
chown 901:901 "$ROOT_STAGE/launcher.log"
chmod 666 "$ROOT_STAGE/launcher.log"
chsmack -a 'User::App::Shared' "$ROOT_STAGE/launcher.log"
```

Verify SDK-side loading with `dotnet <staged-assembly> --help`: the expected
usage response establishes payload visibility without running the root chain.

Then set **Developer Mode Host PC IP to `127.0.0.1`** (Apps → Settings →
`12345`) and fully reboot. Check fresh identity proof and the bridge service
separately. Port `26103` requires a successful module start; a green manager
alone does not establish headless access.

### Connect the existing desktop CLI through the bridge

The CLI starts a loopback proxy that prepends the bridge token, so Tizen Studio's
`sdb` executable remains unchanged. Set `TVROOT_BRIDGE_TOKEN` to the token
recorded during installation:

```
TVROOT_BRIDGE_TOKEN=<32-character-token> \
  python -m samsung_tv_root archive-root root <tv-ip> --command 'id'
```

Use `--bridge-port 26104` for the manager-lifetime diagnostic relay instead.
The TV callback still connects directly to the desktop over the LAN, so allow
the selected callback port through the desktop firewall as usual.
Bridge connections clear existing loopback device entries in the host SDB
server because its single-loopback slot otherwise retains dead proxies. This
can disconnect another `127.0.0.1:*` SDB session using that server.

## Operating model

The v5.13 manager also provides a token-authenticated SDK diagnostic relay on
port `26104` while its window/process is running (`26105` if the main bridge
is configured on `26104`). It uses the same bridge token. Pass
`--bridge-port 26104` to inspect a failed startup through it. The diagnostic
listener is independent of root success and must not be treated as root proof.
The root-started headless bridge still uses port `26103` by default and remains
independent of the manager's lifetime. Shared evidence-directory labels let
the app read the outer/payload logs and append its diagnostic log on Tizen 9.

| Developer Mode Host PC IP **at boot** | Result |
| --- | --- |
| `127.0.0.1` | agent boots → self-roots → green status screen, evidence written |
| the host PC's address | agent boots → chain fails quietly → TV behaves stock, host has sdb access |

The developer-host setting must take effect through a real reboot. The Dev Mode
menu is the installation procedure here. The QN90B report also records a remote
research method using a guarded localhost write and detached kernel-reboot
helper, with separate readiness/readback acknowledgements. Those experimental
power helpers and private controllers are not included in this contribution.
See the [QN90B report](../docs/research-notes/QN90B_BOOT_ROOT.md) for its limits.
The agent runs its chain once at boot; there is no
steady-state polling.

### Verify a fresh reboot

Record `/proc/sys/kernel/random/boot_id` before rebooting. After reboot, first
connect through the authenticated bridge and read the new boot ID and
`selfroot-evidence/selfroot-proof.txt` as the SDK user. Do this **before** running
another host-initiated root command.

On the QN90B, use the manager's diagnostic SDK bridge on `26104` until its
headless bridge is repaired. A connection to either port alone is not proof:
verify the new boot and complete root identity from the evidence itself.

New staging archives put `BOOT_ID=` in the root proof alongside the complete
UID/GID status fields. Check the collected proof with:

```console
python tools/verify_boot_proof.py /path/to/selfroot-proof.txt \
  --previous-boot-id "$BOOT_ID_BEFORE" --current-boot-id "$BOOT_ID_AFTER"
```

The verifier rejects an unchanged boot ID, a proof from another boot, a missing
identity field, or any nonzero real/effective/saved/filesystem UID or GID.
File timestamps alone do not establish a fresh boot-root result.

If startup or bridge access fails, restore Host PC IP to the controller's LAN
address and fully reboot to recover direct SDB. Use the archive-root route to
run the prepared stock restore script through stdin (`cat rollback.sh | bash`),
then verify the original app hashes and startup fields. A prepared rollback is
not the same as a live-tested rollback.

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

## Inherited Q60B proof

The original fork reports this historical boot with devIP `127.0.0.1` and no
host connected. It predates the complete boot-ID/UID/GID verifier above and is
not the newer QN90B or U8000 evidence:

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
entirely, goes green, and checks the bridge (reopen fast-path). A full
chain only runs at boot. Closing the manager stops its process and with it
its window. The headless relay is owned by `tvroot-bridge.service`, independently
of the manager process; closing the manager does not own its service lifecycle.

The original fork recommends a headless boot agent for daily use because the
platform can surface the Gaming Hub window during playback. This agent stops
the manager's UI timer and module polling while backgrounded and makes remote
key logging opt-in with `/opt/usr/share/selfroot/key-debug` (read at startup).
The original fork describes changing the app to `svcapp` with
`app_component='svcapp'` and `app_nodisplay='true'`; that migration is separate
from the development fork's verified U8000 UI-app installation and remains unverified on
the QN90B. Verify the service entry point and recovery before changing the
manifest or package database.

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

Installation changes the stock app, its manifest and three startup database
fields. Preserve their original bytes and metadata plus a verified recovery
copy before making changes. Setting Developer Mode to localhost removes direct
desktop SDB access; bridge failure can require physical access to recover.
An OTA update can replace the repurposed app. One successful boot is not proof
of repeatability, native HDMI/gaming behavior, standby/wake or actual stock
restoration. The bridge's bearer token is cleartext on the LAN, and UID 0 still
retains SMACK restrictions.
