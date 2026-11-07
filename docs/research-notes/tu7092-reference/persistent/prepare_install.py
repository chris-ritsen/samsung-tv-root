"""Generate reviewable SDK installation/recovery scripts; no network calls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle', type=Path, required=True)
args = parser.parse_args()
OUT = args.bundle.resolve()
REPORT=json.loads((OUT/'report.json').read_text())
NEW=REPORT['carrier_sha256']
OLD=REPORT['expected_current_sha256']
VENDOR='7bacb5b029bcc932e1ad450895172ff18270bde1894b14612c108a38cb17003c'
TARGET='/opt/data/DeviceTracker/Dlog_buffer.sh'
STOP='/opt/data/DeviceTracker/tizenpwn.stop'
BACKUP='/opt/data/DeviceTracker/.vetro-backup-'+NEW[:12]
STAGE='/home/owner/share/tmp/sdk_tools/vetro-boot-update-'+NEW[:12]
GUARD='''set -eu
[ "$(sed -n 's/^BUILD_ID=//p' /etc/tizen-release)" = T-KTSU2DEUC-REL-202607022000 ] || exit 3
[ "$(id -u)" = 901 ] || exit 4
'''


def check(path, digest):
    return f'[ ! -L {path} ] && [ -f {path} ] && [ "$(sha256sum {path} | cut -d \' \' -f 1)" = {digest} ] || exit 6\n'


def main():
    assert hashlib.sha256((OUT/'Dlog_buffer.sh').read_bytes()).hexdigest()==NEW
    install=GUARD+check(TARGET,OLD)+check(STAGE+'/Dlog_buffer.sh',NEW)+check('/opt/tizenpwn-awk-canary/original',VENDOR)
    install+=f'''[ ! -e {STOP} ] || exit 7
[ ! -e {BACKUP} ] && [ ! -L {BACKUP} ] || exit 7
umask 077
mkdir -m 700 {BACKUP}
cp {TARGET} {BACKUP}/canary
cp /opt/tizenpwn-awk-canary/original {BACKUP}/vendor-original
cp {STAGE}/rollback-sdk.sh {BACKUP}/rollback-sdk.sh
cp {STAGE}/Dlog_buffer.sh {BACKUP}/candidate
chmod 600 {BACKUP}/canary {BACKUP}/vendor-original {BACKUP}/rollback-sdk.sh
chmod 755 {BACKUP}/candidate
'''
    install+=check(BACKUP+'/canary',OLD)+check(BACKUP+'/vendor-original',VENDOR)+check(BACKUP+'/candidate',NEW)+check(TARGET,OLD)
    install+=f'''sync
mv -f {BACKUP}/candidate {TARGET}
sync
'''+check(TARGET,NEW)+f'''ls -lZ {TARGET}
sha256sum {TARGET} {BACKUP}/canary {BACKUP}/vendor-original
echo INSTALL_OK
'''
    rollback=GUARD+check(TARGET,NEW)+check(BACKUP+'/canary',OLD)
    rollback+=f'''umask 077
: > {STOP}
cp {BACKUP}/canary {BACKUP}/restore.tmp
chmod 755 {BACKUP}/restore.tmp
'''+check(BACKUP+'/restore.tmp',OLD)+check(TARGET,NEW)+f'''sync
mv -f {BACKUP}/restore.tmp {TARGET}
sync
'''+check(TARGET,OLD)+'''echo 'CANARY_RESTORED; stop file retained to stop active worker'
'''
    for name,body in [('install-sdk.sh',install),('rollback-sdk.sh',rollback)]:
        subprocess.run(['/bin/bash','-n'],input=body.encode(),check=True)
        (OUT/name).write_text(body)
    (OUT/'deployment.json').write_text(json.dumps({'stage':STAGE,'backup':BACKUP,'target':TARGET,'new_sha256':NEW,'old_sha256':OLD,'stop':STOP},indent=2)+'\n')
    print('Prepared guarded installer and SDK rollback; no TV changes')


if __name__=='__main__': main()
