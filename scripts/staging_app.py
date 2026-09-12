#!/usr/bin/env python3
"""Explicit protected staging entry point; no discovery, provisioning or migration.

--check-config reads only the selected JSON configuration and validates its syntax.
--serve is a separate, deliberate operation that opens the selected TLS listener.
Importing this module never imports the application, opens storage or starts serving.
"""
import argparse
from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'format_version', 'database', 'web_origin', 'original_roots', 'derived_root',
          'bind_host', 'port', 'tls_certificate', 'tls_private_key'}
PRIVATE_NETWORKS = tuple(map(ipaddress.ip_network,
    ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10',
     '127.0.0.0/8', 'fc00::/7', '::1/128')))


class InvalidConfiguration(ValueError):
    def __init__(self):
        super().__init__('Invalid staging configuration')


def _path(value):
    if (type(value) is not str or not value or len(value) > 4096
            or any(ord(c) < 32 for c in value) or value.startswith(('//', '\\\\'))):
        raise InvalidConfiguration()
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts or str(path) != value
            or path == Path(path.anchor)):
        raise InvalidConfiguration()
    return path


@dataclass(frozen=True, repr=False)
class StagingConfiguration:
    database: Path
    web_origin: str
    original_roots: tuple[Path, ...]
    derived_root: Path
    bind_host: str
    port: int
    tls_certificate: Path
    tls_private_key: Path

    def __post_init__(self):
        try:
            if type(self.port) is not int or not 1 <= self.port <= 65535:
                raise InvalidConfiguration()
            if type(self.bind_host) is not str or '%' in self.bind_host:
                raise InvalidConfiguration()
            address = ipaddress.ip_address(self.bind_host)
            if str(address) != self.bind_host or not any(address in net for net in PRIVATE_NETWORKS):
                raise InvalidConfiguration()
            if type(self.web_origin) is not str or len(self.web_origin) > 512:
                raise InvalidConfiguration()
            origin = urlsplit(self.web_origin)
            host = origin.hostname or ''
            labels = host.split('.')
            if (len(host) > 253 or len(labels) < 2 or any(not re.fullmatch(
                    r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)
                    or re.fullmatch(r'[0-9.]+', host)):
                raise InvalidConfiguration()
            canonical = 'https://' + host + (f':{self.port}' if self.port != 443 else '')
            if self.web_origin != canonical:
                raise InvalidConfiguration()
            if type(self.original_roots) is not tuple or not 1 <= len(self.original_roots) <= 8:
                raise InvalidConfiguration()
            media = (*self.original_roots, self.derived_root)
            files = (self.database, self.tls_certificate, self.tls_private_key)
            for path in (*media, *files):
                if not isinstance(path, Path) or _path(str(path)) != path:
                    raise InvalidConfiguration()
            if len(set(files)) != len(files):
                raise InvalidConfiguration()
            if any(left.is_relative_to(right) or right.is_relative_to(left)
                   for i, left in enumerate(media) for right in media[i+1:]):
                raise InvalidConfiguration()
            if any(file.is_relative_to(root) or root.is_relative_to(file)
                   for file in files for root in media):
                raise InvalidConfiguration()
        except (TypeError, ValueError):
            raise InvalidConfiguration() from None

    def build_app(self):
        # Deliberate source root; no .env, legacy config or model entry point.
        sys.path.insert(0, str(ROOT/'backend'))
        from app.access.runtime import RuntimeConfiguration
        return RuntimeConfiguration(database=self.database, web_origin=self.web_origin,
            original_roots=self.original_roots, derived_root=self.derived_root).build_app()

    def server_options(self):
        return dict(host=self.bind_host, port=self.port, ssl_certfile=str(self.tls_certificate),
            ssl_keyfile=str(self.tls_private_key), workers=1, loop='asyncio', http='h11',
            ws='none', reload=False, proxy_headers=False, forwarded_allow_ips='',
            access_log=False, server_header=False, env_file=None, root_path='',
            limit_concurrency=16, timeout_keep_alive=5, timeout_graceful_shutdown=10,
            h11_max_incomplete_event_size=8192, log_level='warning')


def parse_configuration(value):
    try:
        if (type(value) is not dict or set(value) != FIELDS
                or type(value['format_version']) is not int or value['format_version'] != 1
                or type(value['original_roots']) is not list):
            raise InvalidConfiguration()
        return StagingConfiguration(database=_path(value['database']), web_origin=value['web_origin'],
            original_roots=tuple(_path(p) for p in value['original_roots']),
            derived_root=_path(value['derived_root']), bind_host=value['bind_host'], port=value['port'],
            tls_certificate=_path(value['tls_certificate']), tls_private_key=_path(value['tls_private_key']))
    except (TypeError, ValueError, KeyError):
        raise InvalidConfiguration() from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidConfiguration()
        result[key] = value
    return result


def load_configuration(path):
    try:
        path = _path(str(path))
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
            raise InvalidConfiguration()
        with path.open('rb') as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            raise InvalidConfiguration()
        config = parse_configuration(json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object))
        # A config file must not be reachable as an original or cached image.
        if any(path.is_relative_to(root) for root in (*config.original_roots, config.derived_root)):
            raise InvalidConfiguration()
        if path in (config.database, config.tls_certificate, config.tls_private_key):
            raise InvalidConfiguration()
        return config
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise InvalidConfiguration() from None


def serve(config, *, server_run=None):
    app = config.build_app()
    if server_run is None:
        import uvicorn
        server_run = uvicorn.run
    server_run(app, **config.server_options())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-config', action='store_true')
    mode.add_argument('--serve', action='store_true')
    args = parser.parse_args(argv)
    try:
        config = load_configuration(args.config)
        if args.check_config:
            print(json.dumps({'configuration_syntax': 'valid', 'storage_checked': False,
                'certificate_checked': False, 'network_checked': False, 'listener_started': False}))
        else:
            serve(config)
        return 0
    except InvalidConfiguration:
        print('Invalid staging configuration', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
