from fastapi import APIRouter, Depends, Body, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from ..db import Person, FaceDetection, Asset, Task
from ..main import get_db, DERIVED_PATH  # reuse existing get_db and path constants
from .. import schemas

router = APIRouter()

# Helper

def _recompute_face_counts(db_s: Session, person_ids):
    if not person_ids:
        return
    counts = (
        db_s.query(FaceDetection.person_id, func.count(FaceDetection.id))
        .filter(FaceDetection.person_id.in_(person_ids))
        .group_by(FaceDetection.person_id).all()
    )
    count_map = {pid: c for pid, c in counts}
    persons = db_s.query(Person).filter(Person.id.in_(person_ids)).all()
    for p in persons:
        p.face_count = count_map.get(p.id, 0)  # type: ignore[attr-defined]

@router.get('/persons', response_model=schemas.PersonsResponse)
def list_persons(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), include_faces: bool = Query(False), db_s: Session = Depends(get_db)):
    q = db_s.query(Person)
    total = q.count()
    persons = q.order_by(Person.id.asc()).offset((page-1)*page_size).limit(page_size).all()
    result = []
    for p in persons:
        item = {'id': p.id, 'display_name': p.display_name, 'face_count': p.face_count}
        if include_faces:
            faces = db_s.query(FaceDetection).filter(FaceDetection.person_id==p.id).limit(5).all()
            item['sample_faces'] = [f.id for f in faces]
        result.append(item)
    return {'api_version': schemas.API_VERSION, 'page': page, 'page_size': page_size, 'total': total, 'persons': result}

@router.get('/faces', response_model=schemas.FacesResponse)
def list_faces(person_id: int | None = Query(None), unassigned: bool = Query(False), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db_s: Session = Depends(get_db)):
    q = db_s.query(FaceDetection)
    if person_id is not None and unassigned:
        raise HTTPException(status_code=400, detail='Specify either person_id or unassigned, not both')
    if person_id is not None:
        q = q.filter(FaceDetection.person_id==person_id)
    if unassigned:
        q = q.filter(FaceDetection.person_id==None)
    total = q.count()
    faces = q.order_by(FaceDetection.id.asc()).offset((page-1)*page_size).limit(page_size).all()
    return {'api_version': schemas.API_VERSION, 'page': page, 'page_size': page_size, 'total': total, 'faces': [ {'id': f.id, 'asset_id': f.asset_id, 'person_id': f.person_id} for f in faces]}

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
    _recompute_face_counts(db_s, [person.id])
    db_s.commit()
    return {'face_id': face.id, 'person_id': person.id, 'new_person_created': created}

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
    _recompute_face_counts(db_s, [target_person_id])
    db_s.commit()
    return {'assigned': len(faces), 'person_id': target_person_id, 'new_person_created': created}

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
    db_s.commit()
    return {'target_id': target.id, 'merged_sources': [p.id for p in sources], 'moved_faces': len(faces), 'face_count': target.face_count}

@router.post('/persons/{person_id}/delete')
def delete_person(person_id: int, db_s: Session = Depends(get_db)):
    person = db_s.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail='person not found')
    faces = db_s.query(FaceDetection).filter(FaceDetection.person_id==person.id).all()
    for f in faces:
        f.person_id = None  # type: ignore[attr-defined]
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
