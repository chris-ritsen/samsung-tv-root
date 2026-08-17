# Host controller

The controller keeps volatile root available without modifying the TV's boot
configuration. It runs on a computer that has Tizen Studio `sdb` access to the
TV.

## Configuration

Generate a configuration and edit it:

```console
samsung-tv-root config init
samsung-tv-root config check
```

The minimal file is:

```toml
version = 1

[televisions.my-tv]
model = "qn90f"
host = "192.0.2.50"
root_on_presence = true
disable_native_execution_policy = false

[televisions.my-tv.remote]
enabled = false
devices = []
rules = []
```

Add another table under `televisions` for another TV. `device_id` may contain
the TV's exact SSDP UUID when address matching is insufficient.

`disable_native_execution_policy` controls a separate volatile UEP state. Root
does not require UEP to be disabled because the controller executes its
managed payloads through Samsung's signed `/usr/bin/dotnet` runtime. Leave the
setting false unless unsigned native execution is required.

## Lifecycle

At startup, the daemon resolves each configured host, opens its authenticated
loopback control endpoint, joins SSDP notifications, and sends one discovery
request. A matching response or alive notification starts root acquisition.

The acquisition sequence is:

1. Validate the target where the model path requires preflight.
2. Use SDB package-name command injection to start the model-specific payload.
3. Validate every exploit restoration guard.
4. Accept an authenticated root-agent callback only from the configured TV.
5. Confirm UID and GID 0 before publishing `rooted`.
6. Start explicitly configured remote input sessions.

The root connection is monitored directly. If it closes while the same TV boot
is still present, the controller uses the finite retry delays from the
configuration. A new SSDP boot generation resets that bounded attempt state.
There is no periodic root probe, polling loop, TV-side boot unit, or host
service restart policy.

## Running it

Run in the foreground on any supported host:

```console
samsung-tv-root daemon run
```

Linux can install a systemd user service:

```console
samsung-tv-root service install --enable --now
samsung-tv-root service status
```

The generated unit uses `Type=notify`. It has no `Restart=` directive. Service
installation for macOS and Windows is not implemented; their native service
managers can run the same foreground command.

## Control API

CLI requests use a mode-0600 loopback endpoint file containing a random token.
The endpoint accepts authenticated JSON requests and event subscriptions. It is
not a LAN server.

Useful commands:

```console
samsung-tv-root status
samsung-tv-root capabilities my-tv
samsung-tv-root root acquire my-tv
samsung-tv-root execute my-tv 'id'
samsung-tv-root source current my-tv
samsung-tv-root source select my-tv HDMI1
samsung-tv-root local-dimming status my-tv
```

Machine-readable responses use `--output json` before the command.
Root command execution retains at most 1 MiB from each of stdout and stderr. If
either stream exceeds that bound, the agent drains the remaining bytes and adds
an explicit truncation notice to stderr without dropping the root connection.

Capability records distinguish four states:

- `implemented`: callable from this public controller.
- `proven_not_packaged`: validated on that model outside this public adapter.
- `not_investigated`: no validated conclusion for that model.
- `unsupported`: evidence proves the model cannot provide the operation.
