#!/usr/bin/env python3
"""Prepare named geographic regions from recorded GPS in one protected library.

Offline, read-only source access. Explicit operator-supplied rectangles name
places; nothing reverse-geocodes or guesses a missing coordinate. Output is a
new reviewed discovery artifact, never a live configuration or TV publication.
Use --audit alone to report aggregate GPS coverage without writing an artifact.
"""
import argparse
from contextlib import closing
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
import time

import prepare_access_discovery_index as producer
from app.access import discovery as d
from app.access.discovery_provider import ProjectedIndex, RefreshingPlaceIndex, RegionRule, ReviewedPlace, NamedPlace

MAX_REGIONS = 128
ENABLED = ('date', 'locations', 'media')


def regions(value):
    if type(value) is not dict or set(value) != {'version', 'places'} or type(value['version']) is not int or value['version'] != 1:
        raise producer.Refused('Invalid region document')
    entries = value['places']
    if type(entries) is not list or not 1 <= len(entries) <= MAX_REGIONS:
        raise producer.Refused('Invalid region count')
    seen = set()
    for item in entries:
        if type(item) is not dict or set(item) not in ({'id', 'label', 'south', 'west', 'north', 'east'}, {'id', 'label', 'aliases', 'south', 'west', 'north', 'east'}):
            raise producer.Refused('Invalid region')
        d.identifier(item['id']); d.text(item['label'], 256)
        if 'aliases' in item:
            aliases=item['aliases']
            if type(aliases) is not list or len(aliases)>8: raise producer.Refused('Invalid aliases')
            for alias in aliases: d.text(alias,128)
            if len(set(aliases))!=len(aliases): raise producer.Refused('Duplicate aliases')
        if item['id'] in seen:
            raise producer.Refused('Duplicate region')
        seen.add(item['id'])
        for key in ('south', 'west', 'north', 'east'):
            v = item[key]
            limit = 90 if key in ('south', 'north') else 180
            if type(v) not in (int, float) or not math.isfinite(v) or not -limit <= v <= limit:
                raise producer.Refused('Invalid bounds')
        # West > east denotes a region crossing the antimeridian.
        d.validate_region_rule(rule_for(item))
    return tuple(entries)


def rule_for(region):
    return RegionRule(region['id'], region['south'], region['west'], region['north'], region['east'])


def contains(region, lat, lon):
    return d.region_contains(rule_for(region), lat, lon)


def derive(db, library, revision, definitions=(), *, audit=False, refresh=False):
    budget = d.ReadBudget()
    with budget.attempt(db, lambda: False) as (check, read):
        source = d.projected_source(library, read, ENABLED)
        scope = tuple(str(row[0]) for row in source['assets'])
        pairs = []; located = 0; matched = set()
        for aid, lat, lon in source['coordinates']:
            check()
            if lat is None or lon is None:
                continue
            located += 1
            if audit:
                continue
            for region in definitions:
                if contains(region, lat, lon):
                    pairs.append((str(aid), region['id'])); matched.add(aid)
                    if len(pairs) > budget.rows:
                        raise producer.Refused('Too many region associations')
        receipt = {'catalog_assets': len(scope), 'with_recorded_gps': located,
                   'without_valid_gps': len(scope) - located}
        if audit:
            return None, receipt
        if not scope:
            raise producer.Refused('No visible assets')
        constructor = RefreshingPlaceIndex if refresh else ProjectedIndex
        extra = {'region_rules': tuple(rule_for(r) for r in definitions)} if refresh else {}
        index = constructor(**extra, library_id=library, revision=revision, scope_ids=scope,
            indexed_ids=scope, source_digest=d.digest(source), enabled=ENABLED,
            places=tuple(NamedPlace(library, r['id'], r['label'], tuple(r['aliases'])) if 'aliases' in r else ReviewedPlace(library, r['id'], r['label']) for r in definitions),
            regions=tuple(pairs))
        receipt.update({'with_named_place': len(matched),
                        'gps_outside_named_places': located - len(matched)})
        d.validate(index, library, budget.rows)
        if len(d.packed(asdict(index))) > budget.index_bytes:
            raise producer.Refused('Index too large')
        check()
        return index, receipt


def main(argv=None):
    parser = producer.Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--refresh-current-library', action='store_true',
                        help='Explicitly apply these region rules to future active assets in this protected library')
    parser.add_argument('--regions', type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--out', type=Path)
    try:
        args = parser.parse_args(argv)
        library = producer.library(args.library)
        if args.audit:
            if args.refresh_current_library or any(v is not None for v in (args.regions, args.revision, args.out)):
                raise producer.Refused('Audit writes no artifact')
            definitions, revision = (), '1'
        else:
            if any(v is None for v in (args.regions, args.revision, args.out)):
                raise producer.Refused('Explicit regions, revision and output required')
            definitions = regions(producer.review_json(args.regions))
            revision = producer.revision(args.revision)
        with closing(producer.open_read_only(args.database, time.monotonic())) as db:
            index, receipt = derive(db, library, revision, definitions, audit=args.audit, refresh=args.refresh_current_library)
        if index is not None:
            payload = d.packed(asdict(index))
            receipt.update({'output_sha256': producer.write_new(args.out, payload),
                            'output_bytes': len(payload), 'revision': revision,
                            'source_digest': index.source_digest})
        print(json.dumps({'command': 'prepare-access-places', 'completed': True,
                          'existing_database_modified': False, 'audit_only': args.audit,
                          'refresh_current_library': args.refresh_current_library,
                          **receipt}, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception:
        print('Place preparation refused; inspect any new output before reuse.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
