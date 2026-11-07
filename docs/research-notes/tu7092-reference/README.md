# TU7092 reference sources

Read [the full reproduction record](../TU7092_PERSISTENT_ROOT.md) first.
Target: **UE55TU7092UXXH / T-KTSU2DEUC-2743.0 /
T-KTSU2DEUC-REL-202607022000 only**.

| File | Purpose |
| --- | --- |
| `tizenpwn-eu.patch` | EU controller adaptation; apply only to rackrot/tizenpwn commit `d62f8bcc5759a97dc00b630a52a0e788bb957bd1` |
| `build_awk_canary.py` | Offline generator requiring your own exact original DeviceTracker script |
| `run_sdk.py` | Guarded SDK command runner; requires the patched tizenpwn checkout on `PYTHONPATH` |
| `test_boot_carrier.py` | Harmless host checks for preserved vendor execution and refused inputs |
| `agent-node4.js`, `executor.sh`, `supervisor.sh` | Node 4/Bash authenticated root-channel sources |
| `persistent/build.py` | Builds the full Vetro boot carrier from a previously generated marker bundle |
| `persistent/prepare_install.py` | Generates the guarded second-stage SDK installer and rollback |
| `persistent/worker.sh` | Boot supervisor, private configuration selection, stop and reconnect |
| `persistent/test_worker.py` | Host lifecycle simulation using fake identity and capabilities |

The sources follow the repository's Unlicense. The CIFS lab patch preserves
its upstream provenance and separate lab license; see the tizenpwn checkout's
`payloads/tu7000/cifs-lab/LICENSE` and `NOTICE.md`.

Host checks from this repository root:

```sh
python3 -m unittest discover -s docs/research-notes/tu7092-reference -p 'test_*.py'
python3 docs/research-notes/tu7092-reference/persistent/test_worker.py
```

Generated directories contain **your TV's Samsung vendor script**, including
when embedded as base64. Keep them private and outside Git. This source
directory intentionally contains no generated carriers, firmware or tokens.

The input/output arguments are portability changes; the generated carriers
are compared byte-for-byte with the previously installed versions during
contribution validation. No fresh-TV installation is claimed from host tests.
