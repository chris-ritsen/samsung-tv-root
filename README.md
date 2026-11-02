# Samsung TV root

I built working root exploits for the two Samsung TVs I own: a QN90B purchased
in 2022 and a QN90F purchased in July 2026. I use them to make the TVs less
annoying: remap the remote to whichever Arch Linux computer is connected,
control my window manager and MPV, control active YouTube, Plex, and X.com
playback through CDP, and collect diagnostics from the TV.

My TVs are blocked from the internet after Developer Mode is enabled. A
host-side controller reacquires root whenever either TV powers on.

The QN90B took about a day with Codex in March 2026. The QN90F took about three
hours with a newer version of Codex in July 2026, right out of the box. This
public repository is a clean subset of my setup; it does not contain Samsung
firmware, Samsung binaries, or extracted AES keys. It works for me every day.
Ask if you run into problems. Enjoy.

## What is this

Source and host tooling for obtaining volatile root on two tested Samsung Tizen
TVs, keeping root available while the TV is on, observing or remapping physical
remote input, controlling selected native TV functions, and recovering Samsung
SWU firmware keys.

The source tree does not track Samsung firmware, Samsung's `sdb` binary,
extracted keys, device tokens, serial numbers, private network configuration, or
precompiled exploit payloads. Release archives contain payloads built from this
source.

This README describes v0.0.12 and the current source tree. The `archive-root`
command requires v0.0.9 or newer, or a source checkout; it is absent from v0.0.8
and earlier standalone releases. For commands in an older download, use its
bundled documentation or the [v0.0.8 README](https://github.com/chris-ritsen/samsung-tv-root/blob/v0.0.8/README.md).
v0.0.10 added detection for Samsung's nonstandard .NET apphost. v0.0.11 also
accepts a different active CLR directory and permits an explicit runtime choice
when discovery is unavailable. Neither change establishes root on a new TV.
v0.0.12 retries the SDB timing check when its first control call was unusually
slow, and restores the host library path for OpenSSL launched by the frozen
Linux executable. These are host-tool fixes, not new TV exploit routes.

## TV compatibility

Root results are for **exact models and firmware**, not every size or regional
variant in a series. "Owner-tested" means I ran the chain on my TV. "Reported"
means another owner reports UID 0 or an authenticated root agent; linked reports
vary in how much evidence they provide. "Candidate" means an offline firmware
match, **not** a successful TV test or a promise that the current release works.
All routes below start with the `SVE-2025-50109` SDB package-name foothold unless
the row says otherwise. Root access and volatile UEP disable are separate results.

| Status | Exact TV or firmware family | Firmware | Root route and result | Evidence / limitation |
| --- | --- | --- | --- | --- |
| Owner-tested | `QN55QN90BAFXZA` (QN90B) | `T-PTMAKUC-1602.3` | FDET physical-memory route; archive-launcher route also tested | [QN90B reproduction](docs/research-notes/QN90B_REPRODUCTION.md) |
| Owner-tested | `QN75QN90FAFXZA` (QN90F) | `T-RSMFAKUC-0090-1203.0` | Mali-G510 `CVE-2025-0072` route; archive-launcher route also tested | [QN90F reproduction](docs/research-notes/QN90F_REPRODUCTION.md) |
| Reported, public release | `QA55QN90FAUXEG` (QN90F) | `T-RSMFUABC-0090-1301.0` | Mali route; authenticated root, full capability mask and volatile UEP disable | [Independent v0.0.3 validation](docs/research-notes/QN90F_REPRODUCTION.md#tested-targets); the TV UI misspelled the family `RSMFUBAC` |
| Reported, adapted | `QN55Q60BAFXZC` (Q60B) | `T-NKLBAKUC-1720.7` | Archive-launcher route; later boot-time self-root in a [fork](https://github.com/levkropp/samsung-tv-root-untethered/tree/untethered-boot-agent) | [Owner's UID 0 proof and runtime-detection fix](https://github.com/chris-ritsen/samsung-tv-root/issues/1); not stock release behavior |
| Reported, adapted | `UE50AU9072UXXH` (AU9072) | `T-NKLADEUC-2301.1` | Archive-launcher route; authenticated UID 0 | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/5); requires a .NET 3.1 runtime-path fallback |
| Reported, adapted | `QE77S90CATXXN` (S90C) | `T-PTMCDEUC-2000.2` | Archive-launcher bootstrap through a separate direct-SDB wrapper | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/3) and [downstream source](https://github.com/invaliddayta/s90c-tools); not an unmodified controller test |
| Reported, adapted | `TQ43Q7F3AUXXC` (Q7F3A) | `T-RSLFDEUC-0090`, build `202608061939` | Archive-launcher route; authenticated UID 0 | [Owner's v0.0.9 report](https://github.com/chris-ritsen/samsung-tv-root/issues/5#issuecomment-6338160290); requires runtime-detection fallback |
| Reported, adapted | `UE43DU7100KXXU` (DU7100) | `T-KSU2EDDEUC-0090-REL-202603190204`, 2130.0 | Archive-launcher route; authenticated UID 0 | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/6); host-side runtime fallback on an older checkout, not an unmodified release test |
| Reported, downstream | `QN43LS03DAFXZA` (Frame 2024) | `T-PTMDAKUC-0090-2130.0` | Archive-launcher probe returned UID 0 | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/8); vendored v0.0.11 code in `quiet-tizen`, with a first-call timing false negative |
| Reported, downstream | `QA55QEF1AULXL` (QEF1A) | `T-RSLFUABC-0090-REL-202608061940` | SDB plus archive-launcher route; authenticated UID 0 | [Owner's evidence](https://github.com/DemonKingSwarn/samsung-tv-tizen-root/blob/main/evidence/root-evidence.json) and [write-up](https://github.com/DemonKingSwarn/samsung-tv-tizen-root/blob/main/ROOTING-RESEARCH.md); adapted host wrapper, not an unmodified release test |
| Reported, public release | `UA43AU7000KXXD` (AU7000) | `T-KSU2EUABC-REL-202607211852` | Unmodified v0.0.11 archive-launcher route; authenticated UID 0 twice | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/9); frozen Linux host needed an OpenSSL library-path workaround |
| Reported, downstream | `QN85QN90AAFXZA` (QN90A) | `T-NKM2AKUC-2301.1` | SDB plus archive-launcher-based root, later TV-local reacquisition | [Couchroot device record](https://github.com/splitcipher/couchroot/blob/main/docs/lab/devices/qn90a/README.md) and [owner's Reddit report](https://www.reddit.com/r/Tizen/comments/1x3cog3/experimental_release_vetro_allinone_tv_manager/) |
| Reported, downstream | `QN55S90DAFXZA` (S90D) | `T-PTMDAKUC-0090-2130.0` | SDB plus capability/mount-namespace/archive-launcher route | [Owner's route description](https://www.reddit.com/r/Tizen/comments/1wl4e0n/i_made_a_minimal_plexyoutube_launcher_the_default/) and [Couchroot device record](https://github.com/splitcipher/couchroot/blob/main/docs/lab/devices/s90d/README.md) |
| Reported, downstream | `QE50Q80AATXZT` (Q80A) | `T-NKM2DEUC-2301.1` | Vetro's archive-launcher-derived integration; authenticated root agent | [Vetro compatibility record](https://github.com/andrearicci93/vetro#compatibility); not this CLI/release |
| Reported, downstream | `QE43Q67BAUXXH` (Q67B) | `T-NKLBDEUC-1720.7` | Vetro integration reported UID 0 | [Community diagnostic in Vetro](https://github.com/andrearicci93/vetro#compatibility); cold-boot persistence and device controls unverified |
| Candidate, untested | Other QN90B variants using `T-PTMAKUC-1602.3` | `1602.3` | FDET route has an identical vulnerable handler in the decrypted update | Same firmware code is strong evidence, but no other size/region was root-tested here |
| Candidate, untested | Other QN90F variants using the inspected `T-RSMF*` firmware | `1131.0`, `1296.8`, `1301.0` | SDB and archive-launcher prerequisites are present in inspected images | Mali kernel exploitability and the live runtime/preflight remain unverified; 1301.0 is proven only on the model above |
| Candidate, untested | QN80F / Frame 2025 on `T-PTMFAKUC-0090` | `1131.0`, `1301.0` | SDB plus archive-launcher route is a static candidate | Files and SDB pattern found offline; no live root result or proven Mali route |
| Candidate, untested | S90F family on `T-RSMFAKUC-0090` | `1301.0` | SDB plus archive-launcher route is a static candidate | Do not infer the QN90F Mali chain merely from an `r48p0` userspace library |
| Candidate, untested | QN80H / Frame 2026 on `T-PTMHAKUC-0100` | `1204.6` | SDB plus archive-launcher route is a static candidate | Tizen 10 image inspected offline; no retail root test |

v0.0.10 includes runtime detection for Samsung's nonstandard `dotnet` apphost,
which the Q60B, AU9072, and Q7F3A owners had worked around locally. Those owners
have not yet confirmed an unmodified v0.0.10 or v0.0.11 release on their TVs.

On one `UN50M75HAGXZD` running Tizen 10, [the owner reports](https://github.com/chris-ritsen/samsung-tv-root/issues/7)
that SDB connects but rejects this package-name injection before archive-root
preflight can run. This is an exact-build foothold failure, not evidence that all
Tizen 10 TVs reject the route.

The [QN90D fork's experimental branch](https://github.com/lzongren/samsung-tv-root/blob/codex/qn90d-hdmi-wake-service/docs/qn90d-hdmi-wake.md)
describes an archive-root-assisted installation on `QN50QN90DAFXZA`, firmware
`T-PTMDAKUC-0090-2130.0`, but does not publish a separate UID-0 root proof;
it is not counted as a confirmed root result above. A [Q90T owner](https://github.com/chris-ritsen/samsung-tv-root/issues/2#issuecomment-6297686929)
reported root through a **different USB-root adaptation**, while this project's
archive route failed on that TV. Neither is a compatibility claim for this CLI.

Most forks have no commits beyond this repository; a fork or successful app
installation alone is not root evidence. Report new results with exact model,
firmware/build, route, release or local changes, and an authenticated UID-0
readback. The preflight's `tested`, `compatible-untested`, and `incompatible`
labels reflect its own platform checks, not all community reports in this table.

## Included

- The public `SVE-2025-50109` SDB package-name injection for the initial
  `uid=901(sdk)` command foothold.
- A QN90B `/dev/sdp_pqe_fdet` physical-memory exploit.
- A QN90F Mali-G510 r48p0 exploit based on `CVE-2025-0072`.
- A model-independent SDK archive-launcher root route in the source tree,
  live-tested on my QN90B and QN90F.
- Interactive root shells and authenticated root command execution.
- UEP status and volatile disable controls for unsigned native execution.
- An event-driven host controller that reacquires root after TV boot or root
  agent loss.
- Opt-in remote observation, suppression, remapping, and structured events.
- HDMI source, local-dimming, PC/Game/Input Signal Plus, and Picture Off
  controls where listed as implemented below.
- Speaker-volume control and opt-in native TV event streams.
- QN90F retained-frame screenshots and bounded compositor overlays.
- SWU firmware-key extraction for both tested models.

Root and UEP changes remain volatile. The controller makes root appear
semi-persistent by reacquiring it from another computer after a TV reboot. It
does not install a TV-side boot service. The optional source-only boot agent
below provides a separate, manually installed TV-side path.

## Optional TV-side boot-root

**BLUF:** The [boot agent](boot-agent/README.md) lets a supported TV start its
own archive-launcher root chain at boot, without a desktop initiating it. A
token-authenticated headless SDB bridge keeps host access available while
Developer Mode Host PC IP stays at `127.0.0.1`. Installation is manual, opt-in,
and repurposes the stock Gaming Hub service; updating the host CLI installs
nothing on the TV.

The contribution builds on [levkropp's untethered-root fork](https://github.com/levkropp/samsung-tv-root-untethered)
with additional integration and exact-device validation from
[kninetimmy's fork](https://github.com/kninetimmy/samsung-tv-root-untethered).
It adds .NET Core 3.1/.NET 6 boot builds, bridge-aware archive-root commands,
shared staging/evidence requirements, Windows LF deployment checks and a
fresh-boot identity-proof verifier.

| Reported model/build | Result | Remaining boundary |
| --- | --- | --- |
| `QN55QN90BAFXZA`, `T-PTMAKUC-REL-202602250225`, Tizen 6.5/.NET 3.1.3 | One automatic-root reboot; complete zero UID/GID and matching new boot ID retrieved twice as SDK before post-boot host root | Installed CRLF bridge script still blocks headless access; source prevention passes, live repair pending |
| `UN50U8000FFXZA`, `T-X22UDFAKUC-0090-REL-202607141244`, Tizen 9/.NET 6.0.9 | One automatic-root reboot; fresh proof retrieved as SDK before host root; headless access survived manager close | Repeated power cycles, standby/wake, HDMI gaming and actual rollback remain untested |

These are exact-build reports using `archive-root`; they do not establish new
FDET/Mali targets or unrestricted SMACK access. The earlier Q60B result remains
an inherited report. See the [QN90B report](docs/research-notes/QN90B_BOOT_ROOT.md)
and [U8000 report](docs/research-notes/U8000_REPRODUCTION.md) for evidence,
deployment failures and recovery limits. Private framework assemblies, signing
keys, tokens and backups are not included. The optional boot manager is built
from source against the TV's own framework; it is not a bundled release installer.

## Capability status

`implemented` means the public adapter and payload source are present. Use the
documentation shipped with a release to check that release's capabilities.
`proven_not_packaged` means the operation was validated on the stated TV but
the public adapter is not included. `not_investigated` means this project has
not established an answer for that model. `unsupported` is reserved for a
verified platform limitation; no row below currently makes that claim.

| Capability                                               | QN90B                 | QN90F                 |
| -------------------------------------------------------- | --------------------- | --------------------- |
| Root, command execution, UEP control                     | `implemented`         | `implemented`         |
| Source list, current source, HDMI selection              | `implemented`         | `implemented`         |
| HDMI presentation recovery                               | `not_investigated`    | `implemented`         |
| Local-dimming status, set, toggle                        | `implemented`         | `implemented`         |
| PC mode, Game Mode, Input Signal Plus status/enforcement | `not_investigated`    | `implemented`         |
| Picture Off, display status, display wake                | `implemented`         | `implemented`         |
| Remote input observation, filtering, TV-native actions   | `implemented`         | `implemented`         |
| Speaker volume get/set and native change events          | `implemented`         | `implemented`         |
| Foreground app, source, lifecycle, HDMI receiver events  | `implemented`         | `implemented`         |
| Processed 960x540 HDMI capture                           | `not_investigated`    | `implemented`         |
| Transparent text and graphics overlays                   | `not_investigated`    | `implemented`         |

The running controller exposes the machine-readable inventory:

```console
samsung-tv-root capabilities my-tv
samsung-tv-root -o json capabilities my-tv
```

## Run from source

Python 3.12 or newer can run the host CLI directly; a standalone release is not
required. From a clone of this repository:

```console
git clone https://github.com/chris-ritsen/samsung-tv-root.git
cd samsung-tv-root
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m samsung_tv_root doctor
.venv/bin/python -m samsung_tv_root preflight qn90f 192.0.2.50
```

On Windows, use `py -3.12` to create the environment and replace
`.venv/bin/python` with `.venv\Scripts\python.exe`. Pass `--sdb` before the
subcommand when Tizen Studio is not in its default location:

```console
.venv\Scripts\python.exe -m samsung_tv_root --sdb C:\tizen-studio\tools\sdb.exe preflight qn90f 192.0.2.50
```

Preflight needs only Python and Samsung's `sdb`. Root operations also need the
TV payloads. With GNU Make and the .NET 6 SDK installed, build the model-specific
payloads once:

```console
make common-payload qn90b-payload qn90f-payload
.venv/bin/python -m samsung_tv_root doctor
```

Then use `.venv/bin/python -m samsung_tv_root qn90f root ...`. On Windows,
replace `.venv/bin/python` with `.venv\Scripts\python.exe`; the payload build
also requires GNU Make and the .NET SDK. A standalone release avoids these build
requirements.

The archive route additionally needs the host's `openssl` command
on `PATH`. For TVs with .NET 3.1, build `make common31-payload` using SDK
6.0.428, as selected by `payloads/common31/global.json`. The build restores the
.NET 3.1 reference packages from NuGet; installing a .NET 3.1 SDK is not required.

`uv sync --locked` followed by `uv run samsung-tv-root ...` is the equivalent
developer workflow.

## Install a release

Download from [Releases](https://github.com/chris-ritsen/samsung-tv-root/releases)
and extract the archive matching the host:

- Linux x86-64 or ARM64: `.tar.gz`
- macOS Intel or Apple Silicon: `.tar.gz`
- Windows x86-64 or ARM64: `.zip`

Each archive contains a standalone host executable, TV payloads built from this
source, documentation, and the corresponding source tree. Samsung's `sdb` is
not redistributed; install [Tizen Studio](https://developer.tizen.org/development/tizen-studio/download)
separately.

Run the installation check:

```console
./samsung-tv-root doctor
```

Use `samsung-tv-root.exe` on Windows. Put an unusual Tizen Studio location
before the command, for example
`./samsung-tv-root --sdb /path/to/tizen-studio/tools/sdb doctor`.

If a command is rejected as an `invalid choice`, check `--version` and `--help`
against the documentation for that release. In particular, v0.0.8 does not
contain `archive-root`; download v0.0.9 or newer, or use a source checkout.

Create the configuration once, then replace the example name and address with
the TV's values:

```console
./samsung-tv-root config init
./samsung-tv-root config check
```

Each table under `televisions` is a named profile. Direct `preflight`, `root`,
`uep`, and `serve` commands infer the profile when the configuration contains
exactly one TV for that model. If it contains multiple TVs of the same model,
select one with `--profile NAME`. Supplying a host explicitly remains supported.
For a nonstandard Tizen Studio installation, add a top-level
`sdb = "C:/path/to/tizen-studio/tools/sdb.exe"`; explicit `--sdb` still wins.

## Enable Developer Mode

Use the remote's number-entry controls; a Samsung `BN59-01199F` full-button IR
remote was used on the tested TVs. On the TV,
open Smart Hub, open Apps, focus App Settings, and enter `12345` with the
remote's number keys. Enable Developer Mode, enter the controller computer's
IPv4 address, and reboot the TV.

Verify that `sdb` sees only the intended TV:

```console
export TV_IP=192.0.2.50
export SDB=/absolute/path/to/tizen-studio/tools/sdb
"$SDB" connect "$TV_IP:26101"
"$SDB" devices
```

On the tested retail firmware, a plain interactive `sdb shell` prints `closed`
and exits. That is expected and does not show whether the exploit works. The
exploit instead invokes the allowed package installer with a crafted package
name; preflight verifies that separate path with a bounded execution-timing
probe before testing the callback.

In Windows Command Prompt, set the full `sdb.exe` path before testing:

```bat
set TV_IP=192.0.2.50
set SDB=C:\tizen-studio\tools\sdb.exe
"%SDB%" connect "%TV_IP%:26101"
"%SDB%" devices
samsung-tv-root.exe preflight qn90f "%TV_IP%"
```

## One root session

With one configured QN90F profile, run the fingerprint preflight and open a
root shell without repeating its address:

```console
./samsung-tv-root preflight qn90f
./samsung-tv-root qn90f root
```

The equivalent explicit-host form is:

```console
./samsung-tv-root preflight qn90f "$TV_IP"
./samsung-tv-root qn90f root "$TV_IP"
```

Without `--command`, the QN90F command opens one persistent Bash process on a
real PTY. Shell state such as `cd` and exported variables persists; terminal
control, `clear`, Ctrl-C, full-screen programs, and window resizing are relayed.
Type `exit` or press Ctrl-D to close it. The temporary TV listener accepts only
the selected controller address, defaults to TCP port 22222, and is removed
when the session ends. Use `--shell-port PORT` if that port is unavailable.

Run a local Bash script as root without Samsung's script-filename signature
check:

```console
./samsung-tv-root qn90f root "$TV_IP" --script ./httptoolkit.sh
```

The authenticated root agent uploads the script to a private per-session
directory under `/run`, invokes Bash with the script sourced through `-c`, and
removes the directory when the agent exits. It does not replace `/bin/bash` or
install the script. Repeat `--script-argument VALUE` to pass arguments. UEP must
first be disabled for the current boot only when the script itself launches
unsigned native executables.

The QN90F preflight first compares a no-op with a bounded two-second delay to
prove that the SDB package-name injection executed. It then stages a read-only
fingerprint script through SDB, reports the exact callback address and port,
and runs that script through the already-authorized shell. The command does not
change firewall rules, configure logging, or run the root exploit. Override
route detection when needed:

```console
./samsung-tv-root preflight qn90f "$TV_IP" --callback-host 192.0.2.10
```

If the timing probe succeeds but the callback times out, the package-installer
exploit ran and the remaining failure is in staging, script execution, or the
reverse callback path. A failed timing probe means shell execution itself was
not confirmed.

To make one explicit attempt without the compatibility preflight:

```console
./samsung-tv-root qn90f root "$TV_IP" --skip-preflight
```

This skips only the fingerprint gate. Root acquisition still requires the TV to
connect back to the listening host.

Use `qn90b` for the older TV. Run one command with:

```console
./samsung-tv-root qn90f root "$TV_IP" --command 'id; uname -a'
```

With a configured profile, inspect or disable UEP for the current boot:

```console
./samsung-tv-root qn90f uep status
./samsung-tv-root qn90f uep disable
```

The explicit-host forms are:

```console
./samsung-tv-root qn90f uep "$TV_IP" status
./samsung-tv-root qn90f uep "$TV_IP" disable
```

`disable` is idempotent. A successful result reports a validated kernel
neighborhood and either `uep_status_action=disabled` with
`uep_status_after=0`, or `uep_status_action=already-disabled` with
`uep_status_before=0`. Run it before opening the root shell when that shell will
launch uploaded native ELF programs. If a root shell is already open, exit it,
run `uep disable`, and reopen it; do not start a second exploit session in
parallel just to change UEP.

A normal `sdb shell` remains closed on the tested retail firmware. `sdb push`
works for the controller staging directory:

```console
"$SDB" -s "$TV_IP:26101" push ./local-file /home/owner/share/tmp/sdk_tools/local-file
```

The Windows Command Prompt form is:

```bat
"%SDB%" -s "%TV_IP%:26101" push local-file /home/owner/share/tmp/sdk_tools/local-file
```

TV paths passed to `sdb` are POSIX paths even on a Windows host, so prefer
`/home/owner/share/tmp/...` there as well. Current retail firmware can reject
`sdb pull` with `You cannot pull files from this path` even when the Unix mode
allows the SDK user to read the file. Pull through the authenticated root
session instead:

```console
./samsung-tv-root qn90f root "$TV_IP" \
  --pull /home/owner/share/tmp/remote-file ./remote-file
```

```bat
samsung-tv-root.exe qn90f root "%TV_IP%" --callback-host 192.0.2.10 ^
  --pull /home/owner/share/tmp/remote-file remote-file
```

The controller reads the source without modifying it, stages bounded chunks
only under volatile `/run/samsung-tv-root`, verifies the complete SHA-256, and
atomically replaces the local destination after successful verification.

UEP compatibility differs from root compatibility. The model reproduction
document describes the tested boundaries and both supported application
execution paths.

### Archive root route

This route requires v0.0.9 or newer, or a source checkout with built payloads.
Ensure `openssl` is on the host's `PATH`. Standalone archives already include
both the .NET 6 and .NET 3.1 archive payloads; source builds are described
[above](#run-from-source).

This separate root method uses the SDB package-name foothold, a
capability-bearing Samsung `dotnet`, a private mount namespace, and Samsung's
signed-archive launcher. [motodrizzle](https://www.reddit.com/r/Tizen/comments/1wl4e0n/i_made_a_minimal_plexyoutube_launcher_the_default/)
reported the capability/namespace/launcher route on an S90D; this implementation
adapts that route. It has no model whitelist: it checks the SDB foothold,
capabilities, tar support, and .NET runtime on the target and chooses its payload
accordingly. It was live-tested on my QN90B and QN90F with an
authenticated UID/GID 0 agent, root command execution, unchanged system-file
hashes, and per-run staging cleanup. The S90D firmware has matching platform
components, and its owner reported the same underlying route, but this exact
implementation has not been run on an S90D. The agent still has Samsung's
`User` SMACK label; UID 0 is not proof that every security boundary is gone.

```console
./samsung-tv-root archive-root probe "$TV_IP"
./samsung-tv-root archive-root root "$TV_IP" --command 'id'
```

The generic archive commands do not require a `qn90b` or `qn90f` profile. If
the TV has the required capabilities but its .NET runtime cannot be discovered,
an owner can select the installed runtime with `--runtime 3.1` or
`--runtime 6.0` on either command. `6.0` selects the .NET 6 payload for a
compatible runtime version 6 or later. This only bypasses runtime discovery;
the SDB foothold, file capabilities, tar support, authenticated UID-0 callback,
and cleanup checks still apply. A wrong choice can fail the attempt, so use it
only after inspecting the target's runtime. The result records whether the
runtime was detected or explicitly selected.

On Windows, use `samsung-tv-root.exe`. From source, replace `./samsung-tv-root`
with `.venv/bin/python -m samsung_tv_root` (Windows:
`.venv\Scripts\python.exe -m samsung_tv_root`).
`probe` performs the full root acquisition, authenticated identity check, and
cleanup. It is not a read-only compatibility check. Both commands require a
working SDB connection; an open TCP port or a reachable TV network API alone
does not establish that SDB is available.

Use `-o json` before `archive-root` for machine-readable identity and cleanup
evidence. The older `archive-root probe MODEL HOST` spelling still works, but
the model label no longer selects or limits the route. `--command` can be
repeated. This option does not yet provide an interactive PTY, disable UEP, or
run through the host controller. The existing root commands remain the
defaults. It never replaces `/etc/passwd`, the verification key, or the
installed Bash on disk: the helper binds per-run views inside its own mount
namespace. Its archive and payloads are staged under
`/home/owner/share/tmp/sdk_tools` and normally removed after the session; an
interrupted run may leave those files on persistent user storage. The ephemeral
signing private key stays on the controller computer.

## Continuous controller

Create the default no-remap configuration if one was not already created for
the direct commands:

```console
./samsung-tv-root config init
```

Edit the TV name, model, and address in the file printed by `config init`, then
validate it and start the controller:

```console
./samsung-tv-root config check
./samsung-tv-root daemon run
```

The daemon follows TV lifecycle events, acquires root, and starts explicitly
configured remote and native-event sessions.
`my-tv` in the examples below is that user-chosen configuration name.

On Linux with a systemd user manager, install the host service explicitly:

```console
./samsung-tv-root service install --enable --now
./samsung-tv-root service status
```

Automatic service installation for macOS and Windows is not implemented. Run
`daemon run` under the service manager of your choice on those hosts.

Once the controller is running:

```console
./samsung-tv-root status
./samsung-tv-root root acquire my-tv
./samsung-tv-root execute my-tv 'id; uname -a'
./samsung-tv-root source list my-tv
./samsung-tv-root source select my-tv HDMI2
./samsung-tv-root local-dimming toggle my-tv
./samsung-tv-root volume status my-tv
```

Both models implement display status, Picture Off, and wake. QN90F also
implements HDMI policy, retained-frame screenshots, and bounded overlays:

```console
./samsung-tv-root hdmi-policy enforce my-tv --source HDMI2
./samsung-tv-root display picture-off my-tv
./samsung-tv-root display wake my-tv
./samsung-tv-root screenshot my-tv frame.png
./samsung-tv-root overlay message my-tv 'Hello' --seconds 5
```

Native TV events are disabled by default. Enable the profile's `events` table,
restart the host controller, then use `events status` or `events watch`. The
event agent has no restart policy or TV-side boot unit and exits when its
authenticated host connection closes.

See the [controller](docs/user/CONTROLLER.md) and
[remote input](docs/user/REMOTE_POLICY.md) guides for configuration and
extension details.

## Firmware keys

Firmware-key extraction is included for both tested models. Its advanced,
source-oriented procedure is in the
[SWU AES extraction research note](docs/research-notes/AES_EXTRACTION.md).

## Build from source

Source development requires Python 3.12, `uv`, a .NET 6 SDK, and Clang/LLD with
ARMv7 support. Install SDK 6.0.428 for the legacy archive payload build and
OpenSSL for archive-root commands:

```console
uv sync --all-groups
make payloads swu-preloads
make lint test audit
make release
```

GitHub Actions tests Linux, macOS, and Windows, builds the TV payloads, packages
the supported host architectures, and publishes archives for `v*` tags.

## Documentation

Start with the [quick start](QUICKSTART.md). The
[documentation index](docs/README.md) separates practical end-user guides from
implementation and reverse-engineering research notes.

This project is released under the [Unlicense](LICENSE).
