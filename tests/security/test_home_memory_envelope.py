import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import home_memory_envelope as envelope


class MemoryEnvelopeTests(unittest.TestCase):
    def test_limits_refuse_unbounded_or_weakened_launch(self):
        for limit, floor in [(0, 8192), (2049, 8192), (True, 8192), (2048, 4096)]:
            with self.assertRaises(ValueError):
                envelope.limits(limit, floor)

    @unittest.skipIf(sys.platform == 'win32', 'Non-Windows refusal')
    def test_other_platforms_cannot_silently_launch_unbounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'report.json'
            with self.assertRaises(OSError):
                envelope.run([sys.executable, '-c', 'raise AssertionError'], marker)
            self.assertFalse(marker.exists())

    @unittest.skipUnless(sys.platform == 'win32', 'Requires the native Windows kernel')
    def test_job_limit_inherits_to_grandchild_and_blocks_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'allocation.json'
            code = ('import json;from pathlib import Path\n'
                    'try:\n b=bytearray(256*1024**2);state="unexpected_allocation"\n'
                    'except MemoryError:state="allocation_blocked"\n'
                    f'Path({str(marker)!r}).write_text(json.dumps({{"state":state}}))\n')
            child = 'import subprocess,sys;sys.exit(subprocess.call([sys.executable,"-c",' + repr(code) + ']))'
            report = root / 'job.json'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/home_memory_envelope.py'),
                                     '--memory-mib', '128', '--report', str(report), '--',
                                     sys.executable, '-c', child], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual(json.loads(marker.read_text())['state'], 'allocation_blocked')
            summary = json.loads(report.read_text())
            self.assertEqual(summary['state'], 'finished')
            self.assertEqual(summary['limit_bytes'], 128*1024**2)
            self.assertEqual(summary['limit_flags'], 0x200)

    @unittest.skipUnless(sys.platform == 'win32', 'Requires the native Windows kernel')
    def test_limit_is_shared_between_parent_and_grandchild(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'allocation.json'
            code = ('from pathlib import Path\n'
                    'try:\n b=bytearray(64*1024**2);state="unexpected_allocation"\n'
                    'except MemoryError:state="aggregate_allocation_blocked"\n'
                    f'Path({str(marker)!r}).write_text(state)\n')
            child = ('import subprocess,sys;a=bytearray(64*1024**2);'
                     'sys.exit(subprocess.call([sys.executable,"-c",' + repr(code) + ']))')
            report = root / 'job.json'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/home_memory_envelope.py'),
                                     '--memory-mib', '128', '--report', str(report), '--',
                                     sys.executable, '-c', child], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual(marker.read_text(), 'aggregate_allocation_blocked')

    @unittest.skipUnless(sys.platform == 'win32', 'Requires the native Windows kernel')
    def test_small_work_completes_and_propagates_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'job.json'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/home_memory_envelope.py'),
                                     '--memory-mib', '256', '--report', str(report), '--',
                                     sys.executable, '-c', 'a=bytearray(8*1024**2);raise SystemExit(7)'],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 7, result.stderr.decode(errors='replace'))
            summary = json.loads(report.read_text())
            self.assertEqual(summary['returncode'], 7)
            self.assertGreater(summary['kernel_peak_job_memory_bytes'], 8*1024**2)
