# Documentation

Start with the [quick start](../QUICKSTART.md) to install the host tool, create a
TV profile, run preflight, and open a root shell.

These guides describe v0.0.11 and the current source tree. `archive-root` requires
v0.0.9 or newer, or a source checkout. For older standalone downloads, start with
their bundled documentation or the [v0.0.8 README](https://github.com/chris-ritsen/samsung-tv-root/blob/v0.0.8/README.md).

## End-user guides

- [Host controller](user/CONTROLLER.md): configuration, lifecycle, service, and
  control commands.
- [Remote input](user/REMOTE_POLICY.md): opt-in observation, suppression, and
  remapping.

## Device reports

- [TQ55LS03FAUXXC / T-PTMFDEUC-0090-1301.0](reports/TQ55LS03FAUXXC.md):
  first-hand archive-root success, authenticated UID 0, no kernel/USB exploit,
  no persistence.

## Research notes

These files preserve implementation, exploit reproduction, and reverse-
engineering details. They are not setup guides. Commands and observations may
be historical, incomplete, or specific to a source checkout and tested
firmware.

- [Exploit chain](research-notes/EXPLOIT_CHAIN.md)
- [QN90B reproduction](research-notes/QN90B_REPRODUCTION.md)
- [QN90F reproduction](research-notes/QN90F_REPRODUCTION.md)
- [SWU AES extraction](research-notes/AES_EXTRACTION.md)
