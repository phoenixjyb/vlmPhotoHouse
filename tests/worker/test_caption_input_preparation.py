"""Synthetic-only coverage for pre-upload resizing and permanent input errors."""
import hashlib
import io
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image

from app.caption_service import CaptionInputError, CaptionServiceTransientError, HTTPCaptionProvider


VALID = 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。'
PIXEL_ERROR = ('Image size (199756800 pixels) exceeds limit of 178956970 pixels, '
               'could be decompression bomb DOS attack.')


def fake_service(monkeypatch, tmp_path, responses=None, active='qwen3-vl'):
    calls = []
    pending = iter(responses or [httpx.Response(200, json={'caption': VALID})])

    class Client:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            return httpx.Response(200, json={'active_provider': active, 'model_cache_ready': True})

        def post(self, url, files, data=None):
            raw = files['file'][1].read()
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                calls.append({'size': im.size, 'pixels': im.tobytes(), 'data': data, 'raw': raw})
            return next(pending)

    monkeypatch.setattr('app.caption_service.httpx.Client', Client)
    monkeypatch.setattr('app.caption_service._caption_tmp_dir', lambda: str(tmp_path))
    monkeypatch.setenv('CAPTION_HTTP_MAX_IMAGE_EDGE', '1536')
    monkeypatch.setenv('CAPTION_HTTP_RETRY_DELAY_SEC', '0')
    monkeypatch.setenv('CAPTION_HTTP_RETRIES', '2')
    return HTTPCaptionProvider(), calls


@pytest.mark.parametrize('size,expected', [
    ((4000, 3000), (1536, 1152)), ((2252, 4000), (865, 1536)),
    ((1536, 1536), (1536, 1536)), ((320, 240), (320, 240)),
    ((16320, 12240), (1536, 1152)), ((1, 20000), (1, 1536)),
])
def test_dimensions_without_allocating_giant_original(monkeypatch, tmp_path, size, expected):
    provider, _ = fake_service(monkeypatch, tmp_path)
    source = Mock(size=size)
    source.resize.return_value = Image.new('RGB', expected)
    prepared = provider.prepare_image(source)
    if max(size) > 1536:
        source.resize.assert_called_once_with(expected, Image.Resampling.LANCZOS)
        assert prepared.size == expected
    else:
        source.resize.assert_not_called()
        assert prepared is source
    source.close.assert_not_called()
    source.save.assert_not_called()


def test_uploaded_pixels_match_existing_server_resize(monkeypatch, tmp_path):
    provider, calls = fake_service(monkeypatch, tmp_path)
    monkeypatch.setenv('CAPTION_HTTP_MAX_IMAGE_EDGE', '64')
    source = Image.new('RGB', (137, 101))
    source.putdata([(i % 251, (i * 7) % 251, (i * 13) % 251) for i in range(137 * 101)])
    before = source.tobytes()
    expected = source.resize((64, 47), Image.Resampling.LANCZOS)
    assert provider.generate_caption(source, prompt='Detailed EN/ZH caption') == VALID
    assert calls[0]['size'] == expected.size
    assert calls[0]['pixels'] == expected.tobytes()
    assert calls[0]['data'] == {'prompt': 'Detailed EN/ZH caption'}
    assert source.size == (137, 101) and source.tobytes() == before
    assert not list(tmp_path.glob('*.png'))


def test_giant_original_is_never_encoded_or_uploaded(monkeypatch, tmp_path):
    provider, calls = fake_service(monkeypatch, tmp_path)
    source = Mock(size=(16320, 12240))
    source.resize.return_value = Image.new('RGB', (1536, 1152), 'red')
    original_limit = Image.MAX_IMAGE_PIXELS
    provider.generate_caption(source)
    assert calls[0]['size'] == (1536, 1152)
    source.save.assert_not_called()
    source.close.assert_not_called()
    assert Image.MAX_IMAGE_PIXELS == original_limit
    with pytest.raises(ValueError):
        source.resize.return_value.getpixel((0, 0))
    assert not list(tmp_path.glob('*.png'))


@pytest.mark.parametrize('edge', ['0', '-1', '63', '8193', 'bad', ''])
def test_invalid_config_fails_before_upload(monkeypatch, tmp_path, edge):
    provider, calls = fake_service(monkeypatch, tmp_path)
    monkeypatch.setenv('CAPTION_HTTP_MAX_IMAGE_EDGE', edge)
    with pytest.raises(CaptionInputError):
        provider.generate_caption(Image.new('RGB', (32, 32)))
    assert not calls
    assert not list(tmp_path.glob('*.png'))


@pytest.mark.parametrize('active', ['qwen2.5-vl', 'blip2', None])
def test_other_or_unknown_providers_are_unchanged(monkeypatch, tmp_path, active):
    provider, calls = fake_service(monkeypatch, tmp_path, active=active)
    monkeypatch.setenv('CAPTION_HTTP_MAX_IMAGE_EDGE', '64')
    source = Image.new('RGB', (100, 80))
    assert provider.prepare_image(source) is source
    provider.generate_caption(source)
    assert calls[0]['size'] == source.size


def test_pixel_error_is_permanent_and_not_retried(monkeypatch, tmp_path):
    from app.tasks import TaskExecutor

    provider, calls = fake_service(monkeypatch, tmp_path, [httpx.Response(500, json={'detail': PIXEL_ERROR})])
    with pytest.raises(CaptionInputError) as caught:
        provider.generate_caption(Image.new('RGB', (32, 32)))
    assert TaskExecutor.__new__(TaskExecutor)._classify_permanent(caught.value)
    assert len(calls) == 1
    assert not list(tmp_path.glob('*.png'))


@pytest.mark.parametrize('response', [
    httpx.Response(503, json={'detail': 'CUDA out of memory'}),
    httpx.Response(500, text='upstream temporarily unavailable'),
    httpx.Response(500, json={'detail': 'Image size service temporarily unavailable'}),
    httpx.Response(500, json=[]),
])
def test_other_server_failures_still_retry(monkeypatch, tmp_path, response):
    from app.tasks import TaskExecutor

    provider, calls = fake_service(monkeypatch, tmp_path, [response, response])
    source = Image.new('RGB', (32, 32))
    with pytest.raises(CaptionServiceTransientError) as caught:
        provider.generate_caption(source)
    assert not TaskExecutor.__new__(TaskExecutor)._classify_permanent(caught.value)
    assert len(calls) == 2
    assert calls[0]['raw'] == calls[1]['raw']
    assert source.getpixel((0, 0)) == (0, 0, 0)
    assert not list(tmp_path.glob('*.png'))


def test_task_reuses_resized_oriented_image_and_preserves_original(monkeypatch, tmp_path):
    from app.db import Asset, Task
    from app.tasks import TaskExecutor
    from sqlalchemy.orm import Session

    provider, calls = fake_service(monkeypatch, tmp_path, [
        httpx.Response(200, json={'caption': 'EN: incomplete'}),
        httpx.Response(200, json={'caption': VALID}),
    ])
    monkeypatch.setenv('CAPTION_HTTP_MAX_IMAGE_EDGE', '64')
    monkeypatch.setenv('CAPTION_AUTO_TAG_ENABLE', 'false')
    monkeypatch.setenv('CAPTION_ENABLE_STUB_FALLBACK', 'false')
    monkeypatch.setattr('app.caption_service.get_caption_provider', lambda: provider)
    source = tmp_path / 'synthetic.jpg'
    exif = Image.Exif()
    exif[274] = 6
    Image.new('RGB', (200, 100), 'red').save(source, exif=exif)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    resize = Image.Image.resize
    sizes = []

    def measured_resize(image, size, *args, **kwargs):
        sizes.append((image.size, size))
        return resize(image, size, *args, **kwargs)

    monkeypatch.setattr(Image.Image, 'resize', measured_resize)
    session = Mock(spec=Session)
    asset = Mock(spec=Asset)
    asset.id, asset.path, asset.mime = 1, str(source), 'image/jpeg'
    session.get.return_value = asset
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    task = Mock(spec=Task)
    task.payload_json = {'asset_id': 1}
    TaskExecutor.__new__(TaskExecutor)._handle_caption(session, task)
    assert sizes == [((100, 200), (32, 64))]
    assert [c['size'] for c in calls] == [(32, 64), (32, 64)]
    assert calls[0]['raw'] == calls[1]['raw']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert session.add.call_args.args[0].text == VALID
    assert not list(tmp_path.glob('*.png'))
