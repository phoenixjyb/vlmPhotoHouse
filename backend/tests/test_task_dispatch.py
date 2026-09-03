from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, Task
from app.tasks import TaskExecutor


DISPATCHED_TASK_TYPES = (
    'phash',
    'video_probe',
    'video_keyframes',
    'video_embed',
    'video_scene_detect',
    'video_segment_embed',
)


def _executor_with_memory_database():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    executor = object.__new__(TaskExecutor)
    executor.session_factory = session_factory
    executor.settings = SimpleNamespace()
    return executor, session_factory


def test_existing_phash_and_video_handlers_are_dispatched(monkeypatch):
    executor, session_factory = _executor_with_memory_database()
    seen = []

    for task_type in DISPATCHED_TASK_TYPES:
        monkeypatch.setattr(
            executor,
            f'_handle_{task_type}',
            lambda session, task, expected=task_type: seen.append(
                (expected, task.type)
            ),
        )

    with session_factory() as session:
        for priority, task_type in enumerate(DISPATCHED_TASK_TYPES):
            session.add(
                Task(
                    type=task_type,
                    state='pending',
                    priority=priority,
                    scheduled_at=datetime.utcnow(),
                    payload_json={},
                )
            )
        session.commit()

    for _ in DISPATCHED_TASK_TYPES:
        assert executor.run_once()

    assert seen == [(task_type, task_type) for task_type in DISPATCHED_TASK_TYPES]
    with session_factory() as session:
        states = session.query(Task.type, Task.state).order_by(Task.priority).all()
    assert states == [(task_type, 'finished') for task_type in DISPATCHED_TASK_TYPES]


def test_unknown_task_type_fails_closed():
    executor, session_factory = _executor_with_memory_database()

    with session_factory() as session:
        task = Task(
            type='future_task',
            state='pending',
            priority=1,
            scheduled_at=datetime.utcnow(),
            payload_json={},
        )
        session.add(task)
        session.commit()
        task_id = task.id

    assert executor.run_once()

    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.state == 'failed'
        assert task.last_error == 'Unsupported task type: future_task'
