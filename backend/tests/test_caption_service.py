"""Tests for caption service integration."""

import pytest
from PIL import Image
import numpy as np
from unittest.mock import patch, MagicMock

from app.caption_service import (
    get_caption_provider,
    StubCaptionProvider,
    LlavaNextCaptionProvider,
    Qwen2VLCaptionProvider,
    BLIP2CaptionProvider,
)


def test_get_caption_provider_default():
    """Test that default configuration returns StubCaptionProvider."""
    provider = get_caption_provider()
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
    ('qwen2.5-vl', Qwen2VLCaptionProvider),
    ('blip2', BLIP2CaptionProvider),
])
def test_provider_selection(provider_name, expected_class):
    """Test that provider selection works correctly."""
    with patch('app.config.settings') as mock_settings:
        mock_settings.caption_provider = provider_name
        mock_settings.caption_device = 'cpu'
        mock_settings.caption_model = 'auto'
        
        # For real model providers, mock the model loading to avoid heavy dependencies
        if provider_name != 'stub':
            with patch('transformers.AutoProcessor'), \
                 patch('transformers.LlavaNextForConditionalGeneration'), \
                 patch('transformers.Qwen2VLForConditionalGeneration'), \
                 patch('transformers.Blip2ForConditionalGeneration'):
                provider = get_caption_provider()
        else:
            provider = get_caption_provider()
            
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
    session.get.return_value = asset
    
    executor = TaskExecutor()
    
    # Mock PIL Image loading and caption service
    with patch('PIL.Image.open') as mock_open, \
         patch('app.caption_service.get_caption_provider') as mock_provider:
        
        # Create mock image
        mock_image = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
        mock_open.return_value.convert.return_value = mock_image
        
        # Create mock provider
        mock_caption_provider = Mock()
        mock_caption_provider.generate_caption.return_value = 'Test caption'
        mock_caption_provider.get_model_name.return_value = 'test-model'
        mock_provider.return_value = mock_caption_provider
        
        # Test caption generation
        result = executor._handle_caption(session, task)
        
        # Verify calls
        mock_provider.assert_called_once()
        mock_caption_provider.generate_caption.assert_called_once()
        session.add.assert_called_once()
        session.commit.assert_called_once()


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
    session.get.return_value = asset
    
    executor = TaskExecutor()
    
    # Mock PIL Image loading to fail
    with patch('PIL.Image.open', side_effect=Exception('Model loading failed')):
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
