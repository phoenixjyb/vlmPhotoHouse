import sys
import types

from app.face_detection_service import (
    InsightFaceDetectionProvider,
    StubDetectionProvider,
    describe_detection_runtime,
)


def _install_fake_runtime(monkeypatch, available, session_providers):
    state = {'preload_calls': 0, 'face_analysis': None}

    class FakeSession:
        def get_providers(self):
            return list(session_providers)

    class FakeFaceAnalysis:
        def __init__(self, name, allowed_modules, providers):
            state['face_analysis'] = {
                'name': name,
                'allowed_modules': allowed_modules,
                'providers': providers,
            }
            self.models = {
                'detection': types.SimpleNamespace(session=FakeSession())
            }

        def prepare(self, ctx_id, det_size):
            state['prepare'] = {'ctx_id': ctx_id, 'det_size': det_size}

    insightface_module = types.ModuleType('insightface')
    insightface_app_module = types.ModuleType('insightface.app')
    insightface_app_module.FaceAnalysis = FakeFaceAnalysis
    insightface_module.app = insightface_app_module

    ort_module = types.ModuleType('onnxruntime')
    ort_module.__version__ = 'test-ort'
    ort_module.get_available_providers = lambda: list(available)

    def preload_dlls():
        state['preload_calls'] += 1

    ort_module.preload_dlls = preload_dlls

    monkeypatch.setitem(sys.modules, 'insightface', insightface_module)
    monkeypatch.setitem(sys.modules, 'insightface.app', insightface_app_module)
    monkeypatch.setitem(sys.modules, 'onnxruntime', ort_module)
    return state


def test_insightface_reports_prepared_cuda_session(monkeypatch):
    state = _install_fake_runtime(
        monkeypatch,
        available=('CUDAExecutionProvider', 'CPUExecutionProvider'),
        session_providers=('CUDAExecutionProvider', 'CPUExecutionProvider'),
    )

    provider = InsightFaceDetectionProvider('cuda:0')

    assert state['preload_calls'] == 1
    assert state['face_analysis']['providers'] == [
        'CUDAExecutionProvider',
        'CPUExecutionProvider',
    ]
    assert state['prepare'] == {'ctx_id': 0, 'det_size': (640, 640)}
    assert provider.effective_execution_provider == 'CUDAExecutionProvider'
    assert provider.effective_device == 'cuda:0'
    assert provider.accelerated is True


def test_insightface_reports_cpu_fallback_from_prepared_session(
    monkeypatch, caplog
):
    state = _install_fake_runtime(
        monkeypatch,
        available=('AzureExecutionProvider', 'CPUExecutionProvider'),
        session_providers=('CPUExecutionProvider',),
    )

    provider = InsightFaceDetectionProvider('cuda:0')

    assert state['preload_calls'] == 1
    assert state['face_analysis']['providers'] == ['CPUExecutionProvider']
    assert state['prepare'] == {'ctx_id': -1, 'det_size': (640, 640)}
    assert provider.effective_execution_provider == 'CPUExecutionProvider'
    assert provider.effective_device == 'cpu'
    assert provider.accelerated is False
    assert 'CUDAExecutionProvider unavailable' in caplog.text


def test_stub_runtime_description_is_explicit():
    runtime = describe_detection_runtime(StubDetectionProvider())

    assert runtime['runtime'] == 'builtin'
    assert runtime['effective_device'] == 'stub'
    assert runtime['effective_execution_provider'] == 'StubDetectionProvider'
    assert runtime['accelerated'] is False
