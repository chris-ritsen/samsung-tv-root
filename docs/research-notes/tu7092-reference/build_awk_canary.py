#!/usr/bin/env python3
"""Build an offline DeviceTracker canary; never connects to or changes the TV."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

OUT = None
VENDOR_SHA = '7bacb5b029bcc932e1ad450895172ff18270bde1894b14612c108a38cb17003c'
BASE = '/opt/tizenpwn-awk-canary'
TARGET = '/opt/data/DeviceTracker/Dlog_buffer.sh'
STOP = '/opt/data/DeviceTracker/tizenpwn.stop'
BOOT_COMMAND = f'[ ! -e {STOP} ] && [ -f {BASE}/enable ] && [ -r {BASE}/boot ] && /bin/sh -c "$(cat {BASE}/boot)"; :'
BOOT = f'''[ "$(id -u)" = 0 ] || exit 0
[ ! -e {STOP} ] || exit 0
[ -f {BASE}/enable ] || exit 0
umask 022
mkdir /run/tizenpwn-awk-canary 2>/dev/null || exit 0
{{
    printf 'uid=%s\\n' "$(id -u)"
    printf 'gid=%s\\n' "$(id -g)"
    printf 'context=%s\\n' "$(cat /proc/self/attr/current)"
    sed -n '/^CapEff:/p' /proc/self/status
    printf 'boot_id='
    cat /proc/sys/kernel/random/boot_id
    printf 'uptime='
    cat /proc/uptime
}} > {BASE}/last-boot.new
chmod 644 {BASE}/last-boot.new
chsmack -a _ {BASE}/last-boot.new
mv {BASE}/last-boot.new {BASE}/last-boot.txt
'''.encode()


def render(vendor: bytes, bootstrap: str) -> bytes:
    encoded = base64.b64encode(vendor).decode('ascii')
    vendor_command = '/bin/bash -c "$(printf %s ' + encoded + ' | /usr/bin/base64 -d)"'
    return ('#!/usr/bin/awk -f\n'
            '# TU7092 canary: run optional marker, then preserved vendor body.\n'
            'BEGIN {\n    system(' + json.dumps(bootstrap) + ');\n'
            '    exit system(' + json.dumps(vendor_command) + ');\n}\n').encode()


def main(argv=None):
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True, help='Byte-exact original from your own TV; never redistributed')
    parser.add_argument('--out', type=Path, required=True, help='New local output directory; contains vendor bytes, do not publish')
    args = parser.parse_args(argv)
    OUT = args.out.resolve()
    if OUT.exists():
        raise SystemExit('Output already exists; refusing to overwrite')
    original = args.original.read_bytes()
    if len(original) != 2844 or hashlib.sha256(original).hexdigest() != VENDOR_SHA:
        raise SystemExit('Unexpected vendor DeviceTracker bytes')
    candidate = render(original, BOOT_COMMAND)
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    # Only restores the known canary; never follows an unexpected live revision.
    rollback = f'''#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || exit 4
[ "$(sed -n 's/^BUILD_ID=//p' /etc/tizen-release)" = T-KTSU2DEUC-REL-202607022000 ] || exit 3
BASE={BASE}
TARGET={TARGET}
[ ! -L "$BASE" ] && [ -d "$BASE" ] || exit 5
[ ! -L "$BASE/original" ] && [ -f "$BASE/original" ] || exit 5
[ "$(sha256sum "$BASE/original" | cut -d ' ' -f 1)" = {VENDOR_SHA} ] || exit 5
[ "$(wc -c < "$BASE/original")" -eq 2844 ] || exit 5
[ ! -L "$TARGET" ] && [ -f "$TARGET" ] || exit 6
current=$(sha256sum "$TARGET" | cut -d ' ' -f 1)
case "$current" in
    {VENDOR_SHA}) rm -f "$BASE/enable"; echo 'Original already present'; exit 0 ;;
    {candidate_sha}) ;;
    *) echo 'Unexpected boot script; restore refused'; exit 6 ;;
esac
command -v chsmack >/dev/null || exit 7
rm -f "$BASE/enable"
cp "$BASE/original" "$BASE/restore.tmp"
chown 0:0 "$BASE/restore.tmp"
chmod 777 "$BASE/restore.tmp"
chsmack -a _ "$BASE/restore.tmp"
mv -f "$BASE/restore.tmp" "$TARGET"
sync
[ "$(sha256sum "$TARGET" | cut -d ' ' -f 1)" = {VENDOR_SHA} ] || exit 8
echo 'Original DeviceTracker bytes restored'
'''.encode()
    OUT.mkdir(parents=True)
    for name, data in [('Dlog_buffer.sh.candidate', candidate), ('original', original),
                       ('boot', BOOT), ('rollback.sh', rollback)]:
        (OUT / name).write_bytes(data)
    installer = [
        '#!/bin/sh', '# Review artifact only; execute as content through the root channel.',
        'set -eu', '[ "$(id -u)" = 0 ] || exit 4',
        '[ "$(sed -n \'s/^BUILD_ID=//p\' /etc/tizen-release)" = T-KTSU2DEUC-REL-202607022000 ] || exit 3',
        'command -v chsmack >/dev/null || exit 7',
        f'BASE={BASE}', f'TARGET={TARGET}',
        '[ ! -e "$BASE" ] && [ ! -L "$BASE" ] || exit 5',
        '[ ! -L "$TARGET" ] && [ -f "$TARGET" ] || exit 5',
        f'[ "$(sha256sum "$TARGET" | cut -d \' \' -f 1)" = {VENDOR_SHA} ] || exit 6',
        '[ "$(stat -c \'%u %g %a\' "$TARGET")" = "0 0 777" ] || exit 6',
        f'[ ! -e {STOP} ] || exit 6',
        'umask 077', 'mkdir -m 755 "$BASE"', 'chsmack -a _ "$BASE"',
        'cp "$TARGET" "$BASE/original"', 'chmod 644 "$BASE/original"',
        'chsmack -a _ "$BASE/original"',
        f'[ "$(sha256sum "$BASE/original" | cut -d \' \' -f 1)" = {VENDOR_SHA} ] || exit 8',
    ]
    for name, data in [('candidate', candidate), ('boot', BOOT), ('rollback.sh', rollback)]:
        installer += ['printf %s ' + base64.b64encode(data).decode() + ' | base64 -d > "$BASE/' + name + '"',
                      'chmod 600 "$BASE/' + name + '"', 'chsmack -a _ "$BASE/' + name + '"',
                      '[ "$(sha256sum "$BASE/' + name + '" | cut -d \' \' -f 1)" = ' + hashlib.sha256(data).hexdigest() + ' ] || exit 8']
    installer += [
        ': > "$BASE/enable"', 'chmod 600 "$BASE/enable"',
        'chmod 755 "$BASE/candidate"',
        # Recheck immediately before the only mutation of an existing boot file.
        f'[ "$(sha256sum "$TARGET" | cut -d \' \' -f 1)" = {VENDOR_SHA} ] || exit 6',
        'sync', 'mv -f "$BASE/candidate" "$TARGET"', 'sync',
        f'if [ "$(sha256sum "$TARGET" | cut -d \' \' -f 1)" != {candidate_sha} ]; then',
        '    /bin/sh -c "$(cat "$BASE/rollback.sh")"',
        '    exit 8', 'fi',
        'echo "Marker-only DeviceTracker canary installed; no reboot performed."',
    ]
    (OUT / 'install.sh').write_text('\n'.join(installer) + '\n')
    report = {'scope': 'offline marker-only canary; not installed', 'base': BASE,
              'target': TARGET, 'original_sha256': VENDOR_SHA,
              'candidate_sha256': candidate_sha, 'candidate_size': len(candidate),
              'rootfs_write_required': False, 'cold_boot_tested': False,
              'starts_vetro_agent': False, 'changes_telemetry': False,
              'vendor_body_embedded_verbatim_as_base64': True,
              'rollback_metadata_requires_live_recheck': True}
    report['installer_sha256'] = hashlib.sha256((OUT / 'install.sh').read_bytes()).hexdigest()
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
