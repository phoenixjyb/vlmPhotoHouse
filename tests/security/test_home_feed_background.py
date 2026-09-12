"""Synthetic launcher checks: no listener, real configuration or media."""
import importlib.util
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('background', ROOT/'scripts/home_feed_background.py')
background = importlib.util.module_from_spec(spec)
spec.loader.exec_module(background)


class BackgroundTests(unittest.TestCase):
    def test_existing_launchers_keep_options_and_replace_only_logging(self):
        for kind in ('v1', 'v2'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source/'scripts').mkdir()
                options = dict(host='192.168.40.10', port=18444, access_log=False,
                    proxy_headers=False, workers=1, ws='none', ssl_keyfile='fixture-key')
                stub = f'OPTIONS={options!r}\n'
                stub += 'def load_config(path): return str(path), OPTIONS.copy()\n'
                stub += 'def serve(config, options, server_run): server_run(config, **options)\n'
                stub += 'def main(args, server_run): server_run(args[1], **OPTIONS); return 0\n'
                name = 'home_feed_app.py' if kind == 'v1' else 'home_catalog_app.py'
                (source/'scripts'/name).write_text(stub)
                calls = []
                old = sys.path[:]
                try:
                    result = background.serve_existing(source, kind, source/'config.json',
                        lambda app, **kw: calls.append((app, kw)))
                finally:
                    sys.path[:] = old
                self.assertEqual(result, 0)
                self.assertEqual(calls, [(str(source/'config.json'), dict(options, log_config=None))])

    def test_rejects_changed_access_logging_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory); (source/'scripts').mkdir()
            (source/'scripts/home_catalog_app.py').write_text(
                'def main(args, server_run): return server_run(None, access_log=True, proxy_headers=False)')
            old = sys.path[:]
            try:
                with self.assertRaisesRegex(ValueError, 'serving policy'):
                    background.serve_existing(source, 'v2', source/'config', lambda *a, **k: self.fail())
            finally:
                sys.path[:] = old

    def test_unicode_and_large_records_stay_within_rotation_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'server.log'
            handler = RotatingFileHandler(path, maxBytes=background.LOG_BYTES,
                backupCount=background.LOG_BACKUPS, encoding='utf-8')
            handler.setFormatter(background.BoundedFormatter('%(message)s'))
            record = logging.LogRecord('synthetic', logging.INFO, '', 0, '字'*100000, (), None)
            for _ in range(1000):
                handler.handle(record)
            handler.close()
            files = list(Path(directory).glob('server.log*'))
            self.assertEqual(len(files), 4)
            # RotatingFileHandler's threshold uses character length; retain a
            # conservative one-record UTF-8 allowance in the asserted bound.
            self.assertTrue(all(p.stat().st_size <= background.LOG_BYTES+8192 for p in files))

    def test_stream_does_not_accumulate_unterminated_output(self):
        stream = background.DiagnosticStream(logging.INFO)
        with patch.object(logging.Logger, 'log') as log:
            self.assertEqual(stream.write('x'*1000000), 1000000)
            self.assertEqual(len(log.call_args.args[2]), background.RECORD_CHARS)
        self.assertEqual(vars(stream), {'level': logging.INFO})

    def test_console_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config = root/'config.json'; config.write_text('{}')
            with patch.object(background, 'configure_logging'), patch.object(background, 'console_window', return_value=42), patch.object(background, 'serve_existing') as serve, patch.object(background.logging, 'exception'):
                result = background.main(['--source-root', str(root), '--kind', 'v1',
                    '--config', str(config), '--log-dir', str(root)])
                self.assertEqual(result, 1)
                serve.assert_not_called()
            self.assertIn('"state": "exited"', (root/'process.json').read_text())

    def test_pythonw_none_streams_have_file_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
                background.configure_logging(Path(directory))
                sys.stdout.write('synthetic stdout')
                sys.stderr.write('synthetic stderr')
                logging.getLogger('uvicorn.error').info('synthetic uvicorn')
                logging.shutdown()
            text = (Path(directory)/'server.log').read_text()
            for message in ('synthetic stdout', 'synthetic stderr', 'synthetic uvicorn'):
                self.assertIn(message, text)


if __name__ == '__main__':
    unittest.main()
