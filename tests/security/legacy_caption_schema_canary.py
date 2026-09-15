"""Actual installed handler + ORM against an isolated canary copy, fake inference.

Does not run the queue, TaskExecutor initialization, app.main, models or servers.
Only use after fullsize_provisioning_canary on its private owner-canary.sqlite.
"""
from contextlib import ExitStack, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import types
import uuid
from unittest.mock import patch

legacy, database, work = (Path(arg).resolve(strict=True) for arg in sys.argv[1:4])
def phase(name):
    print(json.dumps({'phase':name,'torch_imported':'torch' in sys.modules}),file=sys.stderr,flush=True)
phase('source-preflight')
assert database == work/'owner-canary.sqlite'
with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as check:
    check.execute('PRAGMA query_only=ON')
    assert check.execute('SELECT version_num FROM alembic_version').fetchall() == [('d8e5b2f7a904',)]
    assert check.execute('SELECT count(*) FROM access_accounts WHERE state != "disabled"').fetchone()[0] == 0
    assert check.execute('SELECT count(*) FROM access_libraries WHERE state != "closed"').fetchone()[0] == 0
    task_counts = check.execute('SELECT state,count(*) FROM tasks GROUP BY state ORDER BY state').fetchall()
    author = check.execute("SELECT id FROM access_accounts WHERE phone_login='+12025550199'").fetchone()[0]

dotenv = types.ModuleType('dotenv'); dotenv.load_dotenv = lambda *a, **k: None
sys.path.insert(0, str(legacy/'backend'))
with ExitStack() as guards:
    guards.enter_context(patch.dict(sys.modules, {'dotenv': dotenv}))
    guards.enter_context(patch.dict(os.environ, {
        'DATABASE_URL':'sqlite:///'+database.as_posix(), 'VLM_DATA_ROOT':str(work/'scratch'),
        'DERIVED_PATH':str(work/'scratch'/'derived'), 'CUDA_VISIBLE_DEVICES':'',
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','CAPTION_WORD_LIMIT':'0',
        'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1',
        'CAPTION_PROMPT':'Synthetic schema compatibility check', 'CAPTION_AUTO_TAG_ENABLE':'false',
        'CAPTION_ENABLE_STUB_FALLBACK':'false'}))
    for name in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
        guards.enter_context(patch(name,side_effect=AssertionError('External I/O forbidden')))
    connect = sqlite3.connect
    def only_canary(path, *args, **kwargs):
        assert path == ':memory:' or Path(path).resolve() == database, 'Unexpected database access'
        return connect(path, *args, **kwargs)
    guards.enter_context(patch('sqlite3.connect', side_effect=only_canary))
    guards.enter_context(patch('sqlite3.dbapi2.connect', side_effect=only_canary))
    phase('sqlalchemy-import')
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    phase('orm-import')
    from app.db import Asset, Caption, Task
    phase('task-handler-import')
    from app.tasks import TaskExecutor
    import app.tasks as tasks
    import app.caption_service as captions
    from PIL import Image
    phase('imports-complete')
    assert Path(tasks.__file__).resolve() == legacy/'backend'/'app'/'tasks.py'
    assert 'app.main' not in sys.modules and 'app.dependencies' not in sys.modules
    generated = 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。'
    calls = []
    class FakeProvider:
        def generate_caption(self, image, **kwargs):
            calls.append(image.size); return generated
        def get_model_name(self): return 'qwen3-vl-http-synthetic-schema-check'
    guards.enter_context(patch.object(captions, 'get_caption_provider', return_value=FakeProvider()))
    engine = create_engine('sqlite:///'+database.as_posix())
    try:
        phase('fixture-and-handler')
        with Session(engine) as session:
            session.execute(text('PRAGMA foreign_keys=ON'))
            fixture_id = 'synthetic-' + uuid.uuid4().hex
            asset = Asset(path=fixture_id+'.jpg', hash_sha256=fixture_id, mime='image/jpeg', status='active')
            session.add(asset);session.commit()
            previous = Caption(asset_id=asset.id,text='synthetic old AI',model='synthetic-old',user_edited=False)
            session.add(previous);session.commit()
            session.execute(text('''INSERT INTO access_stories
                (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
                VALUES (:story,:asset,'synthetic-owner-qualification',:author,1,'','Our story 我们的故事','mixed','',1,1,0)'''),
                {'story':fixture_id,'asset':asset.id,'author':author})
            session.execute(text('''INSERT INTO access_story_revisions
                VALUES (:story,1,:author,:mutation,:digest,'','Our story 我们的故事','mixed','',1,0)'''),
                {'story':fixture_id,'author':author,'mutation':fixture_id,'digest':'0'*64});session.commit()
            story_before=session.execute(text('SELECT * FROM access_stories')).fetchall()
            history_before=session.execute(text('SELECT * FROM access_story_revisions')).fetchall()
            executor=TaskExecutor.__new__(TaskExecutor)
            executor._load_caption_image=lambda asset:Image.new('RGB',(32,32),'red')
            task=Task(type='caption',state='pending',payload_json={'asset_id':asset.id,'replace_generated':True})
            result=executor._handle_caption(session,task)
            assert result.text==generated and calls==[(32,32)]
            session.refresh(previous);assert previous.superseded
            result.user_edited=True;result.text='Synthetic family edit';session.commit();calls.clear()
            skipped=executor._handle_caption(session,task)
            assert skipped.text=='Synthetic family edit' and not calls
            assert session.execute(text('SELECT * FROM access_stories')).fetchall()==story_before
            assert session.execute(text('SELECT * FROM access_story_revisions')).fetchall()==history_before
            assert session.execute(text('SELECT state,count(*) FROM tasks GROUP BY state ORDER BY state')).fetchall()==task_counts
            assert session.execute(text('SELECT version_num FROM alembic_version')).fetchall()==[('d8e5b2f7a904',)]
            assert session.execute(text('PRAGMA foreign_key_check')).fetchone() is None
    finally: engine.dispose()
    print(json.dumps({'caption_schema_canary':'pass','actual_installed_handler':True,
        'tasks_sha256':hashlib.sha256((legacy/'backend'/'app'/'tasks.py').read_bytes()).hexdigest(),
        'ai_refresh':True,'user_edit_preserved':True,'stories_preserved':True,'queue_unchanged':True,
        'real_inference':False,'queue_runner_started':False,'activated':False}))
