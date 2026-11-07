"""Host lifecycle simulation: fake identity, never a claim of TV root."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

SOURCE = Path(__file__).with_name('worker.sh')


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vetro-worker-test-')
        self.root = Path(self.tmp.name)
        for name in ('base', 'run', 'assets', 'stage', 'bin'):
            (self.root/name).mkdir()
        for name, body in [('id', 'echo 0'), ('chsmack', 'exit 0')]:
            p = self.root/'bin'/name
            p.write_text('#!/bin/sh\n'+body+'\n'); p.chmod(0o700)
        (self.root/'attr').write_text('_')
        (self.root/'caps').write_text('CapEff:\t0000003fffffffff\n')
        (self.root/'assets/agent-node4.js').write_text('// harmless fixture')
        (self.root/'assets/executor.sh').write_text(':')
        (self.root/'assets/supervisor.sh').write_text('''
echo "$$ $VETRO_AGENT_CONFIG" >> "$TEST_ROOT/starts"
trap 'echo stopped >> "$TEST_ROOT/stops"; exit 0' TERM INT HUP
if [ ! -f "$TEST_ROOT/failed-once" ]; then touch "$TEST_ROOT/failed-once"; exit 1; fi
while :; do sleep 0.1; done
''')
        self.env = dict(os.environ, PATH=str(self.root/'bin')+':'+os.environ['PATH'],
            TEST_ROOT=str(self.root), VETRO_BOOT_BASE=str(self.root/'base'),
            VETRO_BOOT_RUN=str(self.root/'run'), VETRO_BOOT_ASSETS=str(self.root/'assets'),
            VETRO_BOOT_STAGE=str(self.root/'stage'), VETRO_BOOT_STOP=str(self.root/'stop'),
            VETRO_BOOT_ATTR=str(self.root/'attr'), VETRO_BOOT_CAPFILE=str(self.root/'caps'),
            VETRO_BOOT_CONFIG_UID=str(os.getuid()))
        self.proc = None

    def launch(self):
        self.proc = subprocess.Popen(['/bin/bash', str(SOURCE)], env=self.env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def wait_for(self, predicate, timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate(): return
            time.sleep(.1)
        self.fail('timed out waiting for lifecycle event')

    def lines(self, name):
        p=self.root/name
        return p.read_text().splitlines() if p.exists() else []

    def config(self, suffix, valid=True):
        parent=self.root/'stage'/('vetro-external-'+suffix*24)
        parent.mkdir(mode=0o700)
        p=parent/'agent.json';p.write_text('{}');p.chmod(0o600 if valid else 0o644)
        return p

    def test_wait_reconnect_rotation_and_stop(self):
        self.launch()
        self.wait_for(lambda: (self.root/'run/status.txt').exists())
        self.assertIn('waiting-for-vetro',(self.root/'run/status.txt').read_text())
        first=self.config('a',False)
        time.sleep(3.2)
        self.assertFalse(self.lines('starts'), 'unsafe config must be ignored')
        first.chmod(0o600)
        self.wait_for(lambda: len(self.lines('starts'))>=2)
        second=self.config('b')
        os.utime(second,(time.time()+2,time.time()+2))
        self.wait_for(lambda: any(str(second) in x for x in self.lines('starts')))
        (self.root/'stop').touch()
        self.proc.wait(timeout=5)
        self.assertEqual(self.proc.returncode,0)
        self.assertIn('state=stopped',(self.root/'run/status.txt').read_text())
        self.assertGreaterEqual(len(self.lines('stops')),2)
        for line in self.lines('starts'):
            with self.assertRaises(ProcessLookupError): os.kill(int(line.split()[0]),0)

    def test_insufficient_capabilities_refused(self):
        (self.root/'caps').write_text('CapEff:\t0000000000000000\n')
        self.config('a'); self.launch(); self.proc.wait(timeout=5)
        self.assertEqual(self.proc.returncode,1)
        self.assertIn('capabilities-failed',(self.root/'run/status.txt').read_text())
        self.assertFalse(self.lines('starts'))

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired: self.proc.kill();self.proc.wait()
        for line in self.lines('starts'):
            try: os.killpg(int(line.split()[0]),signal.SIGTERM)
            except ProcessLookupError: pass
        self.tmp.cleanup()


if __name__ == '__main__': unittest.main(verbosity=2)
