"""Synthetic configuration and mocked serving only; no listener or runtime data."""
from contextlib import redirect_stdout, redirect_stderr
import importlib
import inspect
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import staging_app


class StagingLauncherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='photohouse-staging-config-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.path = self.root/'synthetic-config.json'
        self.value = dict(format_version=1, database=str(self.root/'synthetic.sqlite'),
            web_origin='https://photohouse.test:18443', original_roots=[str(self.root/'originals')],
            derived_root=str(self.root/'derived'), bind_host='127.0.0.1', port=18443,
            tls_certificate=str(self.root/'synthetic-cert.pem'), tls_private_key=str(self.root/'synthetic-key.pem'))
        for target in ('socket.socket.bind', 'socket.socket.connect', 'subprocess.Popen',
                       'os.system', 'sqlite3.connect'):
            guard = patch(target, side_effect=AssertionError('External I/O forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def write(self, value=None):
        self.path.write_text(json.dumps(self.value if value is None else value))

    def test_check_mode_reads_config_only_and_prints_no_private_values(self):
        self.write()
        output = io.StringIO()
        with patch.object(staging_app, 'serve', side_effect=AssertionError('Serving forbidden')):
            with redirect_stdout(output):
                self.assertEqual(staging_app.main(['--config',str(self.path),'--check-config']), 0)
        self.assertEqual(json.loads(output.getvalue()), {'configuration_syntax':'valid',
            'storage_checked':False,'certificate_checked':False,'network_checked':False,'listener_started':False})
        self.assertEqual(list(self.root.iterdir()), [self.path])
        self.assertNotIn('photohouse.test', repr(staging_app.load_configuration(self.path)))

    def test_missing_mode_never_serves(self):
        self.write()
        with patch.object(staging_app, 'serve', side_effect=AssertionError('Serving forbidden')):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                staging_app.main(['--config',str(self.path)])
            self.assertEqual(result.exception.code, 2)

    def test_json_shape_unknown_keys_duplicates_and_invalid_values_are_refused(self):
        for value in (None, [], self.value|{'format_version':True}, self.value|{'format_version':2},
                      self.value|{'proxy_headers':True}, self.value|{'password':'private'},
                      self.value|{'original_roots':[]}, self.value|{'original_roots':'/private'}):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(staging_app.InvalidConfiguration):
                    staging_app.parse_configuration(value)
        self.write()
        self.path.write_text(self.path.read_text()[:-1]+',"port":18443}')
        with self.assertRaises(staging_app.InvalidConfiguration):
            staging_app.load_configuration(self.path)

    def test_canonical_https_origin_and_matching_listener_port_are_required(self):
        invalid = ('http://photohouse.test:18443', 'https://photohouse.test',
            'https://PHOTOHOUSE.test:18443', 'https://photohouse.test:18443/',
            'https://photohouse.test:18443?x=1', 'https://photohouse.test:18443#x',
            'https://user:secret@photohouse.test:18443', 'https://photohouse.test:18443\\x',
            ' https://photohouse.test:18443', 'https://photo_house.test:18443',
            'https://photohouse.test.:18443', 'https://127.0.0.1:18443',
            'https://photohouse.test:018443', 'https://photo\nhouse.test:18443')
        for origin in invalid:
            with self.subTest(origin=origin), self.assertRaises(staging_app.InvalidConfiguration):
                staging_app.parse_configuration(self.value|{'web_origin':origin})
        staging_app.parse_configuration(self.value|{'web_origin':'https://photohouse.test','port':443})
        with self.assertRaises(staging_app.InvalidConfiguration):
            staging_app.parse_configuration(self.value|{'web_origin':'https://photohouse.test:443','port':443})

    def test_bind_is_an_explicit_canonical_private_ip_without_zone_or_dns(self):
        for host in ('0.0.0.0','::','8.8.8.8','169.254.1.2','localhost','fe80::1%en0',
                     '::ffff:127.0.0.1','100.128.0.1','192.0.2.10'):
            with self.subTest(host=host), self.assertRaises(staging_app.InvalidConfiguration):
                staging_app.parse_configuration(self.value|{'bind_host':host})
        for host in ('10.0.0.1','172.16.0.1','192.168.0.1','100.64.0.1','::1','fd00::1'):
            self.assertEqual(staging_app.parse_configuration(self.value|{'bind_host':host}).bind_host, host)
        for port in (True,0,65536,'18443',18443.0):
            with self.assertRaises(staging_app.InvalidConfiguration):
                staging_app.parse_configuration(self.value|{'port':port})

    def test_paths_cannot_overlap_media_or_use_relative_network_or_parent_paths(self):
        for value in ('relative.sqlite','//server/share/private.sqlite','\\\\server\\share\\private.sqlite',
                      str(self.root/'..'/'elsewhere.sqlite'), '/', str(self.root/'bad\x00file')):
            with self.assertRaises(staging_app.InvalidConfiguration):
                staging_app.parse_configuration(self.value|{'database':value})
        for update in ({'database':str(self.root/'originals'/'data.sqlite')},
                       {'tls_private_key':str(self.root/'derived'/'key.pem')},
                       {'tls_certificate':self.value['tls_private_key']},
                       {'derived_root':str(self.root/'originals'/'nested')},
                       {'original_roots':self.value['original_roots']*2}):
            with self.assertRaises(staging_app.InvalidConfiguration):
                staging_app.parse_configuration(self.value|update)

    def test_config_file_must_be_small_regular_direct_and_outside_media(self):
        self.write()
        alias = self.root/'alias.json'; alias.symlink_to(self.path)
        for path in (alias,self.root,self.root/'missing.json'):
            with self.assertRaises(staging_app.InvalidConfiguration):
                staging_app.load_configuration(path)
        for data in (b'x'*65537, b'\xff', b'{}', b'{', b'['*2000+b']'*2000):
            self.path.write_bytes(data)
            with self.assertRaises(staging_app.InvalidConfiguration):
                staging_app.load_configuration(self.path)
        originals = self.root/'originals'; originals.mkdir()
        self.path = originals/'config.json'
        self.write()
        with self.assertRaises(staging_app.InvalidConfiguration):
            staging_app.load_configuration(self.path)
        self.path = self.root/'synthetic-config.json'
        self.write(self.value|{'database':str(self.path)})
        with self.assertRaises(staging_app.InvalidConfiguration):
            staging_app.load_configuration(self.path)

    def test_errors_are_sanitized_and_do_not_start_the_server(self):
        self.path.write_text('{"password":"never-print-this"}')
        output = io.StringIO()
        with redirect_stderr(output), patch.object(staging_app, 'serve') as server:
            self.assertEqual(staging_app.main(['--config',str(self.path),'--serve']), 2)
        server.assert_not_called()
        self.assertEqual(output.getvalue(), 'Invalid staging configuration\n')

    def test_import_and_config_ignore_ambient_runtime_and_proxy_environment(self):
        with patch.dict('os.environ', {'DATABASE_URL':'sqlite:///private-real.sqlite',
            'WEB_CONCURRENCY':'99','FORWARDED_ALLOW_IPS':'*','UVICORN_HOST':'0.0.0.0'}):
            importlib.reload(staging_app)
            self.write()
            config = staging_app.load_configuration(self.path)
            self.assertEqual(config.database, self.root/'synthetic.sqlite')
            self.assertEqual(config.server_options()['workers'], 1)
            self.assertFalse(config.server_options()['proxy_headers'])
            self.assertEqual(config.server_options()['forwarded_allow_ips'], '')

    def test_mocked_serve_constructs_only_explicit_protected_app_with_tls(self):
        config = staging_app.parse_configuration(self.value)
        server = Mock()
        staging_app.serve(config, server_run=server)
        server.assert_called_once()
        app = server.call_args.args[0]
        options = server.call_args.kwargs
        self.assertEqual(app.state.access_runtime.web_origin, self.value['web_origin'])
        self.assertEqual(app.state.access_runtime.connection_factory.path, config.database)
        self.assertEqual(app.state.media_runtime.original_roots, config.original_roots)
        self.assertEqual((options['ssl_certfile'],options['ssl_keyfile']),
                         (self.value['tls_certificate'],self.value['tls_private_key']))
        self.assertEqual((options['host'],options['port']), ('127.0.0.1',18443))
        self.assertEqual((options['loop'],options['http'],options['ws']), ('asyncio','h11','none'))
        self.assertFalse(options['access_log'] or options['proxy_headers'] or options['reload'])
        self.assertEqual(options['limit_concurrency'],16)
        self.assertIsNone(options['env_file'])
        # Verify options against the existing local library without starting it.
        import uvicorn
        inspect.signature(uvicorn.run).bind(app, **options)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
