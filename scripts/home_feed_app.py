#!/usr/bin/env python3
"""Explicit independent home-feed TLS launcher. Never start from ambient defaults."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.home_feed import Configuration, bounded_read, direct_path, unique


def load_config(path):
    value = json.loads(bounded_read(path,65536),object_pairs_hook=unique)
    if type(value) is not dict or set(value) != {'version','manifest','media_root','origin',
            'allowed_networks','bind_host','port','tls_certificate','tls_private_key'}:
        raise ValueError()
    if type(value['version']) is not int or value['version'] != 1: raise ValueError()
    if type(value['allowed_networks']) is not list: raise ValueError()
    config = Configuration(Path(value['manifest']),Path(value['media_root']),value['origin'],tuple(value['allowed_networks']))
    import ipaddress
    from app.home_feed import PRIVATE
    address = ipaddress.ip_address(value['bind_host'])
    if address.version != 4 or not any(address in network for network in PRIVATE) or str(address) != value['bind_host']:
        raise ValueError()
    if type(value['port']) is not int or not 1 <= value['port'] <= 65535 or value['port'] != (urlsplit(config.origin).port or 443):
        raise ValueError()
    certificate,key = direct_path(Path(value['tls_certificate'])), direct_path(Path(value['tls_private_key']))
    files = (path,config.manifest,certificate,key)
    if len(set(files)) != len(files) or any(p.is_relative_to(config.media_root) for p in files): raise ValueError()
    options = dict(host=value['bind_host'],port=value['port'],ssl_certfile=str(certificate),ssl_keyfile=str(key),
        workers=1,loop='asyncio',http='h11',ws='none',reload=False,proxy_headers=False,
        forwarded_allow_ips='',access_log=False,server_header=False,env_file=None,
        limit_concurrency=16,h11_max_incomplete_event_size=8192,timeout_keep_alive=5,
        timeout_graceful_shutdown=10)
    return config,options


def serve(config,options,server_run=None):
    from app.home_feed import create_home_feed
    if server_run is None:
        import uvicorn
        server_run = uvicorn.run
    server_run(create_home_feed(config),**options)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-config',action='store_true');mode.add_argument('--serve',action='store_true')
    args=parser.parse_args(argv)
    try:
        config,options=load_config(args.config)
    except Exception:
        print('Invalid home feed configuration',file=sys.stderr);return 2
    if args.check_config:
        print(json.dumps({'configuration_syntax':'valid','manifest_checked':False,
            'media_checked':False,'certificate_checked':False,'listener_started':False}))
    else:
        serve(config,options)
    return 0


if __name__=='__main__': raise SystemExit(main())
