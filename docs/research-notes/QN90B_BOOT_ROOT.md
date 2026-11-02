# QN90B automatic boot-root report

**BLUF:** The development fork verified one automatic TV-side `archive-root`
boot on `QN55QN90BAFXZA`, build `T-PTMAKUC-REL-202602250225`. A remote Linux
reboot returned fresh complete zero UID/GID proof, retrieved twice as SDK
before any post-boot host root. The installed headless bridge remains blocked
by a CRLF script; successful boot-root and headless access are separate results.

This report comes from [kninetimmy's development fork](https://github.com/kninetimmy/samsung-tv-root-untethered),
building on the archive-launcher route here and
[levkropp's boot agent](https://github.com/levkropp/samsung-tv-root-untethered).
It is separate from the older [QN90B FDET reproduction](QN90B_REPRODUCTION.md)
and the inherited Q60B report. Private controllers, credentials, backups and
raw device evidence are not included.

## Exact target and results

| Property | Observed value |
| --- | --- |
| Model | `QN55QN90BAFXZA` |
| Internal build | `T-PTMAKUC-REL-202602250225` |
| Platform | `Tizen6/TV 6.5.0 (arm)` |
| Kernel / architecture | Linux `5.4.77`, `armv7l` |
| Runtime / manager | .NET `3.1.3`, manager `5.13` targeting .NET Core 3.1 |
| Root route | Model-independent `archive-root` |
| Developer Mode | Enabled, effective Host PC IP `127.0.0.1` |

The numeric software version displayed in TV Settings was not recorded. The
older `1602.3` result does not identify this internal build. Platform preflight
still reports `compatible-untested`; the successful archive route does not
establish the FDET route or volatile UEP disable on this firmware.

Before activation, authenticated host root returned UID/EUID/GID/EGID zero.
Installation backed up the stock Gaming Hub application, its manifest and the
package database. All 13 deployed hashes, eight retained stock hashes,
ownership/modes/SMACK labels and three system-file hashes were checked. Only
the Gaming Hub row's three startup fields changed. No privacy/debloat module
was installed or enabled.

After the successful reboot, a new kernel boot ID matched the root proof.
Real/effective/saved/filesystem UID and GID were all zero. Matching proof was
collected twice as SDK UID 901 through the authenticated diagnostic relay
before any post-boot host root. All 24 checked core hashes and six metadata
captures were preserved; task staging was subsequently removed with guarded
cleanup. Root retained Samsung's `User` SMACK label.

## Failures that mattered

The manager-created evidence directory initially belonged to UID 5001 with
mode `0755`. The SDK launcher could connect but could not redirect its output
there, so the root-launch block did not run. The successful setup retained the
existing shared/transmute metadata and files while changing this directory to
SDK `901:901`, mode `0777`. An exclusive SDK create/read/remove check passed
before the next activation. See [deployment](../../boot-agent/README.md#deploy-one-time).

Automatic root then passed, but `tvroot-bridge.service` was absent/inactive.
The deployed `modules/bridge-service/boot.sh` matched the Windows checkout and
contained 32 CRLF lines. Read-only Linux Bash parsing of the original bytes
returned exit 2 with line 33 `unexpected end of file`; an LF-only stdin copy
returned exit 0. No service repair was performed during that test.

The source now requires LF shell scripts even with `core.autocrlf=true`, and
regressions check the raw bytes and Bash stdin parsing. This prevents future
bad deployment bytes; it does not repair the existing TV copy. Its script must
still be backed up, replaced while preserving metadata, hash-checked, parsed
and exercised as a separately scoped live operation.

The token-authenticated diagnostic SDK relay on port `26104` works while the
manager process lives. It proves SDK connectivity, not root or independence
from the manager. The default headless port `26103` remains unverified here.

## Remote activation and reboot method

After installation and initial Developer Mode setup, the verified activation
required no TV-menu, remote-button or physical interaction. The desktop
initiated activation and reboot; the installed manager initiated the root
chain on the subsequent boot.

1. Check the exact model/build, runtime, deployed hashes, retained metadata and
   recovery backups. Qualify SDK access to shared staging and evidence first.
2. Obtain temporary authenticated archive-launcher root. Inspect full identity,
   namespaces, reboot capability, the prepared helper, current boot and settings.
3. A detached controller saves readiness durably, disconnects its ordinary SDK
   session and acknowledges one developer-host write. After the helper writes
   localhost, save the typed readback and caller context before sending a
   separate power acknowledgement.
4. The helper performs at most one libc `sync()` and one `reboot(RB_AUTOBOOT)`.
   A dropped connection or ambiguous acknowledgement permits neither a retry
   nor automatic restoration. A later reboot-only attempt used a fresh one-use
   packet and left localhost unchanged.
5. On the new boot, collect matching complete root proof as SDK twice before
   host root, then check global hashes outside private bind views and clean
   only task-owned staging.

The experimental reboot/cutover helpers and device-specific controllers stay
outside this contribution. Their source and qualification history remain in
the [development fork](https://github.com/kninetimmy/samsung-tv-root-untethered/tree/eaa21ece2b953d716052a113eaa41987ee484650/tools/reboot-helper).
The supported installation instructions here use the Developer Mode menu and
a normal full reboot. Direct kernel restart bypasses application shutdown;
quiet storage samples and `sync()` do not establish database consistency or
general restart safety. Remote access loss can require physical recovery.

## Remaining validation

Wrong-token rejection on this TV, management after manager close or HDMI
switch, repeated reboot/standby-wake, native 4K120/HDR/VRR/FreeSync/Game Mode,
picture/audio behavior and actual stock restoration remain untested. One
automatic-root boot is not a reliability guarantee. Do not transfer this
result to another model, build or root route.
