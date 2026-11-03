# Quick start

## 1. Install SDB

Install [Tizen Studio](https://developer.tizen.org/development/tizen-studio/download)
from Samsung/Tizen, or use Samsung's standalone SDB package. This project does
not redistribute Samsung's `sdb` executable.

On Linux x86-64, the standalone package is enough for this tool; the full IDE
is not required. Download and verify it before extracting or running it:

```console
curl -fLO https://download.tizen.org/sdk/tizenstudio/official/binary/sdb_4.2.36_ubuntu-64.zip
printf '%s  %s\n' \
  addf825e1a886a9f220cb3d287e74438cae0ffafe5821b9baca9d4f6c7de5124 \
  sdb_4.2.36_ubuntu-64.zip | sha256sum -c -
```

Only after the checksum reports `OK`:

```console
unzip sdb_4.2.36_ubuntu-64.zip
./sdb-pkg/data/tools/sdb version
```

The checksum is published in Samsung's
[Linux package index](https://download.tizen.org/sdk/tizenstudio/official/pkg_list_ubuntu-64).
Pass the extracted executable's absolute path with `--sdb /path/to/sdb` before
the subcommand. This package is for x86-64 hosts, not Linux ARM64.

## 2. Enable Developer Mode

On the TV:

1. Open Smart Hub and Apps.
2. Focus App Settings and enter `12345`.
3. Enable Developer Mode.
4. Enter the controller computer's LAN IPv4 address.
5. Fully reboot the TV; a short press of Power may only enter standby. Owners
   of some models report needing to unplug the TV for about a minute and
   reconnect it before SDB starts. Do not interrupt an update or active use.

## 3. Check the release

Extract the matching release and run:

```console
./samsung-tv-root doctor
```

The examples below use `./samsung-tv-root` on Linux and macOS. On Windows, run
the same arguments with `samsung-tv-root.exe`. Release archives contain the TV
payloads; they do not require a local payload build. Put an unusual Tizen Studio
location before the command, for example
`./samsung-tv-root --sdb /path/to/sdb doctor`.

These instructions describe v0.0.12 and the current source tree. `archive-root`
requires v0.0.9 or newer, or a source checkout. For v0.0.8 and earlier downloads,
follow the bundled documentation or the
[v0.0.8 README](https://github.com/chris-ritsen/samsung-tv-root/blob/v0.0.8/README.md).

To run from source instead of a standalone release:

```console
git clone https://github.com/chris-ritsen/samsung-tv-root.git
cd samsung-tv-root
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m samsung_tv_root doctor
```

On Windows, use `py -3.12` and `.venv\Scripts\python.exe`. When running from a
source checkout, preflight needs only Python and `sdb`; root commands also
require GNU Make, the .NET 6 SDK, and built TV payloads. Run
`make common-payload qn90b-payload qn90f-payload` for the model-specific routes.
The archive route needs OpenSSL on the host's `PATH`; for a TV with .NET 3.1,
also run `make common31-payload` with SDK 6.0.428 installed. That build restores
the .NET 3.1 reference packages from NuGet. See the
[source instructions](README.md#run-from-source).

For source commands below, replace `./samsung-tv-root` with
`.venv/bin/python -m samsung_tv_root` (Windows:
`.venv\Scripts\python.exe -m samsung_tv_root`).

## 4. Save the TV profile

Create the configuration, then edit the file path printed by `config init`:

```console
./samsung-tv-root config init
./samsung-tv-root config check
```

The default file is `%APPDATA%\samsung-tv-root\config.toml` on Windows,
`~/Library/Application Support/samsung-tv-root/config.toml` on macOS, and
`$XDG_CONFIG_HOME/samsung-tv-root/config.toml` on Linux when
`XDG_CONFIG_HOME` is set, otherwise `~/.config/samsung-tv-root/config.toml`.

The generated `televisions.my-tv` table is a named profile. With one configured
QN90F profile, the model-specific commands infer it. Use `--profile NAME` when
more than one configured TV has the same model. A nonstandard Tizen Studio
installation can be saved as a top-level `sdb = "C:/path/to/sdb.exe"` value.

## 5. Verify and root the TV

Using the saved profile:

```console
./samsung-tv-root preflight qn90f
./samsung-tv-root qn90f root
```

On Windows, the exact commands are:

```bat
samsung-tv-root.exe preflight qn90f
samsung-tv-root.exe qn90f root
```

To run a local Bash script without installing it or replacing the TV's Bash:

```bat
samsung-tv-root.exe qn90f root --script httptoolkit.sh
```

The script is staged under volatile `/run` storage and removed with the root
session. Use `--script-argument VALUE` repeatedly when arguments are needed.

An explicit address remains supported:

```console
./samsung-tv-root preflight qn90f 192.0.2.50
./samsung-tv-root qn90f root 192.0.2.50
```

Use `qn90b` for the 2022 PontusM platform. Preflight reports `tested`,
`compatible-untested`, or `incompatible`. The QN90F route verifies restoration
of its temporary credential and GPU page-table changes before accepting root.
The QN90B route changes its own exploit process's credentials and exits after
the requested command; it does not perform the QN90F restoration sequence.

The archive route in v0.0.9 and newer has no model whitelist. It checks the SDB
foothold, required file capabilities, tar support, and installed .NET runtime,
then stages and executes a root payload. `probe` performs the full root
acquisition and cleanup; it is not a read-only preflight:

```console
./samsung-tv-root archive-root probe 192.0.2.50
./samsung-tv-root archive-root root 192.0.2.50 --command 'id'
```

Other models should use this generic route, not a QN90B/QN90F profile chosen
only for its year or Tizen version. See the
[exact-model reports](README.md#tv-compatibility).
`doctor` checks the host installation, not TV compatibility. A missing
`/usr/bin/dotnet` or missing effective capabilities is a route prerequisite
failure; `--runtime` only selects an installed compatible runtime and cannot
supply the missing host or privileges.

The callback must reach the listening host port with the TV's source address
preserved. Check host firewall and macOS Local Network permissions if callbacks
time out; NAT/SNAT and TCP relays can change that address and cause rejection.
Keep the peer-address check enabled.

This route was live-tested on QN90B and QN90F. It does not yet provide an
interactive shell, disable UEP, or replace the controller's root method. It
cleans its per-run TV staging files after a normal session.

All root routes here require a working SDB connection. If TCP port 26101 refuses
connections, resolve Developer Mode and SDB availability before running root
commands. A reachable TV network API does not prove SDB is available. A rejected
`dotnet --list-runtimes` currently stops archive-root runtime detection, even
when a runtime directory exists.

## 6. Keep root available

Run the controller with the same configuration:

```console
./samsung-tv-root daemon run
```

On Linux, the optional host service is:

```console
./samsung-tv-root service install --enable --now
./samsung-tv-root service status
```

The host controller reacquires volatile root after TV lifecycle events. It does
not install persistence on the TV. Remote observation and remapping remain off
until devices and rules are explicitly configured. Native TV event collection
also remains off until `events.enabled = true` is set for that TV.

Further end-user details are in the [controller](docs/user/CONTROLLER.md) and
[remote input](docs/user/REMOTE_POLICY.md) guides. Implementation and reversing
records are listed separately in the [documentation index](docs/README.md).
