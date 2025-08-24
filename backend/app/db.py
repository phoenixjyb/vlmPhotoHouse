from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean, Text, Float, LargeBinary, Index, JSON
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from typing import Optional, List as _List

class Base(DeclarativeBase):
    pass

class Asset(Base):
    __tablename__ = 'assets'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    perceptual_hash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    mime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    orientation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    taken_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, index=True)
    camera_make: Mapped[Optional[str]] = mapped_column(String(64))
    camera_model: Mapped[Optional[str]] = mapped_column(String(64))
    lens: Mapped[Optional[str]] = mapped_column(String(64))
    iso: Mapped[Optional[int]] = mapped_column(Integer)
    f_stop: Mapped[Optional[float]] = mapped_column(Float)
    exposure: Mapped[Optional[str]] = mapped_column(String(32))
    focal_length: Mapped[Optional[float]] = mapped_column(Float)
    gps_lat: Mapped[Optional[float]] = mapped_column(Float)
    gps_lon: Mapped[Optional[float]] = mapped_column(Float)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())
    imported_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(16), default='active', index=True)

    embeddings = relationship('Embedding', back_populates='asset', cascade='all, delete-orphan')
    captions = relationship('Caption', back_populates='asset', cascade='all, delete-orphan')
    faces = relationship('FaceDetection', back_populates='asset', cascade='all, delete-orphan')

class Embedding(Base):
    __tablename__ = 'embeddings'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), index=True, nullable=False)
    modality: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    vector_checksum: Mapped[Optional[str]] = mapped_column(String(64))
    device: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())

    asset = relationship('Asset', back_populates='embeddings')

class Caption(Base):
    __tablename__ = 'captions'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), index=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, onupdate=func.now())

    asset = relationship('Asset', back_populates='captions')

class Person(Base):
    __tablename__ = 'persons'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    embedding_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    face_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, onupdate=func.now())

    faces = relationship('FaceDetection', back_populates='person')

class FaceDetection(Base):
    __tablename__ = 'face_detections'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), index=True, nullable=False)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_w: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_h: Mapped[float] = mapped_column(Float, nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey('persons.id', ondelete='SET NULL'), nullable=True, index=True)
    embedding_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())

    asset = relationship('Asset', back_populates='faces')
    person = relationship('Person', back_populates='faces')

class VideoSegment(Base):
    __tablename__ = 'video_segments'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), index=True, nullable=False)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    keyframe_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    embedding_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default={})
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True, default='pending')
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    progress_current: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    progress_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scheduled_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, index=True, server_default=func.now())
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, onupdate=func.now())
    started_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True, index=True)
    finished_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True, index=True)

Index('idx_task_state_priority', Task.state, Task.priority, Task.scheduled_at)
Index('idx_task_type_state', Task.type, Task.state)

Index('idx_embeddings_asset_mod', Embedding.asset_id, Embedding.modality, unique=True)

# --- Tags ---
class Tag(Base):
    __tablename__ = 'tags'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g., date|location|person|scene|custom
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())

class AssetTag(Base):
    __tablename__ = 'asset_tags'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), index=True, nullable=False)
    tag_id: Mapped[int] = mapped_column(ForeignKey('tags.id', ondelete='CASCADE'), index=True, nullable=False)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, server_default=func.now())
    Index('idx_asset_tag_unique', asset_id, tag_id, unique=True)
