"""Fresh-process source-package smoke; explicit extracted root, synthetic data only."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

root=Path(sys.argv[1]).resolve(strict=True)
sys.path[:0]=[str(root/'backend'),str(root/'scripts')]
with ExitStack() as guards:
    for target in ('socket.socket.bind','socket.socket.connect','subprocess.Popen','os.system'):
        guards.enter_context(patch(target,side_effect=AssertionError('External I/O forbidden')))
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from fastapi.testclient import TestClient
    import app
    from app.main import create_app
    from app.access.runtime import RuntimeConfiguration, REQUIRED_REVISION
    import provision_access
    import staging_app
    for module in (app,provision_access,staging_app):
        assert Path(module.__file__).resolve().is_relative_to(root)
    with tempfile.TemporaryDirectory(prefix='photohouse-package-db-') as directory:
        data=Path(directory).resolve(); database=data/'synthetic.sqlite'
        engine=create_engine('sqlite:///'+str(database))
        with engine.begin() as connection:
            config=Config(); config.set_main_option('script_location',str(root/'backend/migrations'))
            config.attributes['connection']=connection
            command.upgrade(config,REQUIRED_REVISION)
        engine.dispose()
        with TestClient(create_app(),base_url='https://photohouse.test') as client:
            assert client.get('/auth/session').status_code==503
        runtime=RuntimeConfiguration(database,'https://photohouse.test',(data/'originals',),data/'derived')
        with TestClient(runtime.build_app(),base_url='https://photohouse.test') as client:
            assert client.get('/auth/session').status_code==401
            assert client.get('/assets?library=synthetic-family').status_code==401
            assert client.get('/ui').status_code==200
            assert client.get('/ui/app.js').status_code==200
            assert client.get('/ui/styles.css').status_code==200
            assert client.get('/search').status_code==403
        request=data/'owner-request.json'; plan=data/'owner-plan.json'
        request.write_text(json.dumps({'phone_login':'+12025550123','library_id':'synthetic-family'}))
        with redirect_stdout(io.StringIO()):
            assert provision_access.main(['plan-owner','--database',str(database),
                '--request',str(request),'--out',str(plan)])==0
            assert provision_access.main(['validate','--database',str(database),'--plan',str(plan)])==0
print(json.dumps({'package_smoke':'pass','synthetic_migration_revision':REQUIRED_REVISION,
    'asgi_checks':7,'operator_commands':2,'listeners_opened':False,'live_data_accessed':False}))
