# Samsung TV root

I built working root exploits for the two Samsung TVs I own: a QN90B purchased
in 2022 and a QN90F purchased in July 2026. I use them to make the TVs less
annoying: remap the remote to whichever Arch Linux computer is connected,
control my window manager and MPV, control active YouTube, Plex, and X.com
playback through CDP, and collect diagnostics from the TV.

My TVs are blocked from the internet after Developer Mode is enabled. A
host-side controller reacquires root whenever either TV powers on.

The QN90B took about a day with Codex in May 2026. The QN90F took about three
hours with a newer version of Codex in July 2026, right out of the box. This
public repository is a clean subset of my setup; it does not contain Samsung
firmware, Samsung binaries, or extracted AES keys. It works for me every day.
Ask if you run into problems. Enjoy.

## Start here

This repository contains root routes, a host controller, and TV controls.

For a tested TV, follow the [quick start](QUICKSTART.md). You need Developer
Mode, Samsung's `sdb` (standalone or from Tizen Studio), and a controller
computer on the same network. The [quick start](QUICKSTART.md#1-install-sdb)
includes the standalone Linux download. Download a matching host archive
from [Releases](https://github.com/chris-ritsen/samsung-tv-root/releases) or
[run from source](#run-from-source). The release archives include built TV
payloads, but not `sdb`.

With a configured QN90F profile, the basic sequence is:

```console
./samsung-tv-root doctor
./samsung-tv-root preflight qn90f
./samsung-tv-root qn90f root
```

Use `qn90b` for the tested QN90B. On Windows, run `samsung-tv-root.exe` with
the same arguments. Do not substitute a different TV just because its model
name looks similar. `preflight` checks the model-specific path; it does not
run the root exploit. The [archive-route `probe`](#archive-root-route) is
different: it performs a full root attempt.

## Which TVs?

The model-specific routes have been tested on these exact TVs:

| TV | Tested firmware | Root route |
| --- | --- | --- |
| `QN55QN90BAFXZA` (QN90B) | `T-PTMAKUC-1602.3` | FDET physical-memory exploit; archive route also tested |
| `QN75QN90FAFXZA` (QN90F) | `T-RSMFAKUC-0090-1203.0` | Mali-G510 `CVE-2025-0072`; archive route also tested |

Other owners have reported root on more models, sometimes with changes to this
tool or a separate wrapper. Firmware inspection also identifies candidates
that have **not** been root-tested. The [compatibility record](docs/user/COMPATIBILITY.md)
keeps the exact models, firmware, routes, evidence, and limitations together.
No entry for a model means **not investigated**, not proven impossible or
safe to attempt. Root and the per-boot UEP bypass are separate results.

The common starting point is the `SVE-2025-50109` SDB package-name foothold.
The QN90B and QN90F then use different kernel exploits. A third route uses
Samsung's signed-archive launcher; it checks target prerequisites instead of
using a model whitelist. A working SDB connection is required for all three.

The goal is to cover more models with checked, repeatable routes. Reports and
forks are useful evidence, including novel exploits, but their persistence,
filesystem changes, and manual setup are not automatically appropriate here.
New routes should identify the exact platform, prove the resulting privileges,
automate checks and cleanup where possible, and avoid or track persistent TV
changes so they can be reversed.

## What it does

- Open a root shell or run an authenticated root command on the tested TVs.
- Check and disable UEP for the current boot when unsigned native tools need it.
- Keep root available through a host controller that reacquires it after TV
  lifecycle events. It does not install a TV-side boot service.
- Observe and optionally remap physical remote input; control sources,
  picture, display, and speaker volume where the model adapter supports them.
- Receive opt-in native TV events. QN90F also supports retained-frame
  screenshots and bounded overlays.
- Recover SWU firmware keys on the two tested models.

Root and UEP changes are volatile. The controller's host-side reacquisition is
not persistent root on the TV. Remote remapping and native event collection are
off until configured. Use `samsung-tv-root capabilities my-tv` for the current
model's machine-readable capability inventory; the [controller guide](docs/user/CONTROLLER.md)
explains the controls and their limits.

## Run from source

Python 3.12 or newer runs the host CLI. Preflight needs Python and Samsung's
`sdb`; root commands also need built TV payloads. On Linux or macOS:

```console
git clone https://github.com/chris-ritsen/samsung-tv-root.git
cd samsung-tv-root
python -m venv .venv
.venv/bin/python -m pip install -e .
make common-payload qn90b-payload qn90f-payload
.venv/bin/python -m samsung_tv_root doctor
```

Building payloads requires GNU Make, the .NET 6 SDK, and Clang/LLD with ARMv7
support. The archive route also requires host OpenSSL. For a TV with .NET 3.1,
build `common31-payload` with
SDK 6.0.428; it restores the .NET 3.1 reference packages from NuGet.
`uv sync --locked` and `uv run samsung-tv-root ...` are the equivalent developer
workflow.

On Windows, create the environment with `py -3.12`, use
`.venv\Scripts\python.exe`, and pass `--sdb C:\path\to\sdb.exe` before the
subcommand if Tizen Studio is outside its default location. The [quick start](QUICKSTART.md)
has Developer Mode, profile, and Windows command examples.

## Archive root route

The archive route requires v0.0.9 or newer, or a source build. It uses the
SDB foothold, a capability-bearing Samsung `dotnet`, a private mount namespace,
and Samsung's signed-archive launcher. [motodrizzle's S90D work](https://www.reddit.com/r/Tizen/comments/1wl4e0n/i_made_a_minimal_plexyoutube_launcher_the_default/)
described this route; this implementation adapts it. It was live-tested here
on QN90B and QN90F, not on every model in the compatibility record.

```console
./samsung-tv-root archive-root probe 192.0.2.50
./samsung-tv-root archive-root root 192.0.2.50 --command 'id'
```

`probe` performs root acquisition, authenticated UID-0 verification, and
cleanup; **it is not a read-only compatibility check**. The route does not yet
provide an interactive PTY, disable UEP, or replace the controller's root
method. It leaves system files unchanged in tested runs, but stages files on
persistent user storage during the attempt; an interruption may leave them
there. Its private signing key stays on the host. UID 0 does not remove every
Samsung security boundary.

## More information

- [Quick start](QUICKSTART.md): install, Developer Mode, profiles, and first root.
- [Compatibility](docs/user/COMPATIBILITY.md): exact-model results and reports.
- [Controller](docs/user/CONTROLLER.md) and [remote input](docs/user/REMOTE_POLICY.md):
  host service, commands, and remapping.
- [Research notes](docs/README.md): exploit reproduction and SWU key extraction.

This README describes v0.0.13 and the current source tree. Older standalone
releases have different commands; use their bundled documentation. The source
does not track device tokens, serial numbers, private network configuration,
firmware, extracted keys, or precompiled exploit payloads. The project is
released under the [Unlicense](LICENSE).
