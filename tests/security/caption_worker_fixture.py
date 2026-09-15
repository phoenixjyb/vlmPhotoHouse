"""Synthetic-only isolated process for the actual standalone queue runner."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

root, work = Path(sys.argv[1]), Path(sys.argv[2])
mode = sys.argv[3]
migration_root = Path(sys.argv[4]) if len(sys.argv)>4 else root
work.mkdir()  # exclusively new fixture directory
sys.path.insert(0, str(root/'backend'))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from app.db import Asset, Caption, Task

database = work/'fixture.sqlite'
engine = create_engine('sqlite:///'+database.as_posix())
with engine.begin() as connection:
    cfg = Config(); cfg.set_main_option('script_location', str(migration_root/'backend/migrations'))
    cfg.attributes['connection'] = connection
    import app
    # Only fixture construction may use migration metadata outside the artifact.
    # Remove the fallback package path before importing or starting worker code.
    with patch.object(app, '__path__', [str(root/'backend/app'), str(migration_root/'backend/app')]):
        command.upgrade(cfg, 'head')
with Session(engine) as session:
    asset = Asset(path='synthetic-never-read.jpg', hash_sha256='fixture', status='active', mime='image/jpeg')
    session.add(asset); session.flush()
    caption = Caption(asset_id=asset.id, text='Family edit' if mode=='edited' else 'Old synthetic AI',
                      model='old', user_edited=mode=='edited')
    task = Task(type='caption', state='pending', priority=100,
                payload_json={'asset_id':asset.id, 'replace_generated':True})
    other = Task(type='embed', state='pending', priority=1, payload_json={})
    from datetime import datetime, timedelta
    future = Task(type='caption', state='pending', priority=0,
                  scheduled_at=datetime.utcnow()+timedelta(days=1), payload_json={})
    session.add_all([caption, other, future])
    if mode != 'idle': session.add(task)
    session.commit()
    ids = (asset.id, caption.id, task.id if mode != 'idle' else None, other.id, future.id)
engine.dispose()

environment = work/'reviewed.json'; environment.write_text('{"CAPTION_WORD_LIMIT":"0","CAPTION_POLICY_MAX_RETRIES":"0"}')
if mode=='tags': environment.write_text('{"CAPTION_WORD_LIMIT":"0","CAPTION_AUTO_TAG_ENABLE":"true"}')
spec = importlib.util.spec_from_file_location('fixture_worker', root/'scripts/run_caption_worker.py')
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
stopfile = work/'stop'
args = worker.argparse.Namespace(database=str(database), derived=str(work), temporary=str(work),
    stop_file=str(stopfile), caption_url='http://127.0.0.1:1', environment_json=str(environment),
    expected_revision='d8e5b2f7a904', execute=True, legacy_worker_stopped=mode!='unconfirmed', once=mode!='drain')
generated = 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。'
calls = []
class Provider:
    def get_model_name(self): return 'unready' if mode=='unready' else 'qwen3-vl-http-synthetic'
    def generate_caption(self, image, **kwargs):
        calls.append(image.size)
        if mode=='retry': raise ConnectionError('Synthetic service unavailable')
        if mode=='drain': stopfile.touch()
        return generated

configure = worker.configure_process
with ExitStack() as guards:
    for target in ('socket.socket.connect','socket.socket.bind','subprocess.Popen','os.system'):
        guards.enter_context(patch(target, side_effect=AssertionError('External I/O forbidden')))
    def configured(*values):
        configure(*values)
        from app import tasks, caption_service
        from app import config
        from PIL import Image
        with patch.object(config, 'load_dotenv') as dotenv, patch.object(config.Path, 'exists', return_value=True):
            config._load_local_env_files()
            dotenv.assert_not_called()
        assert config.get_settings().caption_provider=='http'
        assert not config.get_settings().enable_inline_worker
        guards.enter_context(patch.object(tasks, 'EmbeddingService', side_effect=AssertionError('No embedding initialization')))
        guards.enter_context(patch.object(tasks, 'InMemoryVectorIndex', side_effect=AssertionError('No index initialization')))
        guards.enter_context(patch.object(tasks.TaskExecutor, '_maybe_enqueue_dim_backfill', side_effect=AssertionError('No backfill')))
        guards.enter_context(patch.object(tasks.TaskExecutor, '_load_caption_image', return_value=Image.new('RGB',(32,32),'red')))
        guards.enter_context(patch.object(caption_service, 'get_caption_provider', return_value=Provider()))
    guards.enter_context(patch.object(worker, 'configure_process', side_effect=configured))
    if mode in ('unready','unconfirmed'):
        try: worker.run(args)
        except worker.Refused: pass
        else: raise AssertionError('Expected fail-closed startup')
    else:
        result = worker.run(args)
        assert result['drained']

with sqlite3.connect(database) as db:
    assert db.execute('SELECT state FROM tasks WHERE id=?',(ids[3],)).fetchone()==('pending',)
    assert db.execute('SELECT state FROM tasks WHERE id=?',(ids[4],)).fetchone()==('pending',)
    assert db.execute('SELECT count(*) FROM tasks').fetchone()[0]==(2 if mode=='idle' else 3)
    assert db.execute('SELECT version_num FROM alembic_version').fetchone()==('d8e5b2f7a904',)
    if mode=='drain':
        assert db.execute('SELECT state FROM tasks WHERE id=?',(ids[2],)).fetchone()==('finished',)
        assert db.execute('SELECT superseded FROM captions WHERE id=?',(ids[1],)).fetchone()==(1,)
        assert db.execute('SELECT text FROM captions WHERE superseded=0').fetchone()==(generated,)
    if mode=='edited':
        assert not calls
        assert db.execute('SELECT text FROM captions').fetchall()==[('Family edit',)]
        assert db.execute('SELECT state FROM tasks WHERE id=?',(ids[2],)).fetchone()==('finished',)
    if mode=='retry':
        assert db.execute('SELECT state,retry_count FROM tasks WHERE id=?',(ids[2],)).fetchone()==('pending',1)
    if mode=='tags':
        assert db.execute('SELECT count(*) FROM asset_tags').fetchone()[0] > 0
        assert db.execute('SELECT state FROM tasks WHERE id=?',(ids[2],)).fetchone()==('finished',)
    else:
        assert db.execute('SELECT count(*) FROM asset_tags').fetchone()[0] == 0
    if mode in ('unready','unconfirmed'):
        assert not calls
        assert db.execute('SELECT state FROM tasks WHERE id=?',(ids[2],)).fetchone()==('pending',)
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
assert 'app.main' not in sys.modules and 'app.dependencies' not in sys.modules and 'torch' not in sys.modules
if mode=='idle':
    # The optional mode must not change the default mixed executor's claim path.
    from app import tasks, config
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    engine = create_engine('sqlite:///'+database.as_posix())
    try:
        with patch.object(tasks, 'EmbeddingService', return_value=SimpleNamespace(dim=512)) as embedding, \
             patch.object(tasks, 'InMemoryVectorIndex'), patch.object(tasks, 'FaissVectorIndex'):
            mixed = tasks.TaskExecutor(sessionmaker(bind=engine), config.get_settings())
            embedding.assert_called_once()
            with Session(engine) as session:
                claimed = mixed._claim_next_task(session)
                assert claimed.type=='embed' and claimed.id==ids[3]
    finally:
        engine.dispose()
print(json.dumps({'fixture':'pass','mode':mode,'real_inference':False}))
