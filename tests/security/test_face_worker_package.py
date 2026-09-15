import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import build_face_worker_package as package


class WorkerPackageTests(unittest.TestCase):
    def test_fixed_source_only_contents_and_hashes(self):
        files={name:('synthetic '+name).encode() for name in package.FILES}
        data=package.package_bytes('a'*40,files)
        self.assertEqual(data,package.package_bytes('a'*40,files))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual(set(archive.namelist()),set(package.FILES)|{'manifest.json'})
            self.assertFalse(manifest['http_listener_included'])
            self.assertFalse(manifest['activated'])
            for name,value in files.items():
                self.assertEqual(manifest['files'][name],hashlib.sha256(value).hexdigest())
            self.assertIn('scripts/run_face_worker.py',archive.namelist())
            self.assertIn('backend/app/access/face_jobs.py',archive.namelist())
            for forbidden in ('main','tasks','config','dependencies'):
                self.assertNotIn('backend/app/'+forbidden+'.py',archive.namelist())
            self.assertFalse(any('.env' in name or '/migrations/' in name for name in archive.namelist()))

    def test_extra_or_missing_source_refused(self):
        files={name:b'x' for name in package.FILES}
        with self.assertRaises(ValueError):package.package_bytes('a'*40,{**files,'.env':b'never include'})
        files.pop(next(iter(files)))
        with self.assertRaises(ValueError):package.package_bytes('a'*40,files)

    def test_floating_commit_symlink_and_oversize_refused(self):
        with self.assertRaises(ValueError):package.source_files('HEAD')
        with patch.object(package,'git',side_effect=[b'commit',b'120000 blob abc\tbackend/app/tasks.py\0']):
            with self.assertRaises(ValueError):package.source_files('a'*40)
        rows=b'\0'.join(('100644 blob abc\t'+name).encode() for name in package.FILES)
        with patch.object(package,'git',side_effect=[b'commit',rows,*([b'999999']*len(package.FILES))]):
            with self.assertRaises(ValueError):package.source_files('a'*40)
