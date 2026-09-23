import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_approved_worker_package as package


class ApprovedWorkerPackageTests(unittest.TestCase):
    def test_fixed_source_only_contents_and_hashes(self):
        files = {name: ('synthetic ' + name).encode() for name in package.FILES}
        data = package.package_bytes('a' * 40, files)
        self.assertEqual(data, package.package_bytes('a' * 40, files))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(set(archive.namelist()), set(package.FILES) | {'manifest.json'})
            self.assertFalse(manifest['activated'])
            self.assertFalse(manifest['model_weights_included'])
            self.assertFalse(manifest['media_included'])
            self.assertIn('scripts/run_approved_cpu_worker.py', archive.namelist())
            self.assertIn('scripts/run_approved_video_worker.py', archive.namelist())
            self.assertNotIn('backend/app/main.py', archive.namelist())
            for name, value in files.items():
                self.assertEqual(manifest['files'][name], hashlib.sha256(value).hexdigest())

    def test_extra_or_missing_source_refused(self):
        files = {name: b'x' for name in package.FILES}
        with self.assertRaises(ValueError):
            package.package_bytes('a' * 40, {**files, '.env': b'secret'})
        files.pop(next(iter(files)))
        with self.assertRaises(ValueError):
            package.package_bytes('a' * 40, files)

    def test_floating_commit_symlink_and_oversize_refused(self):
        with self.assertRaises(ValueError):
            package.source_files('HEAD')
        with patch.object(package, 'git', side_effect=[b'commit', b'120000 blob abc\tbackend/app/config.py\0']):
            with self.assertRaises(ValueError):
                package.source_files('a' * 40)
        rows = b'\0'.join(('100644 blob abc\t' + name).encode() for name in package.FILES)
        with patch.object(package, 'git', side_effect=[b'commit', rows, *([b'999999'] * len(package.FILES))]):
            with self.assertRaises(ValueError):
                package.source_files('a' * 40)
