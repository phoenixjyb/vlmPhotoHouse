from app.main import reinit_executor_for_tests, SessionLocal
from app.db import Asset, VideoSegment, Task

def main():
    reinit_executor_for_tests()
    with SessionLocal() as s:
        v = s.query(Asset).filter(Asset.mime.like('video%')).order_by(Asset.id.desc()).first()
        if not v:
            print("no video asset found")
            return
        segs = s.query(VideoSegment).filter_by(asset_id=v.id).count()
        pending = s.query(Task).filter_by(state='pending').count()
        print(f"asset_id={v.id} path={v.path} duration={v.duration_sec} fps={v.fps} segments={segs} pending_tasks={pending}")

if __name__ == '__main__':
    main()
