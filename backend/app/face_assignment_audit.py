from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .db import FaceAssignmentEvent, FaceDetection

def _ensure_audit_table(session: Session) -> bool:
    # Inspect the caller's connection, never a cached result from another DB and
    # never a second engine connection that can interfere with its transaction.
    if not inspect(session.connection()).has_table('face_assignment_events'):
        raise ValueError('Migrated face assignment audit schema required')
    return True


def record_face_assignment_event(
    session: Session,
    *,
    source: str,
    old_person_id: int | None,
    new_person_id: int | None,
    old_label_source: str | None,
    new_label_source: str | None,
    old_label_score: float | None,
    new_label_score: float | None,
    face: FaceDetection | None = None,
    face_id: int | None = None,
    asset_id: int | None = None,
    reason: str | None = None,
    task_id: int | None = None,
    actor: str | None = None,
) -> bool:
    """Persist a single face-assignment change event.

    Returns True if an event was created. Returns False for no-op updates.
    """
    # Keep history focused on assignment provenance changes.
    # Pure score refreshes for the same person/source are treated as no-op.
    if old_person_id == new_person_id and old_label_source == new_label_source:
        return False
    if not _ensure_audit_table(session):
        return False

    if face is not None:
        if face_id is None:
            face_id = int(face.id)
        if asset_id is None:
            asset_id = int(face.asset_id)

    event = FaceAssignmentEvent(
        face_id=face_id,
        asset_id=asset_id,
        old_person_id=old_person_id,
        new_person_id=new_person_id,
        old_label_source=old_label_source,
        new_label_source=new_label_source,
        old_label_score=old_label_score,
        new_label_score=new_label_score,
        source=source,
        reason=reason,
        task_id=task_id,
        actor=actor,
    )
    session.add(event)
    return True
