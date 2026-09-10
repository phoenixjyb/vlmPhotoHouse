#!/usr/bin/env python3
"""Offline owner/asset provisioning for an independently authorized local operator.

Explicit existing database, private request/plan files, separate backup, exact
reviewed digest and audit references only. No service control, migration, backup
creation, restored-access reopening, environment discovery or HTTP interface.
"""
import argparse
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_JSON = 2_000_000


class OperatorError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unexpected arguments, including accidental secrets.
        raise OperatorError('Invalid operator command')


def selected_path(value):
    if not isinstance(value, (str, Path)):
        raise OperatorError('Invalid path')
    raw = str(value)
    path = Path(raw)
    if (not path.is_absolute() or path == Path(path.anchor) or '..' in path.parts
            or raw != str(path) or raw.startswith(('//', '\\\\')) or len(raw) > 4096
            or any(ord(c) < 32 for c in raw)):
        raise OperatorError('Invalid path')
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OperatorError('Duplicate JSON key')
        result[key] = value
    return result


def invalid_constant(_):
    raise OperatorError('Invalid JSON number')


def read_json(path):
    path = selected_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or path.resolve(strict=True) != path:
        raise OperatorError('Direct regular input required')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise OperatorError('Input changed')
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise OperatorError('Input too large')
    result = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if type(result) is not dict:
        raise OperatorError('JSON object required')
    return result


def write_new_plan(path, envelope):
    path = selected_path(path)
    if path.parent.resolve(strict=True) != path.parent:
        raise OperatorError('Direct output directory required')
    encoded = json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False).encode() + b'\n'
    if len(encoded) > MAX_JSON:
        raise OperatorError('Plan too large')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    # Never overwrite an existing file. Failed writes may leave an incomplete
    # private artifact; it cannot pass sealed-plan validation or be reused here.
    with os.fdopen(os.open(path, flags, 0o600), 'wb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def parser():
    result = Parser(description=__doc__)
    commands = result.add_subparsers(dest='command', required=True)
    for name in ('plan-owner', 'plan-assets', 'validate', 'review', 'apply', 'receipt'):
        command = commands.add_parser(name)
        command.add_argument('--database', required=True, type=Path)
        if name.startswith('plan-'):
            command.add_argument('--request', required=True, type=Path)
            command.add_argument('--out', required=True, type=Path)
        elif name == 'receipt':
            command.add_argument('--plan-id', required=True)
            command.add_argument('--reviewed-plan-digest', required=True)
        else:
            command.add_argument('--plan', required=True, type=Path)
            if name in ('review', 'apply'):
                command.add_argument('--backup', required=True, type=Path)
                command.add_argument('--reviewed-plan-digest', required=True)
                command.add_argument('--authority-reference', required=True)
                command.add_argument('--restore-reference', required=True)
                if name == 'apply':
                    command.add_argument('--review-digest', required=True)
    return result


def execute(args, *, clock=time.time):
    # These modules do not discover storage or import legacy settings/models.
    sys.path.insert(0, str(ROOT/'backend'))
    from app.access.runtime import ExistingDatabase
    from app.access.provisioning import ProvisioningPlanner
    from app.access.provisioning_apply import plan_digest, review_backup, apply_reviewed
    database = selected_path(args.database)
    if args.command.startswith('plan-'):
        request = read_json(args.request)
        expected = ({'phone_login', 'library_id'} if args.command == 'plan-owner'
                    else {'library_id', 'operator_account_id', 'asset_ids'})
        if set(request) != expected:
            raise OperatorError('Unexpected request fields')
        with ExistingDatabase(database, read_only=True)() as connection:
            planner = ProvisioningPlanner(connection, clock=clock)
            envelope = (planner.owner(phone=request['phone_login'], library_id=request['library_id'])
                if args.command == 'plan-owner' else planner.assets(**request))
        write_new_plan(args.out, envelope)
        return {'applied': False, 'plan_id': envelope['plan']['plan_id'],
                'operation': envelope['plan']['operation'], 'plan_digest': plan_digest(envelope)}
    if args.command == 'receipt':
        if (str(uuid.UUID(args.plan_id)) != args.plan_id
                or not re.fullmatch('[0-9a-f]{64}', args.reviewed_plan_digest)):
            raise OperatorError('Exact receipt identity required')
        with ExistingDatabase(database, read_only=True)() as connection:
            row = connection.execute('''SELECT receipt FROM access_provisioning_receipts
                WHERE plan_id=? AND plan_digest=?''', (args.plan_id, args.reviewed_plan_digest)).fetchone()
        if row is None:
            return {'applied': False, 'receipt_found': False}
        receipt = json.loads(row[0])
        return receipt_summary(receipt) | {'receipt_found': True}
    envelope = read_json(args.plan)
    if args.command == 'validate':
        with ExistingDatabase(database, read_only=True)() as connection:
            result = ProvisioningPlanner(connection, clock=clock).validate(envelope)
        return result | {'plan_digest': plan_digest(envelope)}
    # A saved review is never deserialized. Both commands construct a fresh local
    # review; only the distinct apply command can call the write service.
    review = review_backup(database=database, backup=selected_path(args.backup), envelope=envelope,
        reviewed_plan_digest=args.reviewed_plan_digest, authority_reference=args.authority_reference,
        restore_reference=args.restore_reference, clock=clock)
    if args.command == 'review':
        return {'backup_reviewed': True, 'applied': False, 'plan_id': envelope['plan']['plan_id'],
                'operation': envelope['plan']['operation'], 'plan_digest': review.plan_digest,
                'review_digest': review_digest(review),
                'reviewed_effects': envelope['plan']['expected']}
    if args.command != 'apply':
        raise OperatorError('Unknown operation')
    if (not re.fullmatch('[0-9a-f]{64}', args.review_digest)
            or not hmac.compare_digest(args.review_digest, review_digest(review))):
        raise OperatorError('Review changed; repeat explicit review')
    return receipt_summary(apply_reviewed(envelope, review=review, clock=clock))


def review_digest(review):
    # Cross-command acknowledgement binds both exact files, all SQLite state and
    # review references. It is not authority, nor a serialized ApplyReview object.
    value = {'database':str(review.database), 'database_identity':review.database_identity,
        'backup':str(review.backup), 'backup_identity':review.backup_identity,
        'snapshot_digest':review.snapshot_digest, 'plan_digest':review.plan_digest,
        'authority_reference':review.authority_reference, 'restore_reference':review.restore_reference}
    encoded = json.dumps(value,sort_keys=True,separators=(',', ':'),ensure_ascii=True).encode()
    return hashlib.sha256(b'PhotoHouse operator review v1\0'+encoded).hexdigest()


def receipt_summary(receipt):
    # No phone, password, invitation, token, media path, raw key or SQL dump.
    return {key: receipt[key] for key in ('plan_id', 'plan_digest', 'operation', 'actor_account_id')} | {'applied': True}


def main(argv=None, *, clock=time.time):
    applied = False
    try:
        args = parser().parse_args(argv)
        result = execute(args, clock=clock)
        applied = result.get('applied', False)
        print(json.dumps(result, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Operator command interrupted; check the durable receipt before any retry.', file=sys.stderr)
        return 130
    except (ValueError, OSError, RuntimeError, sqlite3.Error, getpass.GetPassWarning,
            EOFError, KeyError, TypeError, RecursionError):
        if applied:
            print('Result output failed after application; query the durable receipt before retrying.', file=sys.stderr)
            return 3
        print('Operator command refused or interrupted; check the durable receipt before retrying apply.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
