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

## Tested TVs

| Profile | Exact model      | Installed firmware | Internal build                     | Platform                                           |
| ------- | ---------------- | ------------------ | ---------------------------------- | -------------------------------------------------- |
| `qn90b` | `QN55QN90BAFXZA` | `T-PTMAKUC-1602.3` | `T-PTMAKUC-REL-202310071804`       | Tizen 6.5, Linux 5.4.77, ARMv7                     |
| `qn90f` | `QN75QN90FAFXZA` | `1203.0`           | `T-RSMFAKUC-0090-REL-202512092052` | Tizen 9.0, Linux 5.4.261, AArch64, Mali-G510 r48p0 |

Other screen sizes, model variants, and firmware versions are untested. The
preflight reports `tested`, `compatible-untested`, or `incompatible` from the
platform requirements instead of rejecting every build-number change.

## Included

- The public `SVE-2025-50109` SDB package-name injection for the initial
  `uid=901(sdk)` command foothold.
- A QN90B `/dev/sdp_pqe_fdet` physical-memory exploit.
- A QN90F Mali-G510 r48p0 exploit based on `CVE-2025-0072`.
- Interactive root shells and authenticated root command execution.
- UEP status and volatile disable controls for unsigned native execution.
- An event-driven host controller that reacquires root after TV boot or root
  agent loss.
- Opt-in remote observation, suppression, remapping, and structured events.
- HDMI source, local-dimming, PC/Game/Input Signal Plus, and Picture Off
  controls where listed as implemented below.
- SWU firmware-key extraction for both tested models.

Root and UEP changes remain volatile. The controller makes root appear
semi-persistent by reacquiring it from another computer after a TV reboot. It
does not install a TV-side boot service.

## Capability status

`implemented` means the public adapter and release payload are present.
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
| Picture Off, display status, display wake                | `proven_not_packaged` | `implemented`         |
| Remote input observation, filtering, TV-native actions   | `implemented`         | `implemented`         |
| Speaker volume get/set and native change events          | `proven_not_packaged` | `proven_not_packaged` |
| Foreground app, source, lifecycle, HDMI receiver events  | `proven_not_packaged` | `proven_not_packaged` |
| Processed 960x540 HDMI capture                           | `not_investigated`    | `proven_not_packaged` |
| Transparent text and graphics overlays                   | `not_investigated`    | `proven_not_packaged` |

The running controller exposes the machine-readable inventory:

```console
samsung-tv-root capabilities my-tv
samsung-tv-root -o json capabilities my-tv
```

## Install a release

Download and extract the archive matching the host:

- Linux x86-64 or ARM64: `.tar.gz`
- macOS Intel or Apple Silicon: `.tar.gz`
- Windows x86-64 or ARM64: `.zip`

Each archive contains a standalone host executable, TV payloads built from this
source, documentation, and the corresponding source tree. Samsung's `sdb` is
not redistributed; install Tizen Studio separately.

Run the installation check:

```console
./samsung-tv-root doctor
```

Use `samsung-tv-root.exe` on Windows. Pass an unusual Tizen Studio location with
`--sdb /path/to/tizen-studio/tools/sdb`.

## Enable Developer Mode

Use a Samsung `BN59-01199F` full-button IR remote for this step. On the TV,
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

A normal `sdb shell` closing immediately is expected on the tested retail
firmware. The package installer remains the command foothold.

## One root session

Run the fingerprint preflight, then open a root shell:

```console
./samsung-tv-root preflight qn90f "$TV_IP"
./samsung-tv-root qn90f root "$TV_IP"
```

Use `qn90b` for the older TV. Run one command with:

```console
./samsung-tv-root qn90f root "$TV_IP" --command 'id; uname -a'
```

Inspect or disable UEP for the current boot:

```console
./samsung-tv-root qn90f uep "$TV_IP" status
./samsung-tv-root qn90f uep "$TV_IP" disable
```

UEP compatibility differs from root compatibility. The model reproduction
documents describe the tested boundaries.

## Continuous controller

Create the default no-remap configuration:

```console
./samsung-tv-root config init
./samsung-tv-root config check
./samsung-tv-root daemon run
```

Edit the generated TV name, model, and address. The daemon follows TV lifecycle
events, acquires root, and starts the explicitly configured remote sessions.
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
```

QN90F also implements:

```console
./samsung-tv-root hdmi-policy enforce my-tv --source HDMI2
./samsung-tv-root display picture-off my-tv
./samsung-tv-root display wake my-tv
```

See [Controller](docs/CONTROLLER.md) and [Remote input](docs/REMOTE_POLICY.md)
for configuration and extension details.

## Firmware keys

Firmware-key extraction is included for both tested models. See
[SWU AES extraction](docs/AES_EXTRACTION.md).

## Build from source

Source development requires Python 3.12, `uv`, a .NET 6 SDK, and Clang/LLD with
ARMv7 support:

```console
uv sync --all-groups
make payloads swu-preloads
make lint test audit
make release
```

GitHub Actions tests Linux, macOS, and Windows, builds the TV payloads, packages
the supported host architectures, and publishes archives for `v*` tags.

## Documentation

- [Quick start](QUICKSTART.md)
- [Controller](docs/CONTROLLER.md)
- [Remote input](docs/REMOTE_POLICY.md)
- [Exploit chain](docs/EXPLOIT_CHAIN.md)
- [QN90B reproduction](docs/QN90B_REPRODUCTION.md)
- [QN90F reproduction](docs/QN90F_REPRODUCTION.md)
- [SWU AES extraction](docs/AES_EXTRACTION.md)

This project is released under the [Unlicense](LICENSE).
