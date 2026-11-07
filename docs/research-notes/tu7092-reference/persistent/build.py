#!/usr/bin/env python3
"""Build a self-contained awk boot carrier; no TV operations."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

SRC = Path(__file__).resolve().parent
OUT = None
BASE = '/opt/vetro-tu7092-root'
RUN = '/run/vetro-tu7092-root'
spec = importlib.util.spec_from_file_location('canary', SRC.parent/'build_awk_canary.py')
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)


def main(argv=None):
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--marker-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    OUT = args.out.resolve()
    if OUT.exists():
        raise SystemExit('Output already exists; refusing to overwrite')
    marker = args.marker_dir.resolve()
    marker_report = json.loads((marker/'report.json').read_text())
    original = (marker/'original').read_bytes()
    marker_carrier = (marker/'Dlog_buffer.sh.candidate').read_bytes()
    if hashlib.sha256(original).hexdigest() != canary.VENDOR_SHA:
        raise SystemExit('Wrong vendor original')
    if hashlib.sha256(marker_carrier).hexdigest() != marker_report['candidate_sha256']:
        raise SystemExit('Wrong marker carrier')
    assets = {name: (SRC.parent/name).read_bytes() for name in ('agent-node4.js', 'executor.sh', 'supervisor.sh')}
    # Validate the opened file, not a pathname checked before a potentially racing open.
    old = """        var stat = fs.lstatSync(CONFIG);
        if (!stat.isFile() || (stat.mode & 63)) throw new Error('unsafe agent config permissions');
        cfg = JSON.parse(fs.readFileSync(CONFIG, 'utf8'));"""
    new = """        var fd = fs.openSync(CONFIG, 'r');
        try {
            var stat = fs.fstatSync(fd);
            if (!stat.isFile() || (stat.mode & 63) || stat.uid !== Number(process.env.VETRO_CONFIG_UID) || stat.size < 1 || stat.size > 4096) throw new Error('unsafe agent config');
            var data = new Buffer(stat.size);
            var count = fs.readSync(fd, data, 0, data.length, 0);
            if (count !== data.length) throw new Error('incomplete agent config');
            cfg = JSON.parse(data.toString('utf8'));
        } finally { fs.closeSync(fd); }"""
    text = assets['agent-node4.js'].decode()
    if text.count(old) != 1: raise SystemExit('Unexpected base agent source')
    assets['agent-node4.js'] = text.replace(old,new).replace('restart the manual root session','boot supervisor will reconnect').encode()
    assets['worker.sh'] = (SRC/'worker.sh').read_bytes()
    hashes = {name: hashlib.sha256(data).hexdigest() for name,data in assets.items()}
    version = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:12]
    dest = BASE + '/v-' + version
    bootstrap = ['set -eu', '[ "$(id -u)" = 0 ] && [ "$(id -g)" = 0 ] || exit 0',
        '[ ! -e /opt/data/DeviceTracker/tizenpwn.stop ] || exit 0',
        f'[ ! -e {BASE}/disabled ] || exit 0',
        '[ "$(sed -n \'s/^BUILD_ID=//p\' /etc/tizen-release)" = T-KTSU2DEUC-REL-202607022000 ] || exit 0',
        'umask 077', f'[ ! -L {BASE} ] && [ ! -L {dest} ] || exit 1',
        f'mkdir -p -m 755 {BASE}', f'[ "$(stat -c %u {BASE})" = 0 ] || exit 1',
        f'chmod 755 {BASE}', f'chsmack -a _ {BASE}', f'mkdir -p -m 700 {dest}',
        f'[ "$(stat -c %u {dest})" = 0 ] || exit 1', f'chmod 700 {dest}']
    for name,data in assets.items():
        path=dest+'/'+name
        bootstrap += [f'if [ ! -f {path} ] || [ "$(sha256sum {path} | cut -d \' \' -f 1)" != {hashes[name]} ]; then',
            'printf %s '+base64.b64encode(data).decode()+f' | base64 -d > {path}.new',
            f'chmod 600 {path}.new', f'mv -f {path}.new {path}', 'fi',
            f'[ "$(sha256sum {path} | cut -d \' \' -f 1)" = {hashes[name]} ] || exit 1']
    bootstrap += [f'mkdir -m 755 {RUN} 2>/dev/null || exit 0', f'chsmack -a _ {RUN}',
        f'/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin VETRO_BOOT_BASE={BASE} VETRO_BOOT_RUN={RUN} VETRO_BOOT_ASSETS={dest} /usr/bin/setsid /bin/bash -c "$(cat {dest}/worker.sh)" </dev/null >{RUN}/worker.log 2>&1 &']
    boot='\n'.join(bootstrap)+'\n'
    subprocess.run(['/bin/bash','-n'],input=boot.encode(),check=True)
    subprocess.run(['/bin/bash','-n'],input=assets['worker.sh'],check=True)
    # Keep the already-proven marker and the original DeviceTracker behavior.
    command=canary.BOOT_COMMAND+'\n/bin/bash -c "$(printf %s '+base64.b64encode(boot.encode()).decode()+' | /usr/bin/base64 -d)"'
    carrier=canary.render(original,command)
    if len(carrier)>100000: raise SystemExit('Carrier exceeds reviewed argument budget')
    OUT.mkdir(parents=True)
    for name,data in assets.items(): (OUT/name).write_bytes(data)
    (OUT/'bootstrap.sh').write_text(boot)
    (OUT/'Dlog_buffer.sh').write_bytes(carrier)
    report={'base':BASE,'runtime':RUN,'version':version,'asset_hashes':hashes,
        'carrier_sha256':hashlib.sha256(carrier).hexdigest(),'carrier_bytes':len(carrier),
        'expected_current_sha256':marker_report['candidate_sha256'],
        'scope':'prepared Vetro agent integration; not installed','tracking_masks_reapplied':False}
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
