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
    from fastapi.testclient import TestClient
    import app
    from app.main import create_app
    from app.access.runtime import RuntimeConfiguration, REQUIRED_REVISION
    import provision_access
    import staging_app
    import prepare_access_database
    for module in (app,provision_access,staging_app,prepare_access_database):
        assert Path(module.__file__).resolve().is_relative_to(root)
    with tempfile.TemporaryDirectory(prefix='photohouse-package-db-') as directory:
        data=Path(directory).resolve(); database=data/'synthetic.sqlite'
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['initialize','--out',str(database)])==0
            assert prepare_access_database.main(['backup','--database',str(database),
                '--out',str(data/'backup.sqlite')])==0
            assert prepare_access_database.main(['rehearse-migration','--database',str(database)])==0
        preparation_output=io.StringIO()
        with redirect_stdout(preparation_output):
            assert prepare_access_database.main(['backup','--database',str(database),
                '--out',str(data/'candidate-backup.sqlite')])==0
        reviewed=json.loads(preparation_output.getvalue())['source_snapshot_digest']
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['migrate-candidate','--database',str(database),
                '--backup',str(data/'candidate-backup.sqlite'),'--out',str(data/'candidate.sqlite'),
                '--reviewed-snapshot-digest',reviewed,'--authority-reference','synthetic-authority',
                '--quiescence-reference','synthetic-stopped-workers'])==0
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
        plan_output=io.StringIO()
        with redirect_stdout(plan_output):
            assert provision_access.main(['plan-owner','--database',str(database),
                '--request',str(request),'--out',str(plan)])==0
        plan_digest=json.loads(plan_output.getvalue())['plan_digest']
        def operator(command, *args):
            output=io.StringIO()
            with redirect_stdout(output):
                assert provision_access.main([command,*map(str,args)])==0
            return json.loads(output.getvalue())
        owner_args=['--database',database,'--plan',plan,'--backup',data/'backup.sqlite',
            '--reviewed-plan-digest',plan_digest,'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        operator('validate','--database',database,'--plan',plan)
        reviewed=operator('review',*owner_args)
        with patch('getpass.getpass',return_value='synthetic original owner password'):
            applied=operator('apply',*owner_args,'--review-digest',reviewed['review_digest'])
        preparation_output=io.StringIO()
        with redirect_stdout(preparation_output):
            assert prepare_access_database.main(['backup','--database',str(database),
                '--out',str(data/'owned-backup.sqlite')])==0
        reviewed_snapshot=json.loads(preparation_output.getvalue())['source_snapshot_digest']
        recovered=data/'recovered.sqlite'
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['migrate-candidate','--database',str(database),
                '--backup',str(data/'owned-backup.sqlite'),'--out',str(recovered),
                '--reviewed-snapshot-digest',reviewed_snapshot,'--authority-reference','synthetic-authority',
                '--quiescence-reference','synthetic-stopped-workers'])==0
            assert prepare_access_database.main(['backup','--database',str(recovered),
                '--out',str(data/'recovered-backup.sqlite')])==0
        request=data/'recovery-request.json';plan=data/'recovery-plan.json'
        request.write_text(json.dumps({'operator_account_id':applied['actor_account_id'],
            'library_id':'synthetic-family','quiescence_reference':'synthetic-stopped-workers',
            'reconciliation_reference':'synthetic-owner-history-review'}))
        planned=operator('plan-recovery','--database',recovered,'--request',request,'--out',plan)
        operator('validate-recovery','--database',recovered,'--plan',plan)
        recovery_args=['--database',recovered,'--plan',plan,'--backup',data/'recovered-backup.sqlite',
            '--reviewed-plan-digest',planned['plan_digest'],'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        reviewed=operator('review-recovery',*recovery_args)
        with patch('getpass.getpass',return_value='synthetic replacement owner password'):
            operator('apply-recovery',*recovery_args,'--review-digest',reviewed['review_digest'])
        assert operator('receipt','--database',recovered,'--plan-id',planned['plan_id'],
            '--reviewed-plan-digest',planned['plan_digest'])['receipt_found']
print(json.dumps({'package_smoke':'pass','synthetic_migration_revision':REQUIRED_REVISION,
    'asgi_checks':7,'operator_commands':9,'database_preparation_commands':8,
    'listeners_opened':False,'live_data_accessed':False}))
