#!/usr/bin/env python3
"""Explicit independent v2 TV catalog launcher; no legacy/protected app imports."""
import argparse
import json
from pathlib import Path
import sys

from home_feed_app import load_config
from app.home_catalog import Publication, create_home_catalog


def main(argv=None, server_run=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-publication', action='store_true')
    mode.add_argument('--serve', action='store_true')
    args = parser.parse_args(argv)
    try:
        # Launcher config version stays 1; control/catalog protocol is version 2.
        config, options = load_config(args.config)
        publication = Publication(config).load()
    except Exception:
        print('Invalid or disabled TV catalog publication/configuration', file=sys.stderr)
        return 2
    if args.check_publication:
        print(json.dumps({'publication_metadata': 'valid', 'version': 2,
            'revision': publication['revision'], 'assets': len(publication['assets']),
            'media_checked': False, 'certificate_checked': False, 'listener_started': False}))
    else:
        if server_run is None:
            import uvicorn
            server_run = uvicorn.run
        server_run(create_home_catalog(config), **options)
    return 0


if __name__ == '__main__': raise SystemExit(main())
