"""Tests for caption service integration."""

import pytest
from PIL import Image
import numpy as np
from unittest.mock import patch, MagicMock

from app.caption_service import (
    _build_caption_provider,
    get_caption_provider,
    HTTPCaptionProvider,
    StubCaptionProvider,
    LlavaNextCaptionProvider,
    Qwen2VLCaptionProvider,
    BLIP2CaptionProvider,
)
from app.caption_policy import CHINESE_POLICY_TERMS


def test_http_caption_provider_sends_prompt(monkeypatch, tmp_path):
    calls = []

    class FakeResponse:
        status_code = 200
        text = ''

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            return FakeResponse({
                'status': 'healthy',
                'active_provider': 'qwen3-vl',
                'model_cache_ready': True,
            })

        def post(self, url, files, data=None):
            calls.append({'url': url, 'data': data})
            return FakeResponse({'caption': 'A detailed caption.'})

    monkeypatch.setattr('app.caption_service.httpx.Client', FakeClient)
    monkeypatch.setattr('app.caption_service._caption_tmp_dir', lambda: str(tmp_path))

    provider = HTTPCaptionProvider('http://127.0.0.1:8102')
    prompt = 'Describe every visible device factually.'
    result = provider.generate_caption(Image.new('RGB', (32, 32)), prompt=prompt)

    assert result == 'A detailed caption.'
    assert provider.get_model_name() == 'qwen3-vl-http'
    assert calls == [{
        'url': 'http://127.0.0.1:8102/caption',
        'data': {'prompt': prompt},
    }]


def test_http_caption_provider_translates_with_reviewed_terms(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        text = ''

        def json(self):
            return {'translation': 'ZH-CN: 一位成人手持一部手机。'}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            return FakeResponse()

        def post(self, url, json):
            calls.append({'url': url, 'json': json})
            return FakeResponse()

    monkeypatch.setattr('app.caption_service.httpx.Client', FakeClient)
    provider = HTTPCaptionProvider('http://127.0.0.1:8102')

    result = provider.translate_caption('A person holds a phone.', avoid_terms=['可能', '拍摄'])

    assert result == '一位成人手持一部手机。'
    assert calls == [{
        'url': 'http://127.0.0.1:8102/translate',
        'json': {
            'text': 'A person holds a phone.',
            'source_lang': 'en',
            'target_lang': 'zh-CN',
            'style': 'photo caption',
            'avoid_terms': ['可能', '拍摄'],
        },
    }]


def test_get_caption_provider_default():
    """Test that default configuration returns StubCaptionProvider."""
    from types import SimpleNamespace

    test_settings = SimpleNamespace(
        caption_provider='stub',
        caption_device='cpu',
        run_mode='tests',
    )
    get_caption_provider.cache_clear()
    with patch('app.config.settings', test_settings):
        provider = get_caption_provider()
    get_caption_provider.cache_clear()
    assert isinstance(provider, StubCaptionProvider)


def test_stub_caption_provider():
    """Test StubCaptionProvider functionality."""
    provider = StubCaptionProvider()
    
    # Create a dummy image
    image = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
    
    caption = provider.generate_caption(image)
    assert isinstance(caption, str)
    assert len(caption) > 0
    assert 'heuristic' in caption.lower() or 'photo' in caption.lower()
    
    model_name = provider.get_model_name()
    assert model_name == 'stub-heuristic'


@pytest.mark.parametrize('provider_name,expected_class', [
    ('stub', StubCaptionProvider),
    ('llava-next', LlavaNextCaptionProvider),
    ('qwen2.5-vl', HTTPCaptionProvider),
    ('blip2', BLIP2CaptionProvider),
])
def test_provider_selection(provider_name, expected_class, monkeypatch):
    """Test that provider selection works correctly."""
    from types import SimpleNamespace

    settings = SimpleNamespace(
        caption_external_dir='',
        caption_service_url='http://127.0.0.1:8102',
        caption_model='auto',
        run_mode='tests',
    )
    monkeypatch.delenv('CAPTION_EXTERNAL_DIR', raising=False)
    response = MagicMock(status_code=503)
    client = MagicMock()
    client.__enter__.return_value.get.return_value = response
    with patch('app.config.get_settings', return_value=settings), \
         patch('app.caption_service.httpx.Client', return_value=client):
        provider = _build_caption_provider(provider_name, 'cpu')

    assert isinstance(provider, expected_class)


def test_caption_task_integration():
    """Test that caption task can use the new service."""
    from app.tasks import TaskExecutor
    from app.db import Task, Caption, Asset
    from sqlalchemy.orm import Session
    from unittest.mock import Mock
    
    # Mock session and objects
    session = Mock(spec=Session)
    task = Mock(spec=Task)
    asset = Mock(spec=Asset)
    
    task.payload_json = {'asset_id': 1}
    asset.path = '/fake/path/test_image.jpg'
    asset.mime = 'image/jpeg'
    session.get.return_value = asset
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    
    executor = TaskExecutor()
    
    # Mock PIL Image loading and caption service
    with patch('PIL.Image.open') as mock_open, \
         patch('app.caption_service.get_caption_provider') as mock_provider:
        
        # Create mock image
        mock_image = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
        mock_open.return_value.convert.return_value = mock_image
        
        # Create mock provider
        mock_caption_provider = Mock()
        english = ' '.join(['adult'] + ['visible'] * 59)
        mock_caption_provider.generate_caption.return_value = (
            f'EN: {english}\n\nZH-CN: 一位成人站在可见的建筑旁。'
        )
        mock_caption_provider.get_model_name.return_value = 'test-model'
        mock_provider.return_value = mock_caption_provider
        
        # Test caption generation
        result = executor._handle_caption(session, task)
        
        # Verify calls
        mock_provider.assert_called_once()
        mock_caption_provider.generate_caption.assert_called_once()
        _, caption_kwargs = mock_caption_provider.generate_caption.call_args
        assert 'Aim for about 70 to 100 English words' in caption_kwargs['prompt']
        assert 'over an exact word count' in caption_kwargs['prompt']
        assert 'ZH-CN: ...' in caption_kwargs['prompt']
        assert 'do not guess the brand, model' in caption_kwargs['prompt']
        assert 'Avoid unsupported inference' in caption_kwargs['prompt']
        session.add.assert_called_once()
        added_caption = session.add.call_args.args[0]
        assert added_caption.model == 'test-model|bilingual-en-zh-cn'
        assert added_caption.model_version == 'bilingual-v1'
        session.commit.assert_called_once()


def test_caption_task_retries_once_for_invalid_bilingual_output():
    """A format miss gets one corrective retry before the task is failed closed."""
    from app.tasks import TaskExecutor
    from app.db import Task, Caption, Asset
    from sqlalchemy.orm import Session
    from unittest.mock import Mock

    session = Mock(spec=Session)
    task = Mock(spec=Task)
    asset = Mock(spec=Asset)
    task.payload_json = {'asset_id': 1}
    asset.path = '/fake/path/test_image.jpg'
    asset.mime = 'image/jpeg'
    session.get.return_value = asset
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    english = ' '.join(['adult'] + ['visible'] * 59)
    valid = f'EN: {english}\n\nZH-CN: 一位成人站在可见的建筑旁。'
    provider = Mock()
    provider.generate_caption.side_effect = ['EN: incomplete output', valid]
    provider.get_model_name.return_value = 'test-model'

    with patch('PIL.Image.open') as image_open, \
         patch('app.caption_service.get_caption_provider', return_value=provider):
        image_open.return_value.convert.return_value = Image.new('RGB', (32, 32))
        result = TaskExecutor()._handle_caption(session, task)

    assert result is not None
    assert provider.generate_caption.call_count == 2
    retry_prompt = provider.generate_caption.call_args_list[1].kwargs['prompt']
    assert 'CORRECTION REQUIRED' in retry_prompt
    assert 'Previous validation issues: format.' in retry_prompt
    assert session.add.call_args.args[0].model == 'test-model|bilingual-en-zh-cn'


def test_caption_task_uses_second_correction_for_remaining_policy_issue():
    from app.tasks import TaskExecutor
    from app.db import Task, Caption, Asset
    from sqlalchemy.orm import Session
    from unittest.mock import Mock

    session = Mock(spec=Session)
    task = Mock(spec=Task)
    asset = Mock(spec=Asset)
    task.payload_json = {'asset_id': 1}
    asset.path = '/fake/path/test_image.jpg'
    asset.mime = 'image/jpeg'
    session.get.return_value = asset
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    neutral_english = ' '.join(['adult'] + ['visible'] * 59)
    policy_english = ' '.join(['adult', 'capturing'] + ['visible'] * 58)
    provider = Mock()
    provider.generate_caption.side_effect = [
        f'EN: {policy_english}\n\nZH-CN: 一位成人正在拍摄可见的建筑。',
        f'EN: {neutral_english}\n\nZH-CN: 一位成人正在拍摄可见的建筑。',
        f'EN: {neutral_english}\n\nZH-CN: 一位成人站在可见的建筑旁。',
    ]
    provider.get_model_name.return_value = 'test-model'

    with patch('PIL.Image.open') as image_open, \
         patch('app.caption_service.get_caption_provider', return_value=provider):
        image_open.return_value.convert.return_value = Image.new('RGB', (32, 32))
        result = TaskExecutor()._handle_caption(session, task)

    assert result is not None
    assert provider.generate_caption.call_count == 3
    second_retry_prompt = provider.generate_caption.call_args_list[2].kwargs['prompt']
    assert 'Previous validation issues: chinese_policy.' in second_retry_prompt
    assert '<rejected_caption>' in second_retry_prompt
    assert 'ZH-CN: 一位成人正在拍摄可见的建筑。' in second_retry_prompt
    assert session.add.call_args.args[0].model == 'test-model|bilingual-en-zh-cn'


def test_caption_task_retranslates_chinese_without_repeating_visual_inference():
    from app.tasks import TaskExecutor
    from app.db import Task, Caption, Asset
    from sqlalchemy.orm import Session
    from unittest.mock import Mock

    session = Mock(spec=Session)
    task = Mock(spec=Task)
    asset = Mock(spec=Asset)
    task.payload_json = {'asset_id': 1}
    asset.path = '/fake/path/test_image.jpg'
    asset.mime = 'image/jpeg'
    session.get.return_value = asset
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    class TranslationProvider:
        supports_text_translation = True

        def __init__(self):
            self.generation_calls = 0
            self.translation_calls = []

        def generate_caption(self, image, prompt=None):
            self.generation_calls += 1
            return 'EN: A person holds a phone.\n\nZH-CN: 一位成人可能正在拍摄。'

        def translate_caption(self, english, avoid_terms=None):
            self.translation_calls.append((english, avoid_terms))
            return '一位成人手持一部手机。'

        def get_model_name(self):
            return 'test-model'

    provider = TranslationProvider()
    with patch('PIL.Image.open') as image_open, \
         patch('app.caption_service.get_caption_provider', return_value=provider):
        image_open.return_value.convert.return_value = Image.new('RGB', (32, 32))
        result = TaskExecutor()._handle_caption(session, task)

    assert result is not None
    assert provider.generation_calls == 1
    assert provider.translation_calls == [
        ('A person holds a phone.', list(CHINESE_POLICY_TERMS))
    ]
    assert session.add.call_args.args[0].text == (
        'EN: A person holds a phone.\n\nZH-CN: 一位成人手持一部手机。'
    )


def test_caption_task_accepts_short_bilingual_caption_without_length_retry():
    from app.tasks import TaskExecutor
    from app.db import Task, Caption, Asset
    from sqlalchemy.orm import Session
    from unittest.mock import Mock

    session = Mock(spec=Session)
    task = Mock(spec=Task)
    asset = Mock(spec=Asset)
    task.payload_json = {'asset_id': 1}
    asset.path = '/fake/path/test_image.jpg'
    asset.mime = 'image/jpeg'
    session.get.return_value = asset
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    provider = Mock()
    provider.generate_caption.return_value = (
        'EN: A child holds a blue toy beside a wooden table.\n\n'
        'ZH-CN: 一名儿童在木桌旁拿着一个蓝色玩具。'
    )
    provider.get_model_name.return_value = 'test-model'

    with patch('PIL.Image.open') as image_open, \
         patch('app.caption_service.get_caption_provider', return_value=provider):
        image_open.return_value.convert.return_value = Image.new('RGB', (32, 32))
        result = TaskExecutor()._handle_caption(session, task)

    assert result is not None
    assert provider.generate_caption.call_count == 1
    assert session.add.call_args.args[0].model == 'test-model|bilingual-en-zh-cn'


def test_caption_fallback_on_error():
    """Test that caption generation falls back to heuristic on error."""
    from app.tasks import TaskExecutor
    from app.db import Task, Caption, Asset
    from sqlalchemy.orm import Session
    from unittest.mock import Mock
    
    # Mock session and objects
    session = Mock(spec=Session)
    task = Mock(spec=Task)
    asset = Mock(spec=Asset)
    
    task.payload_json = {'asset_id': 1}
    asset.path = '/fake/path/test_image.jpg'
    asset.mime = 'image/jpeg'
    session.get.return_value = asset
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    
    executor = TaskExecutor()
    
    # Mock PIL Image loading to fail
    with patch.dict('os.environ', {
        'CAPTION_ENABLE_STUB_FALLBACK': 'true',
        'CAPTION_PROMPT': 'Write one short factual English caption.',
    }), \
         patch('PIL.Image.open', side_effect=Exception('Model loading failed')):
        result = executor._handle_caption(session, task)
        
        # Should still add a caption using fallback
        session.add.assert_called_once()
        
        # Check that fallback caption was created
        added_caption = session.add.call_args[0][0]
        assert hasattr(added_caption, 'text')
        assert hasattr(added_caption, 'model')
        assert added_caption.model == 'stub-fallback'


if __name__ == '__main__':
    pytest.main([__file__])
