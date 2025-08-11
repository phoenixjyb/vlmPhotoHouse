def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200
    data = r.json()
    assert data['ok'] is True
    assert 'profile' in data
