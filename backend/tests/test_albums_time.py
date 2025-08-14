import datetime, uuid
from fastapi.testclient import TestClient
from app.main import SessionLocal
from app.db import Asset

# Helper to insert asset with taken_at

def _add_asset(path: str, taken_at: datetime.datetime):
    with SessionLocal() as s:
        a = Asset(path=path, hash_sha256=path, taken_at=taken_at)
        s.add(a)
        s.commit()
        return a.id

def test_time_albums_basic(client: TestClient):
    # Create assets across two years and months
    base = datetime.datetime(2023,5,10,12,0,0)
    ids = []
    prefix = f"tester_{uuid.uuid4().hex}"
    def p(label): return f"{prefix}/{label}_{uuid.uuid4().hex}.jpg"
    ids.append(_add_asset(p('a1'), base))
    ids.append(_add_asset(p('a2'), base + datetime.timedelta(days=1)))  # 2023-05-11
    ids.append(_add_asset(p('a3'), datetime.datetime(2024,1,2, 9,0,0)))
    ids.append(_add_asset(p('a4'), datetime.datetime(2024,1,2, 10,0,0)))
    ids.append(_add_asset(p('a5'), datetime.datetime(2024,2,15, 8,30,0)))

    r = client.get(f'/albums/time?path_prefix={prefix}')
    assert r.status_code == 200, r.text
    js = r.json()
    years = {y['year']: y for y in js['years']}
    assert 2023 in years and 2024 in years
    assert years[2023]['count'] == 2
    assert years[2024]['count'] == 3
    m2024 = {m['month']: m for m in years[2024]['months']}
    assert 1 in m2024 and 2 in m2024
    jan_days = {d['day']: d for d in m2024[1]['days']}
    assert jan_days[2]['count'] == 2
    feb_days = {d['day']: d for d in m2024[2]['days']}
    assert feb_days[15]['count'] == 1

