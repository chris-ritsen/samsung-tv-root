# Quick start

## 1. Install Tizen Studio

Install Tizen Studio from Samsung/Tizen. This project does not redistribute
Samsung's `sdb` executable.

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

Use `samsung-tv-root.exe` on Windows. Supply an unusual Tizen Studio location
with `--sdb /path/to/tizen-studio/tools/sdb`.

## 4. Verify and root the TV

```console
./samsung-tv-root preflight qn90f 192.0.2.50
./samsung-tv-root qn90f root 192.0.2.50
```

Use `qn90b` for the 2022 PontusM platform. Preflight reports `tested`,
`compatible-untested`, or `incompatible`. Successful root acquisition includes
verification that temporary kernel state was restored.

## 5. Keep root available

Create and edit the default configuration:

```console
./samsung-tv-root config init
./samsung-tv-root config check
./samsung-tv-root daemon run
```

On Linux, the optional host service is:

```console
./samsung-tv-root service install --enable --now
./samsung-tv-root service status
```

The host controller reacquires volatile root after TV lifecycle events. It does
not install persistence on the TV. Remote observation and remapping remain off
until devices and rules are explicitly configured.

Further details are in [Controller](docs/CONTROLLER.md),
[Remote input](docs/REMOTE_POLICY.md), and the model reproduction documents.
