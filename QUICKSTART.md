# Quick start

## 1. Install Tizen Studio

Install Tizen Studio from Samsung/Tizen. This project does not redistribute
Samsung's `sdb` executable.

On Linux, the full Studio install is optional: Samsung's public package
server publishes `sdb` alone (a few MB, with a Samsung-published SHA256 in
`pkg_list_ubuntu-64` on the same server):

```console
curl -O https://download.tizen.org/sdk/tizenstudio/official/binary/sdb_4.2.36_ubuntu-64.zip
unzip sdb_4.2.36_ubuntu-64.zip
./sdb-pkg/data/tools/sdb version
```

Verify the archive against the checksum Samsung lists for the package
before use. The standalone `sdb` is enough for `preflight` and
`archive-root`; only SDK features beyond `sdb` need Tizen Studio.

## 2. Enable Developer Mode

On the TV:

1. Open Smart Hub and Apps.
2. Focus App Settings and enter `12345`.
3. Enable Developer Mode.
4. Enter the controller computer's LAN IPv4 address.
5. Reboot the TV.

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

These instructions describe v0.0.11 and the current source tree. `archive-root`
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
