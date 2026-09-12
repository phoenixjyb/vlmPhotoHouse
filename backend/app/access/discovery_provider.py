"""Internal immutable review inputs, with memory-only provider; no loading/runtime hook.

These are trusted operator assertions, not a new public schema or authorization.
Neither the provider nor any digest can grant membership or original access.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol


@dataclass(frozen=True)
class ReviewedPerson:
    library_id: str
    id: str
    label: str
    aliases: tuple[str, ...] = ()
    allow_zero: bool = False  # Explicit library-roster approval even without a match.


@dataclass(frozen=True)
class ReviewedFace:
    id: str
    asset_id: str
    person_id: str
    source: str = 'manual'


@dataclass(frozen=True)
class ReviewedPlace:
    library_id: str
    id: str
    label: str


@dataclass(frozen=True)
class ReviewedIndex:
    library_id: str
    revision: str
    scope_ids: tuple[str, ...]
    indexed_ids: tuple[str, ...]
    source_digest: str
    people: tuple[ReviewedPerson, ...] = ()
    pinned_ids: tuple[str, ...] = ()
    assignments: tuple[ReviewedFace, ...] = ()
    places: tuple[ReviewedPlace, ...] = ()
    regions: tuple[tuple[str, str], ...] = ()  # (asset_id, reviewed place_id)
    enabled: tuple[str, ...] = ('people', 'date', 'caption', 'tags', 'locations', 'media')


class IndexProvider(Protocol):
    def get(self, library_id: str) -> ReviewedIndex | None: ...


class MemoryIndexProvider:
    """Construction supplies already-reviewed internal inputs; no automatic discovery."""
    def __init__(self, indexes: tuple[ReviewedIndex, ...]):
        if type(indexes) is not tuple or any(type(i) is not ReviewedIndex for i in indexes):
            raise ValueError('Explicit reviewed indexes required')
        if len(indexes) > 32 or len({i.library_id for i in indexes}) != len(indexes):
            raise ValueError('Bounded unique library indexes required')
        self._indexes = MappingProxyType({i.library_id: i for i in indexes})

    def get(self, library_id):
        return self._indexes.get(library_id)
