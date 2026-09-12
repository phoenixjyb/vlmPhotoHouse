"""Unmounted protected discovery service. Internal Python results, not a wire API.

All source reads share the existing AccessService authorization transaction.
No SQL writes, filesystem/index loading, models, HTTP routes or original grants.
"""
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
import hashlib
import json
import math
import re
import sqlite3
import threading
from time import monotonic
import unicodedata

from .credentials import session_digest
from .discovery_provider import ReviewedIndex, ReviewedPerson, ReviewedFace, ReviewedPlace
from .library import _asset
from .service import AccessService, AccessDenied

POLICY = 'protected-discovery-service-1'
FIELDS = ('people', 'date', 'caption', 'tags', 'locations', 'media')
SOURCES = {'manual':'manual', 'cap':'caption', 'img':'image', 'cap+img':'caption_image', 'rule':'rule'}
MAX_ID = 2**63-1
SCOPE = " JOIN assets a ON a.id=x.asset_id JOIN access_asset_libraries m ON m.asset_id=a.id WHERE m.library_id=? AND (a.status='active' OR a.status IS NULL)"


class DiscoveryInvalid(ValueError):
    def __init__(self): super().__init__('Invalid discovery input')
class DiscoveryChanged(Exception):
    def __init__(self): super().__init__('Refresh discovery state')
class DiscoveryUnavailable(Exception):
    def __init__(self): super().__init__('Discovery unavailable')
class DiscoveryBusy(Exception):
    retry_after_seconds = 2
    def __init__(self): super().__init__('Discovery busy')
class DiscoveryCancelled(Exception):
    def __init__(self): super().__init__('Discovery cancelled')


def require(value):
    if not value: raise DiscoveryInvalid()


def packed(value):
    try: return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',', ':'),allow_nan=False).encode()
    except (ValueError,TypeError,UnicodeError,RecursionError): raise DiscoveryInvalid() from None


def digest(value): return hashlib.sha256(packed(value)).hexdigest()


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,18}',value) is not None and int(value) <= MAX_ID)
    return value


def text(value, maximum, nonempty=True):
    require(type(value) is str)
    try: require(len(value.encode('utf-8')) <= maximum)
    except UnicodeError: raise DiscoveryInvalid() from None
    require(not any(ord(c)<32 and c not in '\n\t' for c in value) and (not nonempty or bool(value.strip())))
    return value


def hashed(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def fold(value): return unicodedata.normalize('NFKC',value).casefold()


def ids(values, maximum, *, ordered=False):
    require(type(values) is tuple and len(values)<=maximum)
    for value in values: identifier(value)
    require(len(set(values))==len(values))
    if ordered: require(list(values)==sorted(values,key=int))
    return set(values)


class ReadBudget:
    """Share ONE budget across service instances; dedicated SQLite connection per call.

    Cooperative query/CPU checks, not a hard memory/IO deadline. It owns the
    connection progress callback during a call; no ambient callback is preserved.
    """
    def __init__(self, *, rows=100000, source_bytes=16*1024**2, index_bytes=4*1024**2,
                 response_bytes=512*1024, seconds=2.0, concurrency=2, clock=monotonic):
        require(all(type(v) is int and v>0 for v in (rows,source_bytes,index_bytes,response_bytes,concurrency)))
        require(type(seconds) in (int,float) and math.isfinite(seconds) and seconds>0)
        self.rows,self.source_bytes,self.index_bytes,self.response_bytes=rows,source_bytes,index_bytes,response_bytes
        self.seconds,self.clock=seconds,clock
        self.slots=threading.BoundedSemaphore(concurrency)

    @contextmanager
    def attempt(self, connection, cancelled):
        if not self.slots.acquire(blocking=False): raise DiscoveryBusy()
        try:
            start=self.clock(); count=0; size=0
            def check():
                if cancelled(): raise DiscoveryCancelled()
                now=self.clock()
                if not math.isfinite(now) or now<start or now-start>self.seconds: raise DiscoveryUnavailable()
            def progress():
                try: check(); return 0
                except (DiscoveryUnavailable,DiscoveryCancelled): return 1
            def read(sql, args):
                nonlocal count,size
                check(); result=[]; cursor=connection.execute(sql,args)
                while True:
                    chunk=cursor.fetchmany(128)
                    if not chunk: break
                    check(); count+=len(chunk)
                    if count>self.rows: raise DiscoveryUnavailable()
                    for row in chunk:
                        size+=len(packed(row))
                        if size>self.source_bytes: raise DiscoveryUnavailable()
                        result.append(row)
                return result
            check(); connection.set_progress_handler(progress,1000)
            try: yield check,read
            except sqlite3.Error:
                check(); raise DiscoveryUnavailable() from None
        finally:
            try: connection.set_progress_handler(None,0)
            finally: self.slots.release()


def scoped_source(library, read):
    """Only called after policy. Bounded semantic projection, no paths or globals."""
    assets=read("SELECT a.id,CASE WHEN length(CAST(a.mime AS BLOB))<=256 THEN a.mime END,a.width,a.height,a.duration_sec,CASE WHEN length(CAST(a.taken_at AS BLOB))<=64 THEN a.taken_at END,length(CAST(a.taken_at AS BLOB)) FROM assets a JOIN access_asset_libraries m ON m.asset_id=a.id WHERE m.library_id=? AND (a.status='active' OR a.status IS NULL) ORDER BY a.id",(library,))
    captions=read('SELECT x.id,x.asset_id,CASE WHEN length(CAST(x.text AS BLOB))<=4096 THEN x.text END,length(CAST(x.text AS BLOB)),length(CAST(x.text AS BLOB)),x.user_edited,x.superseded FROM captions x'+SCOPE+' ORDER BY x.id',(library,))
    faces=read('SELECT x.id,x.asset_id,x.person_id,x.label_source FROM face_detections x'+SCOPE+' ORDER BY x.id',(library,))
    links=read('SELECT x.id,x.asset_id,x.tag_id,x.source FROM asset_tags x'+SCOPE+' ORDER BY x.id',(library,))
    blocks=read('SELECT x.id,x.asset_id,x.tag_id FROM asset_tag_blocks x'+SCOPE+' ORDER BY x.id',(library,))
    tags=read("SELECT DISTINCT t.id,CASE WHEN length(CAST(t.name AS BLOB))<=256 THEN t.name END,CASE WHEN length(CAST(t.type AS BLOB))<=32 THEN t.type END,length(CAST(t.name AS BLOB)) FROM tags t JOIN asset_tags x ON x.tag_id=t.id"+SCOPE+' ORDER BY t.id',(library,))
    return {'assets':assets,'captions':captions,'faces':faces,'links':links,'blocks':blocks,'tags':tags}


def validate(index, library, limit):
    require(type(index) is ReviewedIndex and index.library_id==library)
    identifier(index.revision); require(hashed(index.source_digest))
    scope=ids(index.scope_ids,limit,ordered=True); selected=ids(index.indexed_ids,limit,ordered=True)
    require(selected<=scope)
    require(type(index.enabled) is tuple and len(set(index.enabled))==len(index.enabled) and set(index.enabled)<=set(FIELDS) and 'media' in index.enabled)
    require(type(index.people) is tuple and len(index.people)<=5000 and type(index.places) is tuple and len(index.places)<=5000)
    people={}; places={}
    for person in index.people:
        require(type(person) is ReviewedPerson and person.library_id==library and type(person.allow_zero) is bool)
        identifier(person.id); require(person.id not in people); text(person.label,256)
        require(type(person.aliases) is tuple and len(person.aliases)<=8)
        for alias in person.aliases: text(alias,128)
        require(len(set(person.aliases))==len(person.aliases)); people[person.id]=person
    for place in index.places:
        require(type(place) is ReviewedPlace and place.library_id==library)
        identifier(place.id); require(place.id not in places);text(place.label,256);places[place.id]=place
    require(ids(index.pinned_ids,32)<=set(people))
    require(type(index.assignments) is tuple and len(index.assignments)<=limit)
    seen=set()
    for face in index.assignments:
        require(type(face) is ReviewedFace)
        for value in (face.id,face.asset_id,face.person_id):identifier(value)
        require(face.id not in seen and face.source=='manual' and face.asset_id in selected and face.person_id in people)
        seen.add(face.id)
    require(type(index.regions) is tuple and len(index.regions)<=limit)
    pairs=set()
    for pair in index.regions:
        require(type(pair) is tuple and len(pair)==2)
        for value in pair:identifier(value)
        require(pair not in pairs and pair[0] in selected and pair[1] in places);pairs.add(pair)
    return people,places


def taken_day(value):
    if value is None: return None
    try:
        text(value,64); require(len(value)>=10 and value[4]=='-' and value[7]=='-')
        result=date.fromisoformat(value[:10]).isoformat()
        if len(value)>10: require(value[10] in ('T',' '));datetime.fromisoformat(value)
        return result
    except (ValueError,TypeError): return None


def current_caption(rows):
    eligible=[r for r in rows if r[6]==0 and r[5] in (0,1) and ((type(r[4]) is int and r[4]>4096) or (type(r[2]) is str and r[2].strip()))]
    edited=[r for r in eligible if r[5]==1];chosen=edited or eligible
    if len(chosen)!=1: return None
    row=chosen[0]
    if type(row[4]) is not int or row[4]>4096: return None
    try: return text(row[2],4096)
    except DiscoveryInvalid: return None


class DiscoveryReads:
    def __init__(self, access: AccessService, provider, budget: ReadBudget):
        if not isinstance(access,AccessService) or not isinstance(budget,ReadBudget): raise ValueError('Explicit access and shared budget required')
        self.access,self.provider,self.budget=access,provider,budget

    def _run(self, token, library, expected, action, cancelled):
        if type(library) is not str or not 1<=len(library)<=128 or any(ord(c)<32 for c in library):
            raise AccessDenied('Access denied')
        with self.budget.attempt(self.access.db,cancelled) as (check,read):
            with self.access._transaction():
                # The sole authorization decision precedes index lookup and all metadata.
                member=self.access._require(token,library,'library.read')
                check();index=self.provider.get(library)
                if index is None: raise DiscoveryUnavailable()
                try:
                    people,places=validate(index,library,self.budget.rows)
                    if len(packed(asdict(index)))>self.budget.index_bytes: raise DiscoveryUnavailable()
                except (DiscoveryInvalid,TypeError,KeyError,RecursionError): raise DiscoveryUnavailable() from None
                source=scoped_source(library,read);check()
                if tuple(str(r[0]) for r in source['assets'])!=index.scope_ids or digest(source)!=index.source_digest: raise DiscoveryChanged()
                binding=digest({'policy':POLICY,'library':library,'session':session_digest(token),'account':member['account_id'],
                                'membership':member['revision'],'originals':member['originals'],'index':asdict(index)})
                if expected is not None:
                    require(hashed(expected))
                    if binding!=expected: raise DiscoveryChanged()
                facts=self._facts(index,source,people,places,check)
                result=action(index,facts,binding,member,check)
                check()
                if len(packed(result))>self.budget.response_bytes: raise DiscoveryUnavailable()
                return result

    def _facts(self,index,source,people,places,check):
        assets={}
        for r in source['assets']:
            check(); fields=list(r[:6])
            try: text(fields[1],256)
            except DiscoveryInvalid: fields[1]=None
            # Never expose a truncated/invalid recorded date as valid native metadata.
            if taken_day(fields[5]) is None: fields[5]=None
            assets[str(r[0])]=_asset(fields,index.library_id)
        captions=defaultdict(list);person_links=defaultdict(set);regions=defaultdict(set)
        for row in source['captions']:captions[str(row[1])].append(row)
        faces={str(r[0]):(str(r[1]),str(r[2]),r[3]) for r in source['faces']}
        for row in index.assignments:
            check()
            if faces.get(row.id)!=(row.asset_id,row.person_id,row.source): raise DiscoveryChanged()
            person_links[row.asset_id].add(row.person_id)
        approved={pid for pids in person_links.values() for pid in pids}
        if any(pid not in approved and not record.allow_zero for pid,record in people.items()): raise DiscoveryUnavailable()
        for aid,pid in index.regions:regions[aid].add(pid)
        tag_defs={str(r[0]):{'id':str(r[0]),'label':r[1],'kind':r[2] if r[2] in ('date','location','person','scene','custom') else 'unknown'} for r in source['tags']}
        blocked={(str(r[1]),str(r[2])) for r in source['blocks']}; links=defaultdict(list)
        for row in source['links']:links[(str(row[1]),str(row[2]))].append(row)
        tag_links=defaultdict(dict)
        for (aid,tid),rows in links.items():
            check()
            if (aid,tid) not in blocked and len(rows)==1 and tid in tag_defs:
                try: text(tag_defs[tid]['label'],256)
                except DiscoveryInvalid: continue
                tag_links[aid][tid]=SOURCES.get(rows[0][3],'unknown')
        rows={}
        for aid in index.indexed_ids:
            check();rows[aid]={'people':person_links[aid],'locations':regions[aid],'tags':tag_links[aid],
                              'date':taken_day(assets[aid]['taken_at']),'caption':current_caption(captions[aid])}
        counts={f:Counter() for f in ('people','locations','tags')}; provenance=defaultdict(Counter)
        for row in rows.values():
            check()
            for f in counts:counts[f].update(row[f].keys() if f=='tags' else row[f])
            for tid,kind in row['tags'].items():provenance[tid][kind]+=1
        total=len(assets)
        coverage={f:{'with_values':sum(bool(row[f]) for row in rows.values()) if f in index.enabled else 0} for f in FIELDS if f!='media'}
        coverage['media']={'with_values':total}
        for value in coverage.values():value['without_values']=total-value['with_values']
        used_tags=set(counts['tags'])
        facets={'people':[{'id':p.id,'label':p.label,'aliases':list(p.aliases),'asset_count':counts['people'][p.id],'provenance':'reviewed_assignments'} for p in people.values()],
                'locations':[{'id':p.id,'label':p.label,'asset_count':counts['locations'][p.id],'provenance':'reviewed_region'} for p in places.values()],
                'tags':[dict(tag_defs[tid],asset_count=counts['tags'][tid],provenance_counts=dict(provenance[tid])) for tid in used_tags]}
        for f in facets:facets[f]=sorted(facets[f],key=lambda p:int(p['id'])) if f in index.enabled else []
        return assets,rows,facets,coverage

    def facets(self, token, library, *, facet='people', page=1, page_size=50, binding=None, cancelled=lambda:False):
        def action(index,facts,context,member,check):
            require(facet in ('people','tags','locations') and type(page) is int and 1<=page<=5000 and type(page_size) is int and 1<=page_size<=100)
            require(page==1 or binding is not None)
            assets,rows,facets,coverage=facts;items=facets[facet];offset=(page-1)*page_size
            people={p['id']:p for p in facets['people']};pins=index.pinned_ids if 'people' in index.enabled else ()
            days=[r['date'] for r in rows.values() if r['date'] is not None] if 'date' in index.enabled else []
            return {'library_id':library,'binding':context,'revision':index.revision,
                    'enabled':list(index.enabled),'unavailable':{'themes':'no_reviewed_taxonomy','topics':'no_reviewed_taxonomy'},
                    'catalog_assets':len(assets),'indexed_assets':len(rows),'index_complete':len(assets)==len(rows),
                    'metadata_completeness':'not_inferred','tag_generation_completeness':'unknown','coverage':coverage,
                    'captured_date_bounds':{'from':min(days) if days else None,'to':max(days) if days else None},
                    'pinned_person_ids':list(pins),'pinned_people':[people[pid] for pid in pins],
                    'facet':facet,'page':page,'page_size':page_size,'total':len(items),'has_more':offset+page_size<len(items),'items':items[offset:offset+page_size]}
        return self._run(token,library,binding,action,cancelled)

    def search(self, token, library, *, binding, filters, page=1, page_size=50, fingerprint=None, cancelled=lambda:False):
        def action(index,facts,context,member,check):
            require(binding is not None and type(page) is int and 1<=page<=100000 and type(page_size) is int and 1<=page_size<=100)
            require(type(filters) is dict and set(filters)<=set(FIELDS) and set(filters)<=set(index.enabled))
            require(len(packed(filters))<=16384)
            assets,rows,facets,coverage=facts;normalized={}
            for f,v in filters.items():
                if f in ('people','tags'):
                    require(type(v) is dict and set(v)=={'ids','match'} and type(v['ids']) is list and v['match'] in ('any','all'))
                    selection=ids(tuple(v['ids']),20);require(bool(selection) and selection<={r['id'] for r in facets[f]})
                    normalized[f]={'ids':sorted(selection,key=int),'match':v['match']}
                elif f=='locations':
                    require(type(v) is list);selection=ids(tuple(v),20);require(bool(selection) and selection<={r['id'] for r in facets[f]});normalized[f]=sorted(selection,key=int)
                elif f=='media':
                    require(type(v) is list and 1<=len(v)<=3 and all(type(x) is str and x in ('image','video','other') for x in v) and len(set(v))==len(v));normalized[f]=sorted(v)
                elif f=='date':
                    require(type(v) is dict and set(v)=={'from','to'})
                    for endpoint in v.values():
                        if endpoint is not None:
                            require(type(endpoint) is str and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}',endpoint) is not None)
                            try:date.fromisoformat(endpoint)
                            except ValueError:raise DiscoveryInvalid() from None
                    require(any(x is not None for x in v.values()) and (v['from'] is None or v['to'] is None or v['from']<=v['to']));normalized[f]=dict(v)
                else:normalized[f]=fold(text(v,512).strip())
            expected=digest({'binding':context,'filters':normalized,'page_size':page_size})
            if page>1:require(fingerprint is not None)
            if fingerprint is not None:
                require(hashed(fingerprint))
                if fingerprint!=expected:raise DiscoveryChanged()
            found=[]
            for aid,asset in sorted(assets.items(),key=lambda p:int(p[0]),reverse=True):
                check();row=rows.get(aid)
                if 'media' in normalized and asset['kind'] not in normalized['media']:continue
                if row is None and set(normalized)-{'media'}:continue
                matches=True
                for f in ('people','tags'):
                    if f in normalized:
                        selection=set(normalized[f]['ids']);present=set(row[f])
                        if not (selection<=present if normalized[f]['match']=='all' else bool(selection&present)):matches=False
                if not matches:continue
                if 'locations' in normalized and not set(normalized['locations'])&row['locations']:continue
                if 'date' in normalized:
                    day=row['date'];bounds=normalized['date']
                    if day is None or (bounds['from'] is not None and day<bounds['from']) or (bounds['to'] is not None and day>bounds['to']):continue
                if 'caption' in normalized and (row['caption'] is None or normalized['caption'] not in fold(row['caption'])):continue
                found.append(asset)
            offset=(page-1)*page_size
            return {'library_id':library,'binding':context,'fingerprint':expected,'page':page,'page_size':page_size,
                    'total':len(found),'has_more':offset+page_size<len(found),'originals_allowed':bool(member['originals']),
                    'items':found[offset:offset+page_size]}
        return self._run(token,library,binding,action,cancelled)
