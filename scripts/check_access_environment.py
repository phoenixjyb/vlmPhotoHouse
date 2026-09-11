#!/usr/bin/env python3
"""Offline dependency/KDF/SQLite/TLS prerequisite check, not deployment approval.

Reads the selected checked-in lock and installed distribution metadata. Never imports
PhotoHouse, discovers configuration, opens a real database, loads keys, or listens.
Use an isolated CPython 3.12 venv (-I); macOS is explicitly a local-test target only.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sqlite3
import ssl
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = r'[a-z0-9]+(?:[-_.][a-z0-9]+)*'
PIN = re.compile(rf'({NAME})==([0-9]+(?:\.[0-9]+)+)((?:\s+--hash=sha256:[0-9a-f]{{64}})+)')


def canonical(name):
    return re.sub(r'[-_.]+', '-', name.lower())


def parse_lock(data):
    """Deliberately narrow format: exact stable pins and SHA256 hashes only."""
    if len(data) > 256 * 1024:
        raise ValueError('Lock too large')
    lines = [line.strip() for line in data.decode('ascii').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    records, pending = {}, ''
    for line in lines:
        continued = line.endswith('\\')
        pending += ' ' + (line[:-1].rstrip() if continued else line)
        if continued:
            continue
        match = PIN.fullmatch(pending.strip())
        if not match or canonical(match[1]) in records:
            raise ValueError('Invalid or duplicate locked dependency')
        records[canonical(match[1])] = match[2]
        pending = ''
    if pending or not records:
        raise ValueError('Incomplete lock')
    return records


def inspect_inventory(expected, installed, *, prefix, base_prefix, implementation,
                      python_version, system, machine, bits, isolated, target):
    """Pure checks; installed entries are (name, version, installation directory)."""
    issues = []
    if prefix == base_prefix or not isolated:
        issues.append('isolated_venv_required')
    if implementation != 'CPython' or not ((3, 12, 10) <= python_version < (3, 13, 0)):
        issues.append('cpython_3_12_10_or_newer_patch_required')
    supported = ((system == 'Windows' and machine.lower() in ('amd64', 'x86_64'))
                 if target == 'windows-amd64' else
                 (system == 'Darwin' and machine.lower() == 'arm64'))
    if not supported or bits != 64:
        issues.append('target_platform_mismatch')
    found = {}
    for name, version, location in installed:
        if not isinstance(name, str) or not re.fullmatch(NAME, name.lower()):
            issues.append('invalid_distribution_metadata')
            continue
        name = canonical(name)
        if name in found:
            issues.append('duplicate_distribution:' + name)
        found[name] = version
        if not Path(location).resolve().is_relative_to(Path(prefix).resolve()):
            issues.append('distribution_outside_venv:' + name)
    # pip is optional venv bootstrap tooling; its version is not a runtime dependency.
    for name in sorted(set(found) - set(expected) - {'pip'}):
        issues.append('unexpected_distribution:' + name)
    for name, version in expected.items():
        if name not in found:
            issues.append('missing_distribution:' + name)
        elif found[name] != version:
            issues.append('version_mismatch:' + name)
    return issues


def capability_checks():
    # RFC 7914 section 12 known-answer vector, plus the actual application's KDF cost.
    known = hashlib.scrypt(b'', salt=b'', n=16, r=1, p=1, dklen=64)
    if known.hex() != ('77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442'
                       'fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906'):
        raise ValueError('KDF known-answer mismatch')
    derived = hashlib.scrypt(b'synthetic-runtime-check', salt=b'\0' * 16,
                             n=2**17, r=8, p=1, maxmem=256*1024*1024, dklen=32)
    if len(derived) != 32:
        raise ValueError('KDF cost unsupported')
    with sqlite3.connect(':memory:') as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE child(id INTEGER REFERENCES parent(id))')
        try:
            db.execute('INSERT INTO child VALUES(1)')
        except sqlite3.IntegrityError:
            pass
        else:
            raise ValueError('Foreign keys not enforced')
    if not ssl.HAS_TLSv1_2:
        raise ValueError('TLS 1.2 unavailable')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return {'scrypt_known_answer': True, 'scrypt_application_cost': True,
            'sqlite_foreign_keys': True, 'tls_1_2_context': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--target', choices=('windows-amd64', 'macos-arm64-test'), required=True)
    parser.add_argument('--profile', choices=('runtime', 'test'), default='runtime')
    args = parser.parse_args(argv)
    suffix = '-test' if args.profile == 'test' else ''
    result = {'environment_check': 'refused', 'target': args.target, 'profile': args.profile,
              'deployment_approved': False, 'windows_execution_verified': False,
              'listener_started': False, 'real_database_accessed': False,
              'certificate_checked': False, 'installed_wheel_bytes_verified': False}
    try:
        data = (ROOT / 'backend' / f'requirements-access{suffix}.lock').read_bytes()
        expected = parse_lock(data)
        installed = [(d.metadata['Name'], d.version, str(d.locate_file('')))
                     for d in importlib.metadata.distributions()]
        issues = inspect_inventory(expected, installed, prefix=sys.prefix,
            base_prefix=sys.base_prefix, implementation=platform.python_implementation(),
            python_version=tuple(sys.version_info[:3]), system=platform.system(),
            machine=platform.machine(), bits=struct.calcsize('P') * 8,
            isolated=bool(sys.flags.isolated), target=args.target)
        result.update(lock_sha256=hashlib.sha256(data).hexdigest(), issues=issues)
        if not issues:
            result.update(capability_checks())
            result.update(environment_check='pass', packages=len(expected),
                python=platform.python_version(), sqlite=sqlite3.sqlite_version,
                openssl=ssl.OPENSSL_VERSION,
                windows_execution_verified=(args.target == 'windows-amd64'))
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        result['issues'] = ['environment_probe_failed']
    print(json.dumps(result, sort_keys=True))
    return 0 if result['environment_check'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
