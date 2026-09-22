#!/usr/bin/env python3
"""Explicit creation of the bilingual library presets for an existing operator.

Default is read-only preview. --apply creates empty libraries owned only by the
named active operator; no account, original download grant or asset is created.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.access.library_organization import PRESETS, create_presets, labels
from app.access.runtime import ExistingDatabase
from app.access.service import AccessService, AccessDenied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--operator-account', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with ExistingDatabase(args.database, read_only=not args.apply)() as db:
        access = AccessService(db)
        with access._transaction(write=args.apply):
            if db.execute('''SELECT 1 FROM access_operators o JOIN access_accounts a ON a.id=o.account_id
                WHERE a.id=? AND a.state='active' ''', (args.operator_account,)).fetchone() is None:
                raise AccessDenied('Active operator required')
            if args.apply:
                result = create_presets(access, args.operator_account)
            else:
                result = dict(items=[dict(**labels(key), exists=db.execute(
                    'SELECT 1 FROM access_libraries WHERE id=?', (key,)).fetchone() is not None) for key in PRESETS])
        print(json.dumps(dict(applied=args.apply, **result), ensure_ascii=True))


if __name__ == '__main__':
    main()
