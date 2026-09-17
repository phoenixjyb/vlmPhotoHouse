"""Synthetic coverage for the staging configuration contract.

This is the only place a deployment's roots are declared, and it is deliberately strict: the
accepted field set is exact, every path must be absolute and canonical, and no two roots may
overlap. The incoming root is the one optional field, and it exists precisely so that a
configuration written before member upload existed keeps loading.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import staging_app as s


def base():
    return {
        'format_version': 1,
        'database': '/synthetic/databases/metadata.sqlite',
        'web_origin': 'https://photohouse.test:8443',
        'original_roots': ['/synthetic/01_INCOMING'],
        'derived_root': '/synthetic/VLM_DATA/derived',
        'bind_host': '100.98.1.2',
        'port': 8443,
        'tls_certificate': '/synthetic/tls/server.crt',
        'tls_private_key': '/synthetic/tls/server.key',
    }


class StagingConfigurationTests(unittest.TestCase):
    def test_a_configuration_written_before_upload_still_loads(self):
        configuration = s.parse_configuration(base())
        self.assertIsNone(configuration.incoming_root)
        self.assertEqual(configuration.original_roots, (Path('/synthetic/01_INCOMING'),))

    def test_the_incoming_root_is_optional_and_accepted_when_present(self):
        configuration = s.parse_configuration(dict(base(), incoming_root='/synthetic/00_MEMBER_UPLOADS'))
        self.assertEqual(configuration.incoming_root, Path('/synthetic/00_MEMBER_UPLOADS'))

    def test_an_incoming_root_overlapping_anything_the_service_owns_is_refused(self):
        """Overlapping a media root would put unaccepted bytes where the media routes serve."""
        for bad in ('/synthetic/01_INCOMING',
                    '/synthetic/01_INCOMING/_member_uploads',
                    '/synthetic/VLM_DATA/derived/incoming',
                    '/synthetic',
                    '/synthetic/databases/metadata.sqlite',
                    'relative/path',
                    '/synthetic/00_MEMBER_UPLOADS/'):
            with self.subTest(incoming_root=bad):
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(dict(base(), incoming_root=bad))

    def test_the_optional_field_does_not_loosen_the_accepted_set(self):
        for extra in ('surprise', 'incoming', 'upload_root'):
            with self.subTest(extra=extra):
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(dict(base(), **{extra: '/synthetic/x'}))

    def test_the_required_fields_are_still_required(self):
        for missing in sorted(s.FIELDS):
            with self.subTest(missing=missing):
                value = base()
                value.pop(missing)
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(value)

    def test_the_pre_existing_overlap_rules_are_unchanged(self):
        for key, bad in (('derived_root', '/synthetic/01_INCOMING/derived'),
                         ('database', '/synthetic/01_INCOMING/metadata.sqlite'),
                         ('original_roots', ['/synthetic/VLM_DATA/derived'])):
            with self.subTest(key=key):
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(dict(base(), **{key: bad}))
