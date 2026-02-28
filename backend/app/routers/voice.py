from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body, Depends
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from typing import Optional, Any
import httpx
import base64
import subprocess
import tempfile
import os
import re
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from ..config import get_settings
from ..dependencies import get_db
from ..db import Asset, Person, FaceDetection, Task, Tag, AssetTag

router = APIRouter()


def _require_enabled():
    s = get_settings()
    if not s.voice_enabled:
        raise HTTPException(status_code=501, detail='Voice service disabled')
    if s.voice_provider != 'external' or not s.voice_external_base_url:
        raise HTTPException(status_code=501, detail='External voice service not configured')
    return s


def _piper_tts_bytes(text: str, exe_path: str, model_path: str) -> Optional[bytes]:
    """Synthesize WAV bytes using Piper CLI. Returns None on failure."""
    if not text or not exe_path or not model_path:
        return None
    try:
        # Use a temp file for Windows compatibility
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            out_path = tmp.name
        try:
            proc = subprocess.run(
                [exe_path, '-m', model_path, '-f', out_path],
                input=text.encode('utf-8'),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False
            )
            if proc.returncode != 0:
                # Clean up and fail
                try:
                    os.unlink(out_path)
                except Exception:
                    pass
                return None
            # Read produced WAV
            with open(out_path, 'rb') as f:
                data = f.read()
            try:
                os.unlink(out_path)
            except Exception:
                pass
            return data if data else None
        except Exception:
            try:
                os.unlink(out_path)
            except Exception:
                pass
            return None
    except Exception:
        return None


def _normalize_voice_text(text: str) -> str:
    raw = str(text or '').strip().lower()
    raw = re.sub(r"[,\.\!\?;:，。！？；：]+", " ", raw)
    return ' '.join(raw.split())


def _extract_query(normalized_text: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if normalized_text.startswith(prefix):
            return normalized_text[len(prefix):].strip()
    return ''


def _extract_person_assets_query(normalized_text: str) -> str:
    patterns = (
        r"^(?:please\s+)?(?:show me|show|find|open)\s+(?:(?:the|a|an|some)\s+)?(?:photos|photo|pictures|picture|images|image)\s+(?:of\s+)?(.+)$",
        r"^(?:photos|photo|pictures|picture|images|image)\s+(?:of\s+)?(.+)$",
        r"^(?:show me|show)\s+(.+?)\s+(?:photos|photo|pictures|picture|images|image)$",
        r"^(?:show me|show)\s+(.+?)'s\s+(?:photos|photo|pictures|picture|images|image)$",
        r"^(?:请)?(?:给我看|给我看看|帮我找|找找|找一下|显示|打开|看看)\s*(?:一下)?\s*(.+?)\s*(?:的)?\s*(?:照片|图片|相片|影像|相册)$",
        r"^(?:请)?(?:帮我)?(?:找|找下|找一下)\s*(.+?)\s*(?:的)?\s*(?:照片|图片|相片|影像|相册)$",
    )
    for pattern in patterns:
        m = re.match(pattern, normalized_text)
        if not m:
            continue
        query = str(m.group(1) or '').strip(" \t\r\n'\".,!?;:。！？；：")
        query = re.sub(r"^(?:the|a|an)\s+", "", query, flags=re.IGNORECASE).strip()
        if query:
            return query
    return ''


def _parse_voice_action(text: str) -> dict[str, Any]:
    n = _normalize_voice_text(text)
    if not n:
        return {
            'action': 'help',
            'mode': 'read',
            'args': {},
            'needs_confirmation': False,
            'confidence': 0.0,
        }

    mutating_markers = (
        'rename', 'merge', 'delete', 'remove', 'assign', 'unassign', 'add tag',
        'cancel task', 'requeue', 'split person', '重命名', '合并', '删除', '移除', '分配', '取消任务', '重新入队'
    )
    if any(m in n for m in mutating_markers):
        return {
            'action': 'mutate.request',
            'mode': 'mutate',
            'args': {'raw_text': text},
            'needs_confirmation': True,
            'confidence': 0.82,
        }

    person_assets_query = _extract_person_assets_query(n)
    if person_assets_query:
        return {
            'action': 'search.person.assets',
            'mode': 'read',
            'args': {'query': person_assets_query},
            'needs_confirmation': False,
            'confidence': 0.9,
        }

    people_query = _extract_query(n, ('search person ', 'find person ', 'person ', '搜索人物 ', '查找人物 ', '人物 '))
    if people_query:
        return {
            'action': 'search.people',
            'mode': 'read',
            'args': {'query': people_query},
            'needs_confirmation': False,
            'confidence': 0.88,
        }

    tag_query = _extract_query(n, ('search tag ', 'find tag ', 'tag ', 'tags ', '搜索标签 ', '查找标签 ', '标签 '))
    if tag_query:
        return {
            'action': 'search.tags',
            'mode': 'read',
            'args': {'query': tag_query},
            'needs_confirmation': False,
            'confidence': 0.88,
        }

    search_query = _extract_query(n, ('search ', 'find ', '搜索 ', '查找 '))
    if search_query:
        return {
            'action': 'search.assets',
            'mode': 'read',
            'args': {'query': search_query},
            'needs_confirmation': False,
            'confidence': 0.84,
        }

    if any(m in n for m in ('task', 'queue', '任务', '队列')):
        return {
            'action': 'tasks.status',
            'mode': 'read',
            'args': {},
            'needs_confirmation': False,
            'confidence': 0.78,
        }

    if any(m in n for m in ('status', 'health', 'overview', '状态', '健康')):
        return {
            'action': 'system.status',
            'mode': 'read',
            'args': {},
            'needs_confirmation': False,
            'confidence': 0.78,
        }

    return {
        'action': 'help',
        'mode': 'read',
        'args': {'raw_text': text},
        'needs_confirmation': False,
        'confidence': 0.42,
    }


def _voice_summary(action: str, data: dict[str, Any], language: Optional[str]) -> str:
    zh = str(language or '').lower().startswith('zh')
    if action == 'mutate.request':
        return (
            '这是写入类操作，请先确认后再执行。'
            if zh
            else 'This is a mutating request and requires confirmation before execution.'
        )
    if action == 'system.status':
        if zh:
            return (
                f"系统状态：资产{int(data.get('assets_total', 0))}个，人物{int(data.get('persons_total', 0))}个，"
                f"待处理任务{int(data.get('tasks_pending', 0))}个，运行中{int(data.get('tasks_running', 0))}个。"
            )
        return (
            f"System status: {int(data.get('assets_total', 0))} assets, {int(data.get('persons_total', 0))} people, "
            f"{int(data.get('tasks_pending', 0))} pending tasks, {int(data.get('tasks_running', 0))} running tasks."
        )
    if action == 'tasks.status':
        if zh:
            return (
                f"任务状态：待处理{int(data.get('pending', 0))}，运行中{int(data.get('running', 0))}，"
                f"失败{int(data.get('failed', 0))}，死信{int(data.get('dead', 0))}。"
            )
        return (
            f"Task status: {int(data.get('pending', 0))} pending, {int(data.get('running', 0))} running, "
            f"{int(data.get('failed', 0))} failed, {int(data.get('dead', 0))} dead."
        )
    if action == 'search.assets':
        q = str(data.get('query') or '')
        total = int(data.get('total', 0))
        return (
            f"已为“{q}”找到{total}个资产，已返回前几项。"
            if zh
            else f'Found {total} assets for "{q}". Returning top matches.'
        )
    if action == 'search.people':
        q = str(data.get('query') or '')
        total = int(data.get('total', 0))
        return (
            f"已为“{q}”找到{total}个人物匹配。"
            if zh
            else f'Found {total} people matching "{q}".'
        )
    if action == 'search.person.assets':
        q = str(data.get('query') or '')
        person_name = str(data.get('person_name') or '')
        total = int(data.get('total', 0))
        if person_name:
            return (
                f"已找到人物“{person_name}”，共{total}个相关资源，正在展示。"
                if zh
                else f"Found {total} assets for {person_name}. Opening their photos now."
            )
        return (
            f"未找到与“{q}”匹配的人物。"
            if zh
            else f'No person matched "{q}".'
        )
    if action == 'search.tags':
        q = str(data.get('query') or '')
        total = int(data.get('total', 0))
        return (
            f"已为“{q}”找到{total}个标签匹配。"
            if zh
            else f'Found {total} tags matching "{q}".'
        )
    return (
        '我目前支持只读语音命令：搜索资产、搜索人物、搜索标签、查看系统或任务状态。'
        if zh
        else 'I currently support read-only voice commands: asset search, people search, tag search, and status queries.'
    )


# --- STT (proxy to external llmytranslate) ---
@router.post('/voice/transcribe')
async def transcribe(
    file: UploadFile = File(...),
    # Map to llmytranslate's form fields
    language: Optional[str] = Form(None),
    # Back-compat alias
    lang: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
):
    s = _require_enabled()
    url = s.voice_external_base_url.rstrip('/') + s.voice_asr_path
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            files = {'audio_file': (file.filename or 'audio.webm', await file.read(), file.content_type or 'audio/webm')}
            data = {}
            eff_lang = language or lang
            if eff_lang:
                data['language'] = eff_lang
            if prompt:
                data['prompt'] = prompt
            r = await client.post(url, headers=headers, files=files, data=data)
            # Try to parse JSON regardless of status; return JSON on errors (200) for UX consistency
            try:
                resp = r.json()
            except Exception:
                return JSONResponse({'success': False, 'error': r.text or 'ASR provider error', 'status': r.status_code}, status_code=200)
            return JSONResponse(resp, status_code=200)
    except httpx.HTTPError as e:
        # Network error; surface as JSON to clients for graceful handling
        return JSONResponse({'success': False, 'error': f'ASR proxy failed: {e}'}, status_code=200)


# --- TTS (proxy to external llmytranslate) ---
@router.post('/voice/tts')
async def tts(
    text: str = Body(..., embed=True),
    language: Optional[str] = Body('en', embed=True),
    voice: Optional[str] = Body('default', embed=True),
    speed: float = Body(1.0, embed=True),
    format: str = Body('audio/wav', embed=True),
):
    s = _require_enabled()
    url = s.voice_external_base_url.rstrip('/') + s.voice_tts_path
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            # llmytranslate expects form fields and returns base64 audio
            data = {
                'text': text,
                'language': language or 'en',
                'voice_speed': speed,
                'output_format': 'wav' if format.endswith('wav') else 'mp3',
            }
            r = await client.post(url, headers=headers, data=data)
            # Parse JSON regardless of status; degrade gracefully
            try:
                resp = r.json()
            except Exception:
                resp = {'success': False, 'error': r.text or 'Provider error', 'status': r.status_code}

            audio_bytes: Optional[bytes] = None
            if resp.get('success', False):
                audio_b64 = resp.get('audio_base64') or resp.get('audio_data')
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)

            # Fallback to Piper if configured and no audio
            if audio_bytes is None and getattr(s, 'tts_fallback_provider', 'none') == 'piper' and s.piper_exe_path and s.piper_model_path:
                audio_bytes = _piper_tts_bytes(text, s.piper_exe_path, s.piper_model_path)
                if audio_bytes is not None:
                    return StreamingResponse(iter([audio_bytes]), media_type='audio/wav')

            # No audio available; return JSON but 200
            if audio_bytes is None:
                if not resp:
                    resp = {'success': False, 'error': 'No audio returned (TTS unavailable?)'}
                return JSONResponse(resp, status_code=200)

            media_type = 'audio/wav' if (format.endswith('wav')) else 'audio/mpeg'
            return StreamingResponse(iter([audio_bytes]), media_type=media_type)
    except httpx.HTTPError as e:
        # Try fallback on HTTP error
        if getattr(s, 'tts_fallback_provider', 'none') == 'piper' and s.piper_exe_path and s.piper_model_path:
            audio_bytes = _piper_tts_bytes(text, s.piper_exe_path, s.piper_model_path)
            if audio_bytes is not None:
                return StreamingResponse(iter([audio_bytes]), media_type='audio/wav')
        raise HTTPException(status_code=502, detail=f'TTS proxy failed: {e}')


# --- Full voice conversation (STT -> LLM -> TTS) ---
@router.post('/voice/conversation')
async def conversation(
    audio: UploadFile = File(...),
    language: Optional[str] = Form('en'),
    voice: Optional[str] = Form('default'),
    speed: float = Form(1.0),
    model: Optional[str] = Form('gemma3:latest'),
    tts_mode: Optional[str] = Form('fast'),
):
    s = _require_enabled()
    url = s.voice_external_base_url.rstrip('/') + s.voice_conversation_path
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            files = {'audio_file': (audio.filename or 'audio.webm', await audio.read(), audio.content_type or 'audio/webm')}
            data = {
                'language': language or 'en',
                'voice': voice or 'default',
                'speed': str(speed),
                'model': model or 'gemma3:latest',
                'tts_mode': tts_mode or 'fast',
            }
            r = await client.post(url, headers=headers, files=files, data=data)
            # Try to parse JSON regardless of status; degrade to JSON on provider errors
            try:
                resp = r.json()
            except Exception:
                # Non-JSON error from provider
                return JSONResponse({'success': False, 'error': r.text or 'Provider error', 'status': r.status_code}, status_code=200)

            # If provider indicates failure, return JSON so UI can display text/error gracefully
            if not resp.get('success', False):
                return JSONResponse(resp, status_code=200)

            # If no audio is present (e.g., TTS unavailable), return JSON (may include text_response)
            audio_b64 = resp.get('audio_base64') or resp.get('audio_data')
            if not audio_b64:
                # Attempt local TTS fallback if configured
                if getattr(s, 'tts_fallback_provider', 'none') == 'piper' and s.piper_exe_path and s.piper_model_path:
                    text_resp = resp.get('text_response') or resp.get('text') or ''
                    audio_bytes = _piper_tts_bytes(text_resp, s.piper_exe_path, s.piper_model_path)
                    if audio_bytes:
                        return StreamingResponse(iter([audio_bytes]), media_type='audio/wav')
                return JSONResponse(resp, status_code=200)

            # Otherwise, stream audio
            audio_bytes = base64.b64decode(audio_b64)
            media_type = resp.get('content_type') or 'audio/wav'
            return StreamingResponse(iter([audio_bytes]), media_type=media_type)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f'Conversation proxy failed: {e}')


@router.post('/voice/chat')
async def voice_chat(
    text: str = Body(..., embed=True),
    conversation_id: Optional[str] = Body(None, embed=True),
    language: Optional[str] = Body('en', embed=True),
    model: Optional[str] = Body('gemma3:latest', embed=True),
):
    """Text chat proxy with persistent conversation context support."""
    s = _require_enabled()
    message = str(text or '').strip()
    if not message:
        return JSONResponse({'success': False, 'error': 'Empty message'}, status_code=200)

    chat_path = os.getenv('VOICE_CHAT_MESSAGE_PATH', '/api/chat/message')
    if not str(chat_path).startswith('/'):
        chat_path = '/' + str(chat_path)
    url = s.voice_external_base_url.rstrip('/') + str(chat_path)
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    payload: dict[str, Any] = {
        'message': message,
        'model': model or 'gemma3:latest',
        'platform': 'vlmPhotoHouse',
    }
    if conversation_id:
        payload['conversation_id'] = str(conversation_id).strip()
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            r = await client.post(url, headers=headers, json=payload)
            try:
                resp = r.json()
            except Exception:
                return JSONResponse(
                    {
                        'success': False,
                        'error': r.text or f'Chat provider status {r.status_code}',
                        'status': r.status_code,
                        'conversation_id': payload.get('conversation_id'),
                    },
                    status_code=200,
                )

            if not isinstance(resp, dict):
                return JSONResponse(
                    {
                        'success': False,
                        'error': 'Unexpected chat provider response shape',
                        'conversation_id': payload.get('conversation_id'),
                    },
                    status_code=200,
                )

            text_response = str(resp.get('response') or resp.get('text_response') or resp.get('text') or '').strip()
            resolved_conversation_id = str(resp.get('conversation_id') or payload.get('conversation_id') or '').strip()
            if text_response:
                return JSONResponse(
                    {
                        'success': True,
                        'text_response': text_response,
                        'conversation_id': resolved_conversation_id or None,
                        'language': language or 'en',
                        'model': str(resp.get('model_used') or payload.get('model') or 'gemma3:latest'),
                    },
                    status_code=200,
                )

            err = resp.get('detail') or resp.get('error') or r.text or f'Chat provider status {r.status_code}'
            return JSONResponse(
                {
                    'success': False,
                    'error': str(err),
                    'status': r.status_code,
                    'conversation_id': resolved_conversation_id or None,
                },
                status_code=200,
            )
    except httpx.HTTPError as e:
        return JSONResponse(
            {
                'success': False,
                'error': f'Chat proxy failed: {e}',
                'conversation_id': payload.get('conversation_id'),
            },
            status_code=200,
        )


# --- Health and capabilities ---
@router.get('/voice/health')
async def voice_health():
    s = _require_enabled()
    url = s.voice_external_base_url.rstrip('/') + s.voice_health_path
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f'Voice health proxy failed: {e}')


@router.get('/voice/capabilities')
async def voice_capabilities():
    s = _require_enabled()
    url = s.voice_external_base_url.rstrip('/') + s.voice_capabilities_path
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f'Voice capabilities proxy failed: {e}')


@router.post('/voice/command')
def voice_command(
    text: str = Body(..., embed=True),
    language: Optional[str] = Body('en', embed=True),
    limit: int = Body(5, embed=True),
    db_s: Session = Depends(get_db),
):
    _require_enabled()
    contract = _parse_voice_action(text)
    safe_limit = max(1, min(int(limit), 20))

    if contract.get('mode') == 'mutate':
        summary_text = _voice_summary('mutate.request', {}, language)
        return {
            'success': True,
            'phase': 'phase2-read-only',
            'executed': False,
            'contract': contract,
            'summary_text': summary_text,
            'tts_text': summary_text,
            'data': {'reason': 'confirmation_required'},
        }

    action = str(contract.get('action') or 'help')
    data: dict[str, Any]
    executed = True

    if action == 'system.status':
        data = {
            'assets_total': int(db_s.query(func.count(Asset.id)).scalar() or 0),
            'persons_total': int(db_s.query(func.count(Person.id)).scalar() or 0),
            'tasks_pending': int(db_s.query(func.count(Task.id)).filter(Task.state == 'pending').scalar() or 0),
            'tasks_running': int(db_s.query(func.count(Task.id)).filter(Task.state == 'running').scalar() or 0),
        }
    elif action == 'tasks.status':
        rows = db_s.query(Task.state, func.count(Task.id)).group_by(Task.state).all()
        counts = {str(state): int(cnt) for state, cnt in rows}
        data = {
            'pending': int(counts.get('pending', 0)),
            'running': int(counts.get('running', 0)),
            'finished': int(counts.get('finished', 0) + counts.get('done', 0)),
            'failed': int(counts.get('failed', 0)),
            'dead': int(counts.get('dead', 0)),
            'canceled': int(counts.get('canceled', 0)),
        }
    elif action == 'search.assets':
        q = str(contract.get('args', {}).get('query') or '').strip()
        rows = (
            db_s.query(Asset.id, Asset.path, Asset.mime)
            .filter(func.lower(Asset.path).like(f"%{q.lower()}%"))
            .order_by(Asset.id.desc())
            .limit(safe_limit)
            .all()
        )
        data = {
            'query': q,
            'total': int(len(rows)),
            'items': [{'id': int(aid), 'path': path, 'mime': mime} for aid, path, mime in rows],
        }
    elif action == 'search.people':
        q = str(contract.get('args', {}).get('query') or '').strip()
        rows = (
            db_s.query(Person.id, Person.display_name, Person.face_count)
            .filter(Person.display_name != None)
            .filter(func.lower(Person.display_name).like(f"%{q.lower()}%"))
            .order_by(Person.face_count.desc(), Person.id.asc())
            .limit(safe_limit)
            .all()
        )
        data = {
            'query': q,
            'total': int(len(rows)),
            'items': [
                {'id': int(pid), 'display_name': name, 'face_count': int(face_count or 0)}
                for pid, name, face_count in rows
            ],
        }
    elif action == 'search.person.assets':
        q = str(contract.get('args', {}).get('query') or '').strip()
        person_match = (
            db_s.query(Person.id, Person.display_name, Person.face_count)
            .filter(Person.display_name != None)
            .filter(func.lower(Person.display_name).like(f"%{q.lower()}%"))
            .order_by(Person.face_count.desc(), Person.id.asc())
            .first()
        )
        if person_match is None:
            data = {
                'query': q,
                'person_id': None,
                'person_name': None,
                'total': 0,
                'items': [],
            }
        else:
            person_id = int(person_match[0])
            person_name = str(person_match[1] or '')
            asset_ids_select = select(FaceDetection.asset_id).where(FaceDetection.person_id == person_id).distinct()
            base_query = db_s.query(Asset.id, Asset.path, Asset.mime).filter(Asset.id.in_(asset_ids_select))
            total = int(base_query.count() or 0)
            rows = (
                base_query
                .order_by(Asset.id.desc())
                .limit(safe_limit)
                .all()
            )
            data = {
                'query': q,
                'person_id': person_id,
                'person_name': person_name,
                'total': total,
                'items': [{'id': int(aid), 'path': path, 'mime': mime} for aid, path, mime in rows],
            }
    elif action == 'search.tags':
        q = str(contract.get('args', {}).get('query') or '').strip()
        rows = (
            db_s.query(
                Tag.id,
                Tag.name,
                func.count(func.distinct(AssetTag.asset_id)).label('assets'),
            )
            .outerjoin(AssetTag, AssetTag.tag_id == Tag.id)
            .filter(func.lower(Tag.name).like(f"%{q.lower()}%"))
            .group_by(Tag.id, Tag.name)
            .order_by(func.count(func.distinct(AssetTag.asset_id)).desc(), Tag.name.asc())
            .limit(safe_limit)
            .all()
        )
        data = {
            'query': q,
            'total': int(len(rows)),
            'items': [{'id': int(tid), 'name': name, 'assets': int(assets or 0)} for tid, name, assets in rows],
        }
    else:
        executed = False
        data = {
            'suggestions': [
                'search <text>',
                'search person <name>',
                'search tag <name>',
                'task status',
                'system status',
            ]
        }

    summary_text = _voice_summary(action, data, language)
    return {
        'success': True,
        'phase': 'phase2-read-only',
        'executed': executed,
        'contract': contract,
        'summary_text': summary_text,
        'tts_text': summary_text,
        'data': data,
    }


@router.get('/voice/demo')
async def voice_demo_page():
    # Simple HTML page to test voice proxy endpoints
        html = """
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>Voice Demo</title>
            <style>body{font-family:system-ui,Segoe UI,Arial;margin:2rem;max-width:800px}</style>
        </head>
        <body>
            <h1>Voice Demo</h1>
            <section>
                <h2>Text to Speech</h2>
                <form id="ttsForm">
                    <label>Text<br/><textarea name="text" rows="3" style="width:100%">Hello, this is a test.</textarea></label><br/>
                    <label>Language <input name="language" value="en"/></label>
                    <label>Speed <input name="speed" value="1.0" type="number" step="0.1"/></label>
                    <button type="submit">Speak</button>
                </form>
                <audio id="ttsAudio" controls style="display:block;margin-top:1rem"></audio>
                <div id="ttsStatus" style="margin-top:0.5rem;color:#666"></div>
            </section>
            <hr/>
            <section>
                <h2>Microphone Transcribe</h2>
                <div>
                    <button id="recBtn">Start Recording</button>
                    <span id="recStatus" style="margin-left:0.5rem;color:#666"></span>
                </div>
                <pre id="asrOut" style="background:#f6f8fa;padding:0.75rem;border-radius:6px;white-space:pre-wrap"></pre>
            </section>
            <hr/>
            <section>
                <h2>Conversation (upload audio)</h2>
                <form id="convForm" enctype="multipart/form-data">
                    <input type="file" name="audio" accept="audio/*" required />
                    <label>Language <input name="language" value="en"/></label>
                    <button type="submit">Send</button>
                </form>
                <audio id="convAudio" controls style="display:block;margin-top:1rem"></audio>
            </section>
            <script>
                function speak(text, lang) {
                    if (!text) return;
                    if ('speechSynthesis' in window) {
                        const u = new SpeechSynthesisUtterance(String(text));
                        if (lang) u.lang = lang;
                        window.speechSynthesis.speak(u);
                    } else {
                        alert(text);
                    }
                }
                const ttsForm = document.getElementById('ttsForm');
                const ttsAudio = document.getElementById('ttsAudio');
                const ttsStatus = document.getElementById('ttsStatus');
                ttsForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const fd = new FormData(ttsForm);
                    const payload = { text: fd.get('text'), language: fd.get('language'), speed: parseFloat(fd.get('speed')||'1.0') };
                    ttsStatus.textContent = 'Requesting server TTS...';
                    try {
                        const res = await fetch('/voice/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                        if (!res.ok) {
                            ttsStatus.textContent = 'TTS request failed (' + res.status + ').';
                            return;
                        }
                        const ct = res.headers.get('content-type') || '';
                        if (ct.startsWith('audio/')) {
                            const blob = await res.blob();
                            const url = URL.createObjectURL(blob);
                            ttsAudio.src = url;
                            ttsStatus.textContent = 'Server audio ready (' + ct + ').';
                        } else {
                            const j = await res.json().catch(()=>null);
                            const msg = j?.error || j?.text || j?.text_response || payload.text || 'TTS unavailable';
                            const reason = j?.error || (Number(j?.audio_size_bytes || 0) === 0 ? 'No server audio returned' : 'Server returned non-audio response');
                            const sec = Number(j?.processing_time || 0);
                            const lag = sec > 0 ? (' (' + sec.toFixed(2) + 's)') : '';
                            ttsStatus.textContent = 'Server TTS text-only fallback' + lag + ': ' + reason + '. Using browser speech.';
                            speak(msg, payload.language || 'en');
                        }
                    } catch (err) {
                        ttsStatus.textContent = 'TTS request error: ' + String(err);
                    }
                });
                const convForm = document.getElementById('convForm');
                convForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const fd = new FormData(convForm);
                    const res = await fetch('/voice/conversation', { method: 'POST', body: fd });
                    if (!res.ok) { alert('Conversation failed'); return; }
                    const ct = res.headers.get('content-type') || '';
                    if (ct.startsWith('audio/')) {
                        const blob = await res.blob();
                        const url = URL.createObjectURL(blob);
                        document.getElementById('convAudio').src = url;
                    } else {
                        const j = await res.json().catch(()=>null);
                        const msg = j?.text_response || j?.error || 'No audio returned.';
                        speak(msg);
                    }
                });

                // Microphone recorder for ASR
                (function(){
                    let mediaRec = null;
                    let chunks = [];
                    const btn = document.getElementById('recBtn');
                    const status = document.getElementById('recStatus');
                    const out = document.getElementById('asrOut');
                    async function start() {
                        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                        chunks = [];
                        mediaRec = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                        mediaRec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
                        mediaRec.onstop = async () => {
                            const blob = new Blob(chunks, { type: 'audio/webm' });
                            const fd = new FormData();
                            fd.append('file', blob, 'audio.webm');
                            const res = await fetch('/voice/transcribe', { method: 'POST', body: fd });
                            const j = await res.json().catch(()=>null);
                            out.textContent = j ? JSON.stringify(j, null, 2) : 'Transcribe failed';
                            stream.getTracks().forEach(t => t.stop());
                            status.textContent = '';
                        };
                        mediaRec.start();
                        status.textContent = 'Recording... click to stop';
                        btn.textContent = 'Stop Recording';
                    }
                    function stop() {
                        if (mediaRec && mediaRec.state !== 'inactive') mediaRec.stop();
                        btn.textContent = 'Start Recording';
                    }
                    btn.addEventListener('click', async () => {
                        if (!mediaRec || mediaRec.state === 'inactive') {
                            try { await start(); } catch (e) { alert('Mic error: '+e); }
                        } else {
                            stop();
                        }
                    });
                })();
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html, media_type='text/html')
