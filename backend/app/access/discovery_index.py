"""Strict loader for one operator-produced reviewed discovery index artifact.

The artifact is the file `scripts/prepare_access_discovery_index.py` writes: the
`asdict` of a `ReviewedIndex`, JSON with sorted keys and no whitespace. Loading it
reconstructs the same frozen dataclasses the service validates, so the service
consumes the operator's artifact rather than a parallel interpretation of it.

This loader approves nothing. It re-runs the service's own `validate` and the shared
index budget before any runtime exists, so an artifact the service would reject is
refused at load rather than at the first request. It has no directory, environment,
configuration or glob discovery: every artifact path is explicit and read-only.

Nothing here is wired into the application entry point's defaults. A deployment
supplies explicit paths; no path is ever inferred, and no index is ever derived.
"""
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import re
import stat

from . import discovery as d
from .discovery_provider import (MemoryIndexProvider, ProjectedIndex, RefreshingPlaceIndex, RegionRule, ReviewedFace, ReviewedIndex,
                                 ReviewedPerson, ReviewedPlace)
from .discovery_transport import DiscoveryRuntime

INDEX_KEYS = frozenset({'library_id', 'revision', 'scope_ids', 'indexed_ids', 'source_digest',
                        'people', 'pinned_ids', 'assignments', 'places', 'regions', 'enabled'})
PERSON_KEYS = frozenset({'library_id', 'id', 'label', 'aliases', 'allow_zero'})
FACE_KEYS = frozenset({'id', 'asset_id', 'person_id', 'source'})
PLACE_KEYS = frozenset({'library_id', 'id', 'label'})
IDENTIFIER = re.compile(r'[1-9][0-9]{0,18}')
DIGEST = re.compile('[0-9a-f]{64}')


class DiscoveryIndexRefused(RuntimeError):
    """The artifact is absent, malformed or not something the service would accept."""

    def __init__(self):
        super().__init__('Reviewed discovery index refused')


def direct(path):
    """Explicit, direct, non-aliased local file — the producer's own path discipline."""
    if (not path.is_absolute() or '..' in path.parts or path.anchor.startswith(('//', '\\\\'))
            or not path.parent.is_dir() or path.parent.resolve(strict=True) != path.parent):
        raise DiscoveryIndexRefused()
    return path


def text(value, maximum):
    if type(value) is not str:
        raise DiscoveryIndexRefused()
    try:
        if len(value.encode('utf-8')) > maximum:
            raise DiscoveryIndexRefused()
    except UnicodeError:
        raise DiscoveryIndexRefused() from None
    return value


def identifier(value):
    if type(value) is not str or IDENTIFIER.fullmatch(value) is None or int(value) > d.MAX_ID:
        raise DiscoveryIndexRefused()
    return value


def sequence(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise DiscoveryIndexRefused()
    return value


def mapping(value, keys):
    if type(value) is not dict or set(value) != keys:
        raise DiscoveryIndexRefused()
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def reject_constant(_):
    raise ValueError()


def read(path, maximum):
    direct(path)
    try:
        record = path.lstat()
        if not stat.S_ISREG(record.st_mode) or path.resolve(strict=True) != path:
            raise DiscoveryIndexRefused()
        if record.st_size > maximum:
            raise DiscoveryIndexRefused()
        with closing(open(path, 'rb')) as handle:
            payload = handle.read(maximum + 1)
    except OSError:
        # Absent, unreadable or aliased: one opaque refusal, never a raw OSError.
        raise DiscoveryIndexRefused() from None
    if len(payload) > maximum:
        raise DiscoveryIndexRefused()
    return payload


def parse(payload):
    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise DiscoveryIndexRefused() from None
    if type(value) is not dict or set(value) not in (INDEX_KEYS, INDEX_KEYS | {'projection'}, INDEX_KEYS | {'projection', 'region_rules', 'refresh_policy'}):
        raise DiscoveryIndexRefused()
    if 'projection' in value and value['projection'] != 'enabled-v2':
        raise DiscoveryIndexRefused()
    if 'refresh_policy' in value and value['refresh_policy'] != 'current-library-regions-v1':
        raise DiscoveryIndexRefused()
    return value


def person(record):
    mapping(record, PERSON_KEYS)
    if type(record['allow_zero']) is not bool:
        raise DiscoveryIndexRefused()
    return ReviewedPerson(library_id=text(record['library_id'], 128), id=identifier(record['id']),
                          label=text(record['label'], 256),
                          aliases=tuple(text(a, 128) for a in sequence(record['aliases'], 8)),
                          allow_zero=record['allow_zero'])


def face(record):
    mapping(record, FACE_KEYS)
    return ReviewedFace(id=identifier(record['id']), asset_id=identifier(record['asset_id']),
                        person_id=identifier(record['person_id']),
                        source=text(record['source'], 32))


def place(record):
    mapping(record, PLACE_KEYS)
    return ReviewedPlace(library_id=text(record['library_id'], 128), id=identifier(record['id']),
                         label=text(record['label'], 256))


def region(record):
    if type(record) is not list or len(record) != 2:
        raise DiscoveryIndexRefused()
    return (identifier(record[0]), identifier(record[1]))


def index(payload, limit):
    """Rebuild one ReviewedIndex within the shared row budget. validate runs after."""
    record = parse(payload)
    text(record['library_id'], 128)
    identifier(record['revision'])
    if DIGEST.fullmatch(text(record['source_digest'], 64)) is None:
        raise DiscoveryIndexRefused()
    constructor = ProjectedIndex if 'projection' in record else ReviewedIndex
    extra = {}
    if 'region_rules' in record:
        constructor = RefreshingPlaceIndex
        rules = []
        for rule in sequence(record['region_rules'], 128):
            mapping(rule, {'place_id', 'south', 'west', 'north', 'east'})
            parsed = RegionRule(**rule)
            try: d.validate_region_rule(parsed)
            except d.DiscoveryInvalid: raise DiscoveryIndexRefused() from None
            rules.append(parsed)
        extra = {'region_rules': tuple(rules)}
    return constructor(
        **extra,
        library_id=record['library_id'], revision=record['revision'],
        scope_ids=tuple(identifier(v) for v in sequence(record['scope_ids'], limit)),
        indexed_ids=tuple(identifier(v) for v in sequence(record['indexed_ids'], limit)),
        source_digest=record['source_digest'],
        people=tuple(person(v) for v in sequence(record['people'], 5000)),
        pinned_ids=tuple(identifier(v) for v in sequence(record['pinned_ids'], 32)),
        assignments=tuple(face(v) for v in sequence(record['assignments'], limit)),
        places=tuple(place(v) for v in sequence(record['places'], 5000)),
        regions=tuple(region(v) for v in sequence(record['regions'], limit)),
        enabled=tuple(text(v, 32) for v in sequence(record['enabled'], len(d.FIELDS))))


def accepted(loaded, budget):
    """Refuse anything the service would itself reject, before a runtime exists."""
    try:
        d.validate(loaded, loaded.library_id, budget.rows)
        if len(d.packed(asdict(loaded))) > budget.index_bytes:
            raise d.DiscoveryInvalid()
    except (d.DiscoveryInvalid, TypeError, KeyError, RecursionError):
        raise DiscoveryIndexRefused() from None
    return loaded


def shared_budget(value):
    """One budget shared by every index and by the runtime that serves them."""
    if value is None:
        return d.ReadBudget()
    if not isinstance(value, d.ReadBudget):
        raise DiscoveryIndexRefused()
    return value


def load(paths, *, budget=None):
    """Load explicit artifacts into one reviewed provider, sharing one budget."""
    if type(paths) is not tuple or not paths or not all(isinstance(p, Path) for p in paths):
        raise DiscoveryIndexRefused()
    shared = shared_budget(budget)
    indexes = tuple(accepted(index(read(path, shared.index_bytes), shared.rows), shared)
                    for path in paths)
    try:
        return MemoryIndexProvider(indexes)
    except (ValueError, TypeError):
        raise DiscoveryIndexRefused() from None


def runtime(access_runtime, paths, *, budget=None):
    """Compose the reviewed provider with an explicit AccessRuntime and one budget."""
    shared = shared_budget(budget)
    try:
        return DiscoveryRuntime(access=access_runtime, provider=load(paths, budget=shared),
                                budget=shared)
    except (ValueError, TypeError):
        raise DiscoveryIndexRefused() from None
