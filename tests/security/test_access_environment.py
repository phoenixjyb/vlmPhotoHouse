"""Synthetic prerequisite refusals; no application, real storage, or network."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import check_access_environment as check


class AccessEnvironmentTests(unittest.TestCase):
    def test_hash_locked_format_rejects_unpinned_includes_urls_markers_and_duplicates(self):
        good = b'fastapi==0.135.2 \\\n  --hash=sha256:' + b'a'*64 + b'\n'
        self.assertEqual(check.parse_lock(good), {'fastapi': '0.135.2'})
        for bad in (b'', b'fastapi>=0.1', b'-r private.txt', b'--index-url https://other.test',
                    good+good, good.replace(b'sha256', b'md5'), good+b'\\',
                    good.replace(b'0.135.2', b'0.135.2;sys_platform=="win32"'),
                    b'a'*262145):
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError):
                check.parse_lock(bad)

    def inventory(self, **changes):
        prefix=str(Path('/synthetic-venv').resolve())
        args=dict(expected={'fastapi':'0.135.2'},
            installed=[('FastAPI','0.135.2',prefix)], prefix=prefix,
            base_prefix=str(Path('/synthetic-python').resolve()), implementation='CPython',
            python_version=(3,12,12), system='Windows', machine='AMD64', bits=64,
            isolated=True, target='windows-amd64')
        args.update(changes)
        return check.inspect_inventory(**args)

    def test_expected_environment_and_explicit_mac_test_target(self):
        self.assertEqual(self.inventory(), [])
        self.assertEqual(self.inventory(system='Darwin',machine='arm64',target='macos-arm64-test'), [])
        self.assertIn('target_platform_mismatch', self.inventory(system='Darwin',machine='arm64'))

    def test_wrong_interpreter_global_mode_and_architecture_refused(self):
        for change in ({'isolated':False}, {'python_version':(3,14,0)},
                       {'python_version':(3,12,9)}, {'implementation':'PyPy'},
                       {'bits':32}, {'machine':'ARM64'}, {'system':'Linux'}):
            self.assertTrue(self.inventory(**change), change)

    def test_missing_wrong_extra_duplicate_and_outside_distribution_refused(self):
        prefix=str(Path('/synthetic-venv').resolve())
        good=('fastapi','0.135.2',prefix)
        for installed in ([], [('fastapi','0.135.1',prefix)],
                          [good,('torch','2.0.0',prefix)], [good,good],
                          [('fastapi','0.135.2',str(Path('/other').resolve()))]):
            self.assertTrue(self.inventory(installed=installed), installed)
        self.assertEqual(self.inventory(installed=[good,('pip','26.2.1',prefix)]), [])

    def test_runtime_pins_are_identical_in_test_lock_and_no_worker_extras(self):
        runtime=check.parse_lock((check.ROOT/'backend/requirements-access.lock').read_bytes())
        test=check.parse_lock((check.ROOT/'backend/requirements-access-test.lock').read_bytes())
        self.assertTrue(runtime.items() <= test.items())
        self.assertEqual(set(test)-set(runtime), {'httpx','httpcore','certifi'})
        self.assertFalse(set(runtime) & {'torch','pillow','numpy','transformers','uvloop',
                                       'watchfiles','websockets','python-dotenv','httptools'})

    def test_real_stdlib_capabilities_need_no_network_or_disk_database(self):
        with (patch('socket.socket.bind',side_effect=AssertionError('listener')),
              patch('socket.socket.connect',side_effect=AssertionError('network'))):
            self.assertTrue(all(check.capability_checks().values()))

    def test_real_uvicorn_accepts_launcher_options_without_loading_or_listening(self):
        import uvicorn
        import staging_app
        config = SimpleNamespace(bind_host='127.0.0.1', port=8443,
            tls_certificate=Path('/synthetic/cert.pem'),
            tls_private_key=Path('/synthetic/key.pem'))
        with (patch('socket.socket.bind', side_effect=AssertionError('listener')),
              patch('socket.socket.connect', side_effect=AssertionError('network'))):
            server = uvicorn.Config('synthetic:app',
                **staging_app.StagingConfiguration.server_options(config))
        self.assertFalse(server.loaded)
        self.assertFalse(server.proxy_headers)
        self.assertFalse(server.access_log)
        self.assertEqual(server.ws, 'none')
