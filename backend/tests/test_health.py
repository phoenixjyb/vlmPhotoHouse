def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200
    data = r.json()
    assert data['ok'] is True
    assert 'profile' in data


def test_health_reports_effective_face_detection_runtime(client, monkeypatch):
    import app.face_detection_service as detection_module

    class CudaDetector:
        runtime_name = 'onnxruntime'
        runtime_version = 'test-version'
        requested_device = 'cuda:0'
        effective_device = 'cuda:0'
        available_execution_providers = (
            'CUDAExecutionProvider',
            'CPUExecutionProvider',
        )
        execution_providers = ('CUDAExecutionProvider', 'CPUExecutionProvider')
        effective_execution_provider = 'CUDAExecutionProvider'
        accelerated = True

    monkeypatch.setattr(
        detection_module,
        'get_face_detection_provider',
        lambda: CudaDetector(),
    )

    response = client.get('/health')

    assert response.status_code == 200
    runtime = response.json()['face']['detect_runtime']
    assert runtime == {
        'runtime': 'onnxruntime',
        'runtime_version': 'test-version',
        'requested_device': 'cuda:0',
        'effective_device': 'cuda:0',
        'available_execution_providers': [
            'CUDAExecutionProvider',
            'CPUExecutionProvider',
        ],
        'execution_providers': [
            'CUDAExecutionProvider',
            'CPUExecutionProvider',
        ],
        'effective_execution_provider': 'CUDAExecutionProvider',
        'accelerated': True,
    }
