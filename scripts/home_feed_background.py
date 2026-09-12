#!/usr/bin/env python3
"""Run an existing home-feed release with no console and bounded diagnostics.

Use pythonw.exe on Windows. This launcher does not install/start tasks, change
configuration or publications, or provide startup/retry behavior.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import logging
import logging.config
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time

LOG_BYTES = 1024 * 1024
LOG_BACKUPS = 3
RECORD_CHARS = 2048


class BoundedFormatter(logging.Formatter):
    def format(self, record):
        return super().format(record)[:RECORD_CHARS]


class DiagnosticHandler(RotatingFileHandler):
    """Never send logging I/O failures back into redirected stderr."""
    failed_records = 0

    def handleError(self, record):
        # A permission/full-disk failure must not recurse through DiagnosticStream
        # or create an unbounded fallback file. Drop and count the failed record.
        self.failed_records += 1


class DiagnosticStream:
    """No line accumulator: even a newline-free writer has bounded output."""
    encoding = 'utf-8'

    def __init__(self, level):
        self.level = level

    def write(self, value):
        if value.strip():
            logging.getLogger('home_feed.background').log(
                self.level, '%s', value[:RECORD_CHARS])
        return len(value)

    def flush(self):
        for handler in logging.getLogger().handlers:
            handler.flush()

    def isatty(self):
        return False


def configure_logging(directory):
    directory.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig({
        'version': 1, 'disable_existing_loggers': False,
        'formatters': {'bounded': {'()': BoundedFormatter,
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s'}},
        'handlers': {'bounded': {'()': DiagnosticHandler,
            'filename': str(directory / 'server.log'), 'maxBytes': LOG_BYTES,
            'backupCount': LOG_BACKUPS, 'encoding': 'utf-8', 'formatter': 'bounded'}},
        'root': {'handlers': ['bounded'], 'level': 'INFO'},
        'loggers': {name: {'handlers': [], 'propagate': True, 'level': 'INFO'}
            for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access')},
    })
    sys.stdout = DiagnosticStream(logging.INFO)
    sys.stderr = DiagnosticStream(logging.ERROR)


def console_window():
    if sys.platform != 'win32':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetConsoleWindow.restype = ctypes.c_void_p
    return int(kernel.GetConsoleWindow() or 0)


def serve_existing(source, kind, config, server_run=None):
    """Keep the release's validation, factory and all serving options."""
    scripts = source / 'scripts'
    sys.path.insert(0, str(scripts))
    entry = scripts / ('home_feed_app.py' if kind == 'v1' else 'home_catalog_app.py')
    spec = importlib.util.spec_from_file_location('_home_background_entry', entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if server_run is None:
        import uvicorn
        server_run = uvicorn.run

    def bounded_run(app, **options):
        # Fail closed if the existing release does not retain these invariants.
        if options.get('access_log') is not False or options.get('proxy_headers') is not False:
            raise ValueError('Unexpected serving policy')
        return server_run(app, **dict(options, log_config=None))

    if kind == 'v2':
        return module.main(['--config', str(config), '--serve'], server_run=bounded_run)
    configuration, options = module.load_config(config)
    module.serve(configuration, options, server_run=bounded_run)
    return 0


def write_receipt(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--kind', choices=('v1', 'v2'), required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--log-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    configure_logging(args.log_dir)
    window = console_window()
    receipt = {'pid': os.getpid(), 'parent_pid': os.getppid(),
        'started_at': time.time(), 'console_window': window, 'kind': args.kind,
        'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'log_max_bytes': LOG_BYTES, 'log_backups': LOG_BACKUPS,
        'state': 'starting'}
    path = args.log_dir / 'process.json'
    write_receipt(path, receipt)
    try:
        if window:
            raise RuntimeError('Use pythonw.exe; a console is attached')
        logging.info('Starting existing %s feed; pid=%s', args.kind, os.getpid())
        result = serve_existing(args.source_root, args.kind, args.config)
        receipt['exit_code'] = result
        return result
    except Exception:
        logging.exception('Home-feed process failed')
        receipt['exit_code'] = 1
        return 1
    finally:
        receipt.update(state='exited', finished_at=time.time())
        write_receipt(path, receipt)
        logging.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
