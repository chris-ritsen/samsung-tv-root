"""Host-only checks. Harmless substitute vendor code; no TV or network access."""
import base64
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('canary', HERE/'build_awk_canary.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CarrierTests(unittest.TestCase):
    def test_optional_failure_does_not_skip_vendor(self):
        for optional, expected in [("printf 'BOOT\\n'", 'BOOT\nVENDOR\n'),
                                   ('exit 9', 'VENDOR\n'),
                                   (':', 'VENDOR\n')]:
            with self.subTest(optional=optional), tempfile.TemporaryDirectory() as d:
                vendor = b"printf 'VENDOR\\n'\n"
                carrier = builder.render(vendor, optional)
                self.assertIn(base64.b64encode(vendor), carrier)
                script = Path(d)/'carrier'
                script.write_bytes(carrier)
                script.chmod(0o700)
                result = subprocess.run([str(script)], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, expected)

    def test_wrong_original_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as d:
            original = Path(d)/'original'
            original.write_text('not Samsung firmware')
            output = Path(d)/'out'
            result = subprocess.run(['python3', str(HERE/'build_awk_canary.py'),
                                     '--original', str(original), '--out', str(output)],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Unexpected vendor', result.stderr)
            self.assertFalse(output.exists())

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            result = subprocess.run(['python3', str(HERE/'build_awk_canary.py'),
                                     '--original', '/nonexistent', '--out', d],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Output already exists', result.stderr)


if __name__ == '__main__':
    unittest.main()
