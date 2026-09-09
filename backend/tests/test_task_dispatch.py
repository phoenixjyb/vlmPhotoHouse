from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from PIL import Image

from app.caption_service import CaptionServiceTransientError
from app.db import Asset, Base, Caption, Task
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


def test_caption_transport_failure_retries_then_dead_letters_without_false_success(
    monkeypatch,
):
    executor, session_factory = _executor_with_memory_database()
    executor.settings = SimpleNamespace(
        max_task_retries=2,
        retry_backoff_base_seconds=0,
        retry_backoff_cap_seconds=0,
        retry_backoff_jitter=0,
    )

    class FailingProvider:
        def generate_caption(self, image, prompt=None):
            raise CaptionServiceTransientError('caption service unavailable')

        def get_model_name(self):
            return 'unreachable-caption-service'

    monkeypatch.setenv('CAPTION_ENABLE_STUB_FALLBACK', 'false')
    monkeypatch.setattr(
        'app.caption_service.get_caption_provider',
        lambda: FailingProvider(),
    )
    monkeypatch.setattr(
        executor,
        '_load_caption_image',
        lambda asset: Image.new('RGB', (32, 32)),
    )

    with session_factory() as session:
        asset = Asset(
            path='/library/unavailable-caption.jpg',
            hash_sha256='a' * 64,
            mime='image/jpeg',
        )
        session.add(asset)
        session.flush()
        task = Task(
            type='caption',
            state='pending',
            priority=1,
            scheduled_at=datetime.utcnow(),
            payload_json={'asset_id': asset.id},
        )
        session.add(task)
        session.commit()
        asset_id = asset.id
        task_id = task.id

    assert executor.run_once()

    with session_factory() as session:
        task = session.get(Task, task_id)
        asset = session.get(Asset, asset_id)
        assert task is not None
        assert asset is not None
        assert task.state == 'pending'
        assert task.retry_count == 1
        assert task.last_error == 'caption service unavailable'
        assert task.finished_at is None
        assert asset.caption_processed is False
        assert asset.caption_error_last == 'caption service unavailable'
        assert session.query(Caption).filter(Caption.asset_id == asset_id).count() == 0

    assert executor.run_once()

    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.state == 'dead'
        assert task.retry_count == 2
        assert task.last_error == 'caption service unavailable'
        assert task.finished_at is not None
        assert session.query(Caption).filter(Caption.asset_id == asset_id).count() == 0


def test_dim_backfill_does_not_reenqueue_previously_attempted_assets():
    executor, session_factory = _executor_with_memory_database()
    executor._last_dim_backfill_scan = 0.0
    executor._dim_backfill_interval = 0

    with session_factory() as session:
        attempted = Asset(
            path='/library/attempted.jpg',
            hash_sha256='b' * 64,
            mime='image/jpeg',
        )
        fresh = Asset(
            path='/library/fresh.jpg',
            hash_sha256='c' * 64,
            mime='image/jpeg',
        )
        video = Asset(
            path='/library/clip.mp4',
            hash_sha256='e' * 64,
            mime='video/mp4',
        )
        suppressed = Asset(
            path='/library/suppressed.jpg',
            hash_sha256='f' * 64,
            mime='image/jpeg',
            status='suppressed',
        )
        session.add_all([attempted, fresh, video, suppressed])
        session.flush()
        session.add(
            Task(
                type='dim_backfill',
                state='finished',
                payload_json={'asset_id': attempted.id},
            )
        )
        session.commit()
        fresh_id = fresh.id

    with session_factory() as session:
        executor._maybe_enqueue_dim_backfill(session)

    with session_factory() as session:
        generated = session.query(Task).filter(
            Task.type == 'dim_backfill',
            Task.state == 'pending',
        ).all()
        assert [task.payload_json['asset_id'] for task in generated] == [fresh_id]

        generated[0].state = 'finished'
        session.commit()

    executor._last_dim_backfill_scan = 0.0
    with session_factory() as session:
        executor._maybe_enqueue_dim_backfill(session)
        assert session.query(Task).filter(Task.type == 'dim_backfill').count() == 2


def test_dim_backfill_missing_source_is_not_silent_success(tmp_path):
    executor, session_factory = _executor_with_memory_database()
    executor.settings = SimpleNamespace(
        max_task_retries=1,
        retry_backoff_base_seconds=0,
        retry_backoff_cap_seconds=0,
        retry_backoff_jitter=0,
    )

    with session_factory() as session:
        asset = Asset(
            path=str(tmp_path / 'missing.jpg'),
            hash_sha256='d' * 64,
            mime='image/jpeg',
        )
        session.add(asset)
        session.flush()
        task = Task(
            type='dim_backfill',
            state='pending',
            priority=1,
            scheduled_at=datetime.utcnow(),
            payload_json={'asset_id': asset.id},
        )
        session.add(task)
        session.commit()
        task_id = task.id

    assert executor.run_once()

    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.state == 'dead'
        assert task.retry_count == 1
        assert task.last_error is not None
        assert task.last_error.startswith('dimension source missing:')
