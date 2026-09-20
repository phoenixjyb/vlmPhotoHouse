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
    import export_protected_videos
    import app.access.prepared_video as prepared_video
    import prepare_access_database
    from app.access import (captions, duplicates, promotion, task_recovery,
                            upload, upload_schema, upload_transport)
    for module in (app,provision_access,staging_app,prepare_access_database,export_protected_videos,prepared_video,
                   captions, duplicates, promotion, task_recovery,
                   upload, upload_schema, upload_transport):
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
        from app.access.runtime import ExistingDatabase
        from app.access import management_import
        assert Path(management_import.__file__).resolve().is_relative_to(root)
        with ExistingDatabase(recovered)() as connection:
            connection.execute("INSERT INTO persons(id,display_name,face_count) VALUES (91,'Synthetic orphan',0)")
            connection.commit()
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['backup','--database',str(recovered),
                '--out',str(data/'management-backup.sqlite')])==0
        request=data/'management-request.json';plan=data/'management-plan.json'
        request.write_text(json.dumps({'operator_account_id':applied['actor_account_id'],
            'library_id':'synthetic-family','person_ids':[91],'album_ids':[],
            'include_orphan_people':True,'include_empty_albums':False,
            'quiescence_reference':'synthetic-stopped-workers'}))
        planned=operator('plan-management','--database',recovered,'--request',request,'--out',plan)
        operator('validate','--database',recovered,'--plan',plan)
        management_args=['--database',recovered,'--plan',plan,'--backup',data/'management-backup.sqlite',
            '--reviewed-plan-digest',planned['plan_digest'],'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        reviewed=operator('review',*management_args)
        operator('apply',*management_args,'--review-digest',reviewed['review_digest'],'--all-writers-stopped')
        assert operator('receipt','--database',recovered,'--plan-id',planned['plan_id'],
            '--reviewed-plan-digest',planned['plan_digest'])['receipt_found']
        from app.access import ownership_repair
        assert Path(ownership_repair.__file__).resolve().is_relative_to(root)
        with ExistingDatabase(recovered)() as connection:
            connection.execute("INSERT INTO persons(id,display_name,face_count) VALUES (92,'Synthetic target',2)")
            connection.executemany("INSERT INTO assets(id,path,hash_sha256,status) VALUES (?,?,?,?)",[
                (93,'synthetic/visible.jpg','synthetic-hash-93','active'),
                (94,'synthetic/suppressed.jpg','synthetic-hash-94','suppressed')])
            connection.execute("INSERT INTO access_asset_libraries VALUES (93,'synthetic-family')")
            connection.executemany("INSERT INTO face_detections(id,asset_id,bbox_x,bbox_y,bbox_w,bbox_h,person_id)"
                " VALUES (?,?,0,0,1,1,92)",[(931,93),(941,94)])
            connection.commit()
        with redirect_stdout(io.StringIO()):
            assert prepare_access_database.main(['backup','--database',str(recovered),
                '--out',str(data/'repair-backup.sqlite')])==0
        request=data/'repair-request.json';plan=data/'repair-plan.json'
        request.write_text(json.dumps({'library_id':'synthetic-family',
            'operator_account_id':applied['actor_account_id'],'person_id':92,'asset_ids':[94],
            'quiescence_reference':'synthetic-stopped-workers',
            'provenance_reference':'synthetic-ownership-review'}))
        planned=operator('plan-person-repair','--database',recovered,'--request',request,'--out',plan)
        operator('validate','--database',recovered,'--plan',plan)
        repair_args=['--database',recovered,'--plan',plan,'--backup',data/'repair-backup.sqlite',
            '--reviewed-plan-digest',planned['plan_digest'],'--authority-reference','synthetic-authority',
            '--restore-reference','synthetic-restore']
        reviewed=operator('review',*repair_args)
        operator('apply',*repair_args,'--review-digest',reviewed['review_digest'],'--all-writers-stopped')
        assert operator('receipt','--database',recovered,'--plan-id',planned['plan_id'],
            '--reviewed-plan-digest',planned['plan_digest'])['receipt_found']
        with ExistingDatabase(recovered,read_only=True)() as connection:
            assert connection.execute("SELECT library_id FROM access_person_libraries WHERE person_id=92").fetchall()==[('synthetic-family',)]
            assert connection.execute("SELECT status FROM assets WHERE id=94").fetchall()==[('suppressed',)]
print(json.dumps({'package_smoke':'pass','synthetic_migration_revision':REQUIRED_REVISION,
    'asgi_checks':7,'operator_commands':19,'database_preparation_commands':9,
    'listeners_opened':False,'live_data_accessed':False}))
