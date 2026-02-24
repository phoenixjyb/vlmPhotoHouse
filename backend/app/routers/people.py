from fastapi import APIRouter, Depends, Body, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pathlib import Path

from ..db import Person, FaceDetection, Asset, Task
from ..dependencies import get_db
from ..paths import DERIVED_PATH
from .. import schemas

router = APIRouter()

# Helper

def _recompute_face_counts(db_s: Session, person_ids):
    if not person_ids:
        return
    # SessionLocal uses autoflush=False; flush pending person_id changes before counting.
    db_s.flush()
    counts = (
        db_s.query(FaceDetection.person_id, func.count(FaceDetection.id))
        .filter(FaceDetection.person_id.in_(person_ids))
        .group_by(FaceDetection.person_id).all()
    )
    count_map = {pid: c for pid, c in counts}
    persons = db_s.query(Person).filter(Person.id.in_(person_ids)).all()
    for p in persons:
        p.face_count = count_map.get(p.id, 0)  # type: ignore[attr-defined]

def _remove_face_artifacts(face: FaceDetection):
    # Remove generated crops for this face across any size buckets.
    faces_root = DERIVED_PATH / 'faces'
    if faces_root.exists():
        for p in faces_root.glob(f"*/{face.id}.jpg"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
    # Remove persisted embedding if tracked.
    if face.embedding_path:
        try:
            Path(face.embedding_path).unlink(missing_ok=True)
        except Exception:
            pass

def _enqueue_label_propagation(db_s: Session, person_ids: list[int]) -> int | None:
    target_ids = sorted({int(pid) for pid in person_ids if pid is not None})
    if not target_ids:
        return None
    existing = (
        db_s.query(Task)
        .filter(Task.type == 'person_label_propagate')
        .filter(Task.state.in_(['pending', 'running']))
        .order_by(Task.id.desc())
        .first()
    )
    if existing and existing.state == 'pending':
        payload = dict(existing.payload_json or {})
        prev = payload.get('person_ids') or []
        prev_ids = set()
        for v in prev:
            try:
                prev_ids.add(int(v))
            except Exception:
                continue
        payload['person_ids'] = sorted(prev_ids.union(target_ids))
        existing.payload_json = payload
        db_s.flush()
        return int(existing.id)
    # Keep this fairly high priority so manual corrections propagate quickly.
    t = Task(type='person_label_propagate', priority=95, payload_json={'person_ids': target_ids})
    db_s.add(t)
    db_s.flush()
    return int(t.id)

@router.get('/persons', response_model=schemas.PersonsResponse)
def list_persons(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    include_faces: bool = Query(False),
    sort_by: str = Query('id'),
    order: str = Query('asc'),
    named_only: bool = Query(False),
    name_query: str | None = Query(None),
    db_s: Session = Depends(get_db)
):
    base_q = db_s.query(Person)
    if named_only:
        base_q = base_q.filter(Person.display_name != None).filter(func.trim(Person.display_name) != '')
    if name_query and name_query.strip():
        base_q = base_q.filter(Person.display_name.ilike(f"%{name_query.strip()}%"))
    total = base_q.count()
    sort_key = Person.face_count if sort_by == 'face_count' else Person.id
    sort_clause = sort_key.desc() if order == 'desc' else sort_key.asc()
    persons = base_q.order_by(sort_clause, Person.id.asc()).offset((page-1)*page_size).limit(page_size).all()
    result = []
    for p in persons:
        item = {'id': p.id, 'display_name': p.display_name, 'face_count': p.face_count}
        if include_faces:
            faces = db_s.query(FaceDetection).filter(FaceDetection.person_id==p.id).limit(5).all()
            item['sample_faces'] = [f.id for f in faces]
        result.append(item)
    return {'api_version': schemas.API_VERSION, 'page': page, 'page_size': page_size, 'total': total, 'persons': result}

@router.get('/faces', response_model=schemas.FacesResponse)
def list_faces(
    person_id: int | None = Query(None),
    asset_id: int | None = Query(None),
    unassigned: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db_s: Session = Depends(get_db)
):
    q = db_s.query(FaceDetection)
    if person_id is not None and unassigned:
        raise HTTPException(status_code=400, detail='Specify either person_id or unassigned, not both')
    if person_id is not None:
        q = q.filter(FaceDetection.person_id==person_id)
    if asset_id is not None:
        q = q.filter(FaceDetection.asset_id==asset_id)
    if unassigned:
        q = q.filter(FaceDetection.person_id==None)
    total = q.count()
    faces = q.order_by(FaceDetection.id.asc()).offset((page-1)*page_size).limit(page_size).all()
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'faces': [
            {
                'id': f.id,
                'asset_id': f.asset_id,
                'person_id': f.person_id,
                'label_source': getattr(f, 'label_source', None),
                'label_score': getattr(f, 'label_score', None),
            }
            for f in faces
        ],
    }

@router.get('/faces/{face_id}')
def get_face(face_id: int, db_s: Session = Depends(get_db)):
    face = db_s.get(FaceDetection, face_id)
    if not face:
        raise HTTPException(status_code=404, detail='face not found')
    return {
        'id': face.id,
        'asset_id': face.asset_id,
        'bbox': {'x': face.bbox_x, 'y': face.bbox_y, 'w': face.bbox_w, 'h': face.bbox_h},
        'person_id': face.person_id,
        'has_embedding': bool(face.embedding_path),
    }

@router.get('/faces/{face_id}/crop')
def get_face_crop(face_id: int, size: int = Query(256), db_s: Session = Depends(get_db)):
    face = db_s.get(FaceDetection, face_id)
    if not face:
        raise HTTPException(status_code=404, detail='face not found')
    crop_path = DERIVED_PATH / 'faces' / str(size) / f'{face.id}.jpg'
    if not crop_path.exists():
        raise HTTPException(status_code=404, detail='crop not found')
    return FileResponse(str(crop_path))

@router.post('/faces/{face_id}/assign')
def assign_face(face_id: int, person_id: int | None = Body(None), create_new: bool = Body(False), db_s: Session = Depends(get_db)):
    face = db_s.get(FaceDetection, face_id)
    if not face:
        raise HTTPException(status_code=404, detail='face not found')
    target_person_id = person_id
    created = False
    if create_new or (person_id is None):
        p = Person(display_name=None, face_count=0)
        db_s.add(p)
        db_s.flush()
        target_person_id = p.id
        created = True
    person = db_s.get(Person, target_person_id)
    if not person:
        raise HTTPException(status_code=404, detail='person not found')
    face.person_id = person.id  # type: ignore[attr-defined]
    face.label_source = 'manual'  # type: ignore[attr-defined]
    face.label_score = None  # type: ignore[attr-defined]
    _recompute_face_counts(db_s, [person.id])
    propagation_task_id = _enqueue_label_propagation(db_s, [int(person.id)])
    db_s.commit()
    return {'face_id': face.id, 'person_id': person.id, 'new_person_created': created, 'propagation_task_id': propagation_task_id}

@router.delete('/faces/{face_id}')
def delete_face(face_id: int, prune_empty_person: bool = Query(True), db_s: Session = Depends(get_db)):
    face = db_s.get(FaceDetection, face_id)
    if not face:
        raise HTTPException(status_code=404, detail='face not found')

    pid = face.person_id
    _remove_face_artifacts(face)
    db_s.delete(face)
    db_s.flush()

    deleted_person_id = None
    if pid is not None:
        _recompute_face_counts(db_s, [pid])
        if prune_empty_person:
            p = db_s.get(Person, pid)
            if p and p.face_count == 0 and (not p.display_name or not p.display_name.strip()):
                deleted_person_id = p.id
                db_s.delete(p)

    db_s.commit()
    return {'deleted_face_id': face_id, 'deleted_person_id': deleted_person_id}

@router.post('/faces/delete')
def delete_faces_bulk(
    face_ids: List[int] = Body(...),
    prune_empty_person: bool = Body(True),
    db_s: Session = Depends(get_db)
):
    if not face_ids:
        raise HTTPException(status_code=400, detail='face_ids required')

    faces = db_s.query(FaceDetection).filter(FaceDetection.id.in_(face_ids)).all()
    if not faces:
        raise HTTPException(status_code=404, detail='no faces found')

    person_ids = set()
    for face in faces:
        if face.person_id is not None:
            person_ids.add(face.person_id)
        _remove_face_artifacts(face)
        db_s.delete(face)
    db_s.flush()

    deleted_person_ids = []
    if person_ids:
        _recompute_face_counts(db_s, list(person_ids))
        if prune_empty_person:
            for pid in person_ids:
                p = db_s.get(Person, pid)
                if p and p.face_count == 0 and (not p.display_name or not p.display_name.strip()):
                    deleted_person_ids.append(p.id)
                    db_s.delete(p)

    db_s.commit()
    return {'deleted_faces': len(faces), 'deleted_person_ids': deleted_person_ids}

@router.post('/faces/assign')
def assign_faces_bulk(person_id: int | None = Body(None), face_ids: List[int] = Body(...), create_new: bool = Body(False), db_s: Session = Depends(get_db)):
    if not face_ids:
        raise HTTPException(status_code=400, detail='face_ids required')
    target_person_id = person_id
    created = False
    if create_new or (person_id is None):
        p = Person(display_name=None, face_count=0)
        db_s.add(p)
        db_s.flush()
        target_person_id = p.id
        created = True
    faces = db_s.query(FaceDetection).filter(FaceDetection.id.in_(face_ids)).all()
    if not faces:
        raise HTTPException(status_code=404, detail='no faces found')
    for f in faces:
        f.person_id = target_person_id  # type: ignore[attr-defined]
        f.label_source = 'manual'  # type: ignore[attr-defined]
        f.label_score = None  # type: ignore[attr-defined]
    _recompute_face_counts(db_s, [target_person_id])
    propagation_task_id = _enqueue_label_propagation(db_s, [int(target_person_id)])
    db_s.commit()
    return {'assigned': len(faces), 'person_id': target_person_id, 'new_person_created': created, 'propagation_task_id': propagation_task_id}

@router.post('/persons/{person_id}/name')
def rename_person(person_id: int, display_name: str = Body(..., embed=True), db_s: Session = Depends(get_db)):
    person = db_s.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail='person not found')
    person.display_name = display_name  # type: ignore[attr-defined]
    db_s.commit()
    return {'person_id': person.id, 'display_name': person.display_name}

@router.post('/persons/merge')
def merge_persons(target_id: int = Body(...), source_ids: List[int] = Body(...), db_s: Session = Depends(get_db)):
    if target_id in source_ids:
        source_ids = [sid for sid in source_ids if sid != target_id]
    target = db_s.get(Person, target_id)
    if not target:
        raise HTTPException(status_code=404, detail='target person not found')
    sources = db_s.query(Person).filter(Person.id.in_(source_ids)).all()
    if not sources:
        raise HTTPException(status_code=404, detail='no source persons found')
    faces = db_s.query(FaceDetection).filter(FaceDetection.person_id.in_([p.id for p in sources])).all()
    for f in faces:
        f.person_id = target.id  # type: ignore[attr-defined]
    for p in sources:
        db_s.delete(p)
    _recompute_face_counts(db_s, [target.id])
    propagation_task_id = _enqueue_label_propagation(db_s, [int(target.id)])
    db_s.commit()
    return {'target_id': target.id, 'merged_sources': [p.id for p in sources], 'moved_faces': len(faces), 'face_count': target.face_count, 'propagation_task_id': propagation_task_id}

@router.post('/persons/{person_id}/delete')
def delete_person(person_id: int, db_s: Session = Depends(get_db)):
    person = db_s.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail='person not found')
    faces = db_s.query(FaceDetection).filter(FaceDetection.person_id==person.id).all()
    for f in faces:
        f.person_id = None  # type: ignore[attr-defined]
        f.label_source = None  # type: ignore[attr-defined]
        f.label_score = None  # type: ignore[attr-defined]
    db_s.delete(person)
    db_s.commit()
    return {'deleted_person_id': person_id, 'faces_reassigned': len(faces)}

@router.post('/persons/recluster', response_model=schemas.ReclusterTriggerResponse)
def trigger_recluster(db_s: Session = Depends(get_db)):
    existing = db_s.query(Task).filter(Task.type=='person_recluster', Task.state.in_(['pending','running'])).first()
    if existing:
        task_id = existing.id
    else:
        t = Task(type='person_recluster', priority=300, payload_json={})
        db_s.add(t)
        db_s.commit()
        task_id = t.id
    return schemas.ReclusterTriggerResponse(api_version=schemas.API_VERSION, task_id=int(task_id))

@router.get('/persons/recluster/status', response_model=schemas.ReclusterStatusResponse)
def recluster_status(db_s: Session = Depends(get_db)):
    task = db_s.query(Task).filter(Task.type=='person_recluster').order_by(Task.id.desc()).first()
    if not task:
        return schemas.ReclusterStatusResponse(api_version=schemas.API_VERSION, running=False, task=None)
    running = task.state in ('pending','running')
    return schemas.ReclusterStatusResponse(
        api_version=schemas.API_VERSION,
        running=running,
        task=schemas.ReclusterStatusTask(
            id=task.id,
            state=task.state,
            retry_count=task.retry_count,
            created_at=str(task.created_at) if task.created_at else None,
            updated_at=str(task.updated_at) if task.updated_at else None,
            summary=task.payload_json.get('summary') if task.payload_json else None,
        )
    )

# Task management endpoints (basic inspection and cancellation)
@router.get('/tasks', response_model=schemas.TasksResponse)
def list_tasks(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), state: str | None = Query(None), type: str | None = Query(None), db_s: Session = Depends(get_db)):
    q = db_s.query(Task)
    if state:
        q = q.filter(Task.state==state)
    if type:
        q = q.filter(Task.type==type)
    total = q.count()
    tasks = q.order_by(Task.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    def to_out(t: Task):
        return {
            'id': t.id,
            'type': t.type,
            'state': t.state,
            'priority': t.priority,
            'retry_count': t.retry_count,
            'last_error': t.last_error,
            'progress_current': t.progress_current,
            'progress_total': t.progress_total,
            'cancel_requested': t.cancel_requested,
            'created_at': str(t.created_at) if t.created_at else None,
            'updated_at': str(t.updated_at) if t.updated_at else None,
        }
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'tasks': [to_out(t) for t in tasks]
    }

@router.get('/tasks/{task_id}', response_model=schemas.TaskDetailResponse)
def get_task(task_id: int, db_s: Session = Depends(get_db)):
    t = db_s.get(Task, task_id)
    if not t:
        return {'api_version': schemas.API_VERSION, 'task': None}
    out = {
        'id': t.id,
        'type': t.type,
        'state': t.state,
        'priority': t.priority,
        'retry_count': t.retry_count,
        'last_error': t.last_error,
        'progress_current': t.progress_current,
        'progress_total': t.progress_total,
        'cancel_requested': t.cancel_requested,
        'created_at': str(t.created_at) if t.created_at else None,
        'updated_at': str(t.updated_at) if t.updated_at else None,
    }
    return {'api_version': schemas.API_VERSION, 'task': out}

@router.post('/tasks/{task_id}/cancel', response_model=schemas.TaskCancelResponse)
def cancel_task(task_id: int, db_s: Session = Depends(get_db)):
    t = db_s.get(Task, task_id)
    if not t:
        raise HTTPException(status_code=404, detail='task not found')
    if t.state in ('done','failed'):
        return {'api_version': schemas.API_VERSION, 'task_id': t.id, 'state': t.state}
    t.cancel_requested = True
    # Optionally transition pending running tasks; executor will honor later when progress added
    db_s.commit()
    return {'api_version': schemas.API_VERSION, 'task_id': t.id, 'state': t.state}

# --- Person-based search endpoints ---

@router.get('/search/person/{person_id}', response_model=schemas.SearchResponse)
def search_photos_by_person(
    person_id: int,
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=200),
    db_s: Session = Depends(get_db)
):
    """Find all photos containing a specific person."""
    # Verify person exists
    person = db_s.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail='person not found')
    
    # Get asset IDs for photos containing this person
    asset_ids_subquery = (
        db_s.query(FaceDetection.asset_id)
        .filter(FaceDetection.person_id == person_id)
        .distinct()
        .subquery()
    )
    
    # Query assets with pagination
    base_query = db_s.query(Asset).filter(Asset.id.in_(asset_ids_subquery))
    total = base_query.count()
    
    assets = (
        base_query
        .order_by(Asset.id.desc())
        .offset((page-1) * page_size)
        .limit(page_size)
        .all()
    )
    
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'person_id': person_id,
        'person_name': person.display_name,
        'items': [{'id': a.id, 'path': a.path} for a in assets]
    }

@router.get('/search/person/name/{name}', response_model=schemas.SearchResponse)
def search_photos_by_person_name(
    name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db_s: Session = Depends(get_db)
):
    """Find all photos containing a person with the given name (case-insensitive partial match)."""
    # Find persons matching the name
    persons = (
        db_s.query(Person)
        .filter(Person.display_name.ilike(f"%{name}%"))
        .all()
    )
    
    if not persons:
        return {
            'api_version': schemas.API_VERSION,
            'page': page,
            'page_size': page_size,
            'total': 0,
            'search_name': name,
            'matched_persons': [],
            'items': []
        }
    
    person_ids = [p.id for p in persons]
    
    # Get asset IDs for photos containing any of these persons
    asset_ids_subquery = (
        db_s.query(FaceDetection.asset_id)
        .filter(FaceDetection.person_id.in_(person_ids))
        .distinct()
        .subquery()
    )
    
    # Query assets with pagination
    base_query = db_s.query(Asset).filter(Asset.id.in_(asset_ids_subquery))
    total = base_query.count()
    
    assets = (
        base_query
        .order_by(Asset.id.desc())
        .offset((page-1) * page_size)
        .limit(page_size)
        .all()
    )
    
    return {
        'api_version': schemas.API_VERSION,
        'page': page,
        'page_size': page_size,
        'total': total,
        'search_name': name,
        'matched_persons': [{'id': p.id, 'name': p.display_name} for p in persons],
        'items': [{'id': a.id, 'path': a.path} for a in assets]
    }

@router.post('/search/person/vector', response_model=schemas.VectorSearchResponse)
def vector_search_with_person_filter(
    text: Optional[str] = Body(None),
    asset_id: Optional[int] = Body(None),
    person_id: Optional[int] = Body(None),
    k: int = Body(10),
    db_s: Session = Depends(get_db)
):
    """Vector search with optional person filtering."""
    # Import vector search dependencies
    from ..tasks import INDEX_SINGLETON, EMBED_SERVICE
    
    if INDEX_SINGLETON is None or EMBED_SERVICE is None:
        raise HTTPException(status_code=503, detail='Vector index not initialized')
    
    if not text and not asset_id:
        raise HTTPException(status_code=400, detail='Provide text or asset_id')
    
    # Generate query vector
    if text:
        query_vec = EMBED_SERVICE.embed_text_stub(text)
    else:
        asset = db_s.get(Asset, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail='asset not found')
        apath = asset.path if isinstance(asset.path, str) else str(asset.path)
        query_vec = EMBED_SERVICE.embed_image_stub(apath)
    
    # Perform vector search
    matches = INDEX_SINGLETON.search(query_vec, k=k*2)  # Get more results for filtering
    
    # If person filter is specified, filter results
    if person_id is not None:
        # Verify person exists
        person = db_s.get(Person, person_id)
        if not person:
            raise HTTPException(status_code=404, detail='person not found')
        
        # Get asset IDs containing this person
        person_asset_ids = set(
            row[0] for row in 
            db_s.query(FaceDetection.asset_id)
            .filter(FaceDetection.person_id == person_id)
            .distinct()
            .all()
        )
        
        # Filter matches to only include assets with this person
        filtered_matches = [
            (asset_id, score) for asset_id, score in matches 
            if asset_id in person_asset_ids
        ][:k]  # Take only k results after filtering
        
        matches = filtered_matches
    else:
        matches = matches[:k]
    
    # Get asset details
    assets_map = {
        a.id: a for a in 
        db_s.query(Asset).filter(Asset.id.in_([mid for mid, _ in matches])).all()
    }
    
    result_items = []
    for mid, score in matches:
        aobj = assets_map.get(mid)
        result_items.append({
            'asset_id': mid,
            'score': float(score),
            'path': aobj.path if aobj else None
        })
    
    response = {
        'api_version': schemas.API_VERSION,
        'query': {'text': text, 'asset_id': asset_id},
        'k': k,
        'results': result_items
    }
    
    if person_id is not None:
        response['person_filter'] = {
            'person_id': person_id,
            'person_name': person.display_name if person else None
        }
    
    return response
