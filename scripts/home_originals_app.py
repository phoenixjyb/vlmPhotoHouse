#!/usr/bin/env python3
"""Explicit v3 launcher. Reuses reviewed TLS/LAN config; no implicit activation."""
import argparse
import json
from pathlib import Path
from home_feed_app import load_config
from app.home_catalog import Publication
from app.home_originals import SourceIndex, create_home_originals
from app.photo_delivery import PhotoCache


def main(argv=None,server_run=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--sources',type=Path,required=True);p.add_argument('--sources-sha256',required=True)
    p.add_argument('--source-root',type=Path,action='append',required=True)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--allow-originals',action='store_true')
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--check',action='store_true');mode.add_argument('--serve',action='store_true')
    a=p.parse_args(argv)
    try:
        config,options=load_config(a.config)
        sources=SourceIndex(Publication(config),a.sources,a.sources_sha256,a.source_root,originals_allowed=a.allow_originals)
        c=sources.load();cache=PhotoCache(a.cache)
        if a.check:
            print(json.dumps(dict(version=3,assets=len(c['assets']),indexed=len(sources.entries),originals_allowed=a.allow_originals,listener_started=False)))
        else:
            if server_run is None:
                import uvicorn
                server_run=uvicorn.run
            server_run(create_home_originals(config,sources,cache),**options)
        return 0
    except Exception:print('Invalid original delivery configuration');return 2
if __name__=='__main__':raise SystemExit(main())
