"""Fixed source-selection and deterministic archive tests; no Git/network needed."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import build_staging_package as package


class StagingPackageTests(unittest.TestCase):
    def test_archive_is_deterministic_complete_and_contains_no_private_discovery(self):
        files={name:('synthetic source '+name).encode() for name in package.FILES}
        first=package.package_bytes('a'*40,files)
        self.assertEqual(first,package.package_bytes('a'*40,dict(reversed(list(files.items())))))
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual(set(archive.namelist()),set(package.FILES)|{'manifest.json'})
            manifest=json.loads(archive.read('manifest.json'))
            self.assertFalse(manifest['dependencies_included'] or manifest['private_configuration_included'])
            for name in package.FILES:
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),manifest['files'][name])
            self.assertNotIn('backend/app/config.py',archive.namelist())
            self.assertNotIn('backend/app/legacy_main.py',archive.namelist())
            self.assertFalse(any(name.endswith(('.sqlite','.pem','.env','.pt')) for name in archive.namelist()))

    def test_extra_missing_or_traversal_files_are_refused(self):
        files={name:b'synthetic' for name in package.FILES}
        for changed in (files|{'../private.env':b'secret'}, files|{'.env':b'secret'}, {}):
            with self.assertRaises(ValueError): package.package_bytes('a'*40,changed)

    def test_moving_refs_missing_source_and_symlink_git_objects_are_refused(self):
        with patch.object(package,'git') as git:
            with self.assertRaises(ValueError): package.source_files('HEAD')
            git.assert_not_called()
        with patch.object(package,'git',side_effect=[b'commit\n',b'']):
            with self.assertRaises(ValueError): package.source_files('a'*40)
        with patch.object(package,'git',side_effect=[b'commit\n',
                b'120000 blob '+b'b'*40+b'\tbackend/app/main.py\0']):
            with self.assertRaises(ValueError): package.source_files('a'*40)


if __name__=='__main__': unittest.main()
