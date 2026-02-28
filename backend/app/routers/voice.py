from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body, Depends
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from typing import Optional, Any
import httpx
import base64
import subprocess
import tempfile
import os
import re
import time
import uuid
from threading import Lock
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from ..config import get_settings
from ..dependencies import get_db
from ..db import Asset, Person, FaceDetection, Task, Tag, AssetTag, AssetTagBlock
from .people import assign_face_stranger as people_assign_face_stranger, merge_persons as people_merge_persons

router = APIRouter()

_VOICE_CONFIRM_TTL_SEC = int(os.getenv('VOICE_CONFIRM_TTL_SEC', '180') or '180')
_VOICE_PENDING_BY_CLIENT: dict[str, dict[str, Any]] = {}
_VOICE_PENDING_LOCK = Lock()


def _require_enabled():
    s = get_settings()
    if not s.voice_enabled:
        raise HTTPException(status_code=501, detail='Voice service disabled')
    if s.voice_provider != 'external' or not s.voice_external_base_url:
        raise HTTPException(status_code=501, detail='External voice service not configured')
    return s


def _normalize_client_id(client_id: Optional[str]) -> str:
    raw = str(client_id or '').strip()
    if not raw:
        return 'default'
    sanitized = re.sub(r'[^a-zA-Z0-9._:-]+', '', raw)
    return sanitized[:80] or 'default'


def _cleanup_expired_pending_actions(now_ts: Optional[float] = None) -> None:
    now = float(now_ts or time.time())
    with _VOICE_PENDING_LOCK:
        expired = [client for client, rec in _VOICE_PENDING_BY_CLIENT.items() if float(rec.get('expires_at', 0.0)) < now]
        for client in expired:
            _VOICE_PENDING_BY_CLIENT.pop(client, None)


def _put_pending_action(client_id: str, action: str, args: dict[str, Any]) -> dict[str, Any]:
    now = float(time.time())
    rec = {
        'token': str(uuid.uuid4()),
        'client_id': client_id,
        'action': action,
        'args': dict(args),
        'created_at': now,
        'expires_at': now + float(max(30, _VOICE_CONFIRM_TTL_SEC)),
    }
    with _VOICE_PENDING_LOCK:
        _VOICE_PENDING_BY_CLIENT[client_id] = rec
    return rec


def _pop_pending_action(client_id: str, confirmation_token: Optional[str]) -> Optional[dict[str, Any]]:
    _cleanup_expired_pending_actions()
    with _VOICE_PENDING_LOCK:
        rec = _VOICE_PENDING_BY_CLIENT.get(client_id)
        if not rec:
            return None
        token = str(confirmation_token or '').strip()
        if token and token != str(rec.get('token') or ''):
            return None
        _VOICE_PENDING_BY_CLIENT.pop(client_id, None)
        return dict(rec)


def _normalize_person_name(value: str) -> str:
    cleaned = str(value or '').strip(" \t\r\n'\"`“”‘’.,!?;:，。！？；：")
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _parse_rename_person_action(normalized_text: str) -> Optional[dict[str, Any]]:
    m_id = re.match(r"^(?:please\s+)?rename\s+person\s+#?(\d+)\s+(?:to|as)\s+(.+)$", normalized_text)
    if m_id:
        new_name = _normalize_person_name(m_id.group(2))
        if new_name:
            return {
                'person_id': int(m_id.group(1)),
                'old_query': str(m_id.group(1)),
                'new_name': new_name,
            }

    rename_patterns = (
        r"^(?:please\s+)?(?:rename|change name of)\s+(?:person\s+)?(.+?)\s+(?:to|as)\s+(.+)$",
        r"^(?:请)?(?:把|将)?(?:人物)?\s*(.+?)\s*(?:改名为|重命名为|改成|叫做)\s*(.+)$",
    )
    for pattern in rename_patterns:
        m = re.match(pattern, normalized_text)
        if not m:
            continue
        old_query = _normalize_person_name(m.group(1))
        new_name = _normalize_person_name(m.group(2))
        if old_query and new_name:
            return {'person_id': None, 'old_query': old_query, 'new_name': new_name}
    return None


def _normalize_person_ref(raw: str) -> tuple[int | None, str]:
    text = _normalize_person_name(raw)
    text = re.sub(r'^(?:person|人物)\s*#?', '', text, flags=re.IGNORECASE).strip()
    if re.fullmatch(r'\d+', text):
        return int(text), text
    return None, text


def _parse_merge_people_action(normalized_text: str) -> Optional[dict[str, Any]]:
    m_id = re.match(
        r"^(?:please\s+)?merge\s+(?:person\s+)?#?(\d+)\s+(?:into|to)\s+(?:person\s+)?#?(\d+)$",
        normalized_text,
    )
    if m_id:
        src_id = int(m_id.group(1))
        tgt_id = int(m_id.group(2))
        return {
            'source_person_id': src_id,
            'source_query': str(src_id),
            'target_person_id': tgt_id,
            'target_query': str(tgt_id),
        }

    patterns = (
        r"^(?:please\s+)?merge\s+(.+?)\s+(?:into|to)\s+(.+)$",
        r"^(?:请)?(?:把|将)?(.+?)\s*(?:合并到|并入)\s*(.+)$",
    )
    for pattern in patterns:
        m = re.match(pattern, normalized_text)
        if not m:
            continue
        src_id, src_q = _normalize_person_ref(m.group(1))
        tgt_id, tgt_q = _normalize_person_ref(m.group(2))
        if (src_id or src_q) and (tgt_id or tgt_q):
            return {
                'source_person_id': src_id,
                'source_query': src_q,
                'target_person_id': tgt_id,
                'target_query': tgt_q,
            }
    return None


def _parse_assign_stranger_action(normalized_text: str) -> Optional[dict[str, Any]]:
    patterns = (
        r"^(?:please\s+)?(?:assign|mark|set)\s+face\s+#?(\d+)\s+(?:to|as)\s+stranger$",
        r"^(?:请)?(?:把|将)?(?:人脸|脸)\s*#?(\d+)\s*(?:标记为|设为|分配给)\s*陌生人$",
    )
    for pattern in patterns:
        m = re.match(pattern, normalized_text)
        if not m:
            continue
        return {'face_id': int(m.group(1))}
    return None


def _normalize_tag_name(raw: str) -> str:
    text = str(raw or '').strip()
    text = text.strip(" \t\r\n'\"`“”‘’.,!?;:，。！？；：")
    return text


def _parse_add_tag_action(normalized_text: str) -> Optional[dict[str, Any]]:
    patterns = (
        r"^(?:please\s+)?add\s+tag\s+(.+?)\s+to\s+(?:asset|photo|image)\s+#?(\d+)$",
        r"^(?:please\s+)?tag\s+(?:asset|photo|image)\s+#?(\d+)\s+(?:with\s+)?(.+)$",
        r"^(?:请)?(?:给|为)?(?:资源|照片|图片|资产)\s*#?(\d+)\s*(?:加标签|添加标签|打上标签)\s*(.+)$",
    )
    for pattern in patterns:
        m = re.match(pattern, normalized_text)
        if not m:
            continue
        if pattern.startswith("^(?:please\\s+)?tag"):
            aid = int(m.group(1))
            tag_name = _normalize_tag_name(m.group(2))
        elif "资源|照片|图片|资产" in pattern:
            aid = int(m.group(1))
            tag_name = _normalize_tag_name(m.group(2))
        else:
            tag_name = _normalize_tag_name(m.group(1))
            aid = int(m.group(2))
        if tag_name:
            return {'asset_id': aid, 'tag_name': tag_name}
    return None


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

    confirm_phrases = (
        'yes',
        'confirm',
        'go ahead',
        'do it',
        'ok',
        'okay',
        'sure',
        '确定',
        '确认',
        '执行',
        '是',
    )
    if n in confirm_phrases:
        return {
            'action': 'mutate.confirm',
            'mode': 'mutate',
            'args': {},
            'needs_confirmation': False,
            'confidence': 0.92,
        }

    cancel_phrases = (
        'cancel',
        'no',
        'stop',
        'never mind',
        '取消',
        '不要',
        '算了',
    )
    if n in cancel_phrases:
        return {
            'action': 'mutate.cancel',
            'mode': 'mutate',
            'args': {},
            'needs_confirmation': False,
            'confidence': 0.92,
        }

    rename_args = _parse_rename_person_action(n)
    if rename_args:
        return {
            'action': 'mutate.person.rename',
            'mode': 'mutate',
            'args': rename_args,
            'needs_confirmation': True,
            'confidence': 0.9,
        }

    merge_args = _parse_merge_people_action(n)
    if merge_args:
        return {
            'action': 'mutate.people.merge',
            'mode': 'mutate',
            'args': merge_args,
            'needs_confirmation': True,
            'confidence': 0.9,
        }

    assign_stranger_args = _parse_assign_stranger_action(n)
    if assign_stranger_args:
        return {
            'action': 'mutate.face.assign_stranger',
            'mode': 'mutate',
            'args': assign_stranger_args,
            'needs_confirmation': True,
            'confidence': 0.9,
        }

    add_tag_args = _parse_add_tag_action(n)
    if add_tag_args:
        return {
            'action': 'mutate.asset.tag_add',
            'mode': 'mutate',
            'args': add_tag_args,
            'needs_confirmation': True,
            'confidence': 0.88,
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
    if action == 'mutate.pending.rename':
        old_name = str(data.get('old_name') or '')
        new_name = str(data.get('new_name') or '')
        return (
            f'将把人物“{old_name}”重命名为“{new_name}”。请说“确认”执行，或说“取消”放弃。'
            if zh
            else f'I can rename "{old_name}" to "{new_name}". Say "confirm" to execute, or "cancel" to abort.'
        )
    if action == 'mutate.pending.merge':
        source_name = str(data.get('source_name') or '')
        target_name = str(data.get('target_name') or '')
        return (
            f'将把人物“{source_name}”合并到“{target_name}”。请说“确认”执行，或说“取消”放弃。'
            if zh
            else f'I can merge "{source_name}" into "{target_name}". Say "confirm" to execute, or "cancel" to abort.'
        )
    if action == 'mutate.pending.assign_stranger':
        face_id = int(data.get('face_id', 0))
        return (
            f'将把人脸#{face_id}分配到“Stranger”分组。请说“确认”执行，或说“取消”放弃。'
            if zh
            else f'I can assign face #{face_id} to Stranger. Say "confirm" to execute, or "cancel" to abort.'
        )
    if action == 'mutate.pending.tag_add':
        asset_id = int(data.get('asset_id', 0))
        tag_name = str(data.get('tag_name') or '')
        return (
            f'将给资源#{asset_id}添加标签“{tag_name}”。请说“确认”执行，或说“取消”放弃。'
            if zh
            else f'I can add tag "{tag_name}" to asset #{asset_id}. Say "confirm" to execute, or "cancel" to abort.'
        )
    if action == 'mutate.person.rename.done':
        old_name = str(data.get('old_name') or '')
        new_name = str(data.get('new_name') or '')
        return (
            f'已将人物“{old_name}”重命名为“{new_name}”。'
            if zh
            else f'Renamed person "{old_name}" to "{new_name}".'
        )
    if action == 'mutate.person.rename.person_not_found':
        q = str(data.get('query') or data.get('person_id') or '')
        return (
            f'未找到可重命名的人物：{q}。'
            if zh
            else f'No person found to rename for "{q}".'
        )
    if action == 'mutate.person.rename.name_conflict':
        new_name = str(data.get('new_name') or '')
        conflict_name = str(data.get('conflict_name') or '')
        return (
            f'无法重命名为“{new_name}”，该名称已被人物“{conflict_name}”使用。'
            if zh
            else f'Cannot rename to "{new_name}" because that name is already used by "{conflict_name}".'
        )
    if action == 'mutate.person.rename.no_change':
        name = str(data.get('name') or '')
        return (
            f'人物名称已是“{name}”，无需修改。'
            if zh
            else f'Person is already named "{name}". No change needed.'
        )
    if action == 'mutate.people.merge.done':
        source_name = str(data.get('source_name') or '')
        target_name = str(data.get('target_name') or '')
        moved_faces = int(data.get('moved_faces', 0))
        return (
            f'已将“{source_name}”合并到“{target_name}”，迁移人脸{moved_faces}个。'
            if zh
            else f'Merged "{source_name}" into "{target_name}" and moved {moved_faces} faces.'
        )
    if action == 'mutate.people.merge.person_not_found':
        q = str(data.get('query') or '')
        return (
            f'未找到可合并的人物：{q}。'
            if zh
            else f'No person found for merge target "{q}".'
        )
    if action == 'mutate.people.merge.invalid_target':
        return (
            '合并源和目标不能相同。'
            if zh
            else 'Merge source and target cannot be the same person.'
        )
    if action == 'mutate.face.assign_stranger.done':
        face_id = int(data.get('face_id', 0))
        return (
            f'已将人脸#{face_id}分配到“Stranger”。'
            if zh
            else f'Assigned face #{face_id} to Stranger.'
        )
    if action == 'mutate.face.assign_stranger.face_not_found':
        face_id = int(data.get('face_id', 0))
        return (
            f'未找到人脸#{face_id}。'
            if zh
            else f'Face #{face_id} was not found.'
        )
    if action == 'mutate.asset.tag_add.done':
        asset_id = int(data.get('asset_id', 0))
        tag_name = str(data.get('tag_name') or '')
        added = bool(data.get('added', False))
        if zh:
            return (
                f'已为资源#{asset_id}添加标签“{tag_name}”。'
                if added
                else f'资源#{asset_id}已包含标签“{tag_name}”，已更新为手工标签来源。'
            )
        return (
            f'Added tag "{tag_name}" to asset #{asset_id}.'
            if added
            else f'Asset #{asset_id} already had tag "{tag_name}"; updated to manual tag source.'
        )
    if action == 'mutate.asset.tag_add.asset_not_found':
        asset_id = int(data.get('asset_id', 0))
        return (
            f'未找到资源#{asset_id}。'
            if zh
            else f'Asset #{asset_id} was not found.'
        )
    if action == 'mutate.asset.tag_add.invalid_tag':
        return (
            '标签内容为空或无效。'
            if zh
            else 'Tag text is empty or invalid.'
        )
    if action == 'mutate.confirm.missing':
        return (
            '当前没有待确认的写入操作。'
            if zh
            else 'There is no pending mutating request to confirm.'
        )
    if action == 'mutate.cancelled':
        return (
            '已取消待确认的写入操作。'
            if zh
            else 'Canceled the pending mutating request.'
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
        '我目前支持语音命令：搜索资产、搜索人物、搜索标签、查看系统或任务状态，以及带确认的重命名/合并/标签/陌生人分配。'
        if zh
        else 'I currently support voice commands for search/status and confirmation-gated mutations: rename, merge, add tag, and assign stranger.'
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
    client_id: Optional[str] = Body(None, embed=True),
    confirm: bool = Body(False, embed=True),
    cancel: bool = Body(False, embed=True),
    confirmation_token: Optional[str] = Body(None, embed=True),
    db_s: Session = Depends(get_db),
):
    _require_enabled()
    _cleanup_expired_pending_actions()
    contract = _parse_voice_action(text)
    safe_limit = max(1, min(int(limit), 20))
    client_key = _normalize_client_id(client_id)
    action = str(contract.get('action') or 'help')

    def _find_person_match(person_id: int, query: str):
        if person_id > 0:
            return (
                db_s.query(Person.id, Person.display_name, Person.face_count)
                .filter(Person.id == person_id)
                .first()
            )
        q = str(query or '').strip()
        if not q:
            return None
        return (
            db_s.query(Person.id, Person.display_name, Person.face_count)
            .filter(Person.display_name != None)
            .filter(func.lower(Person.display_name).like(f"%{q.lower()}%"))
            .order_by(Person.face_count.desc(), Person.id.asc())
            .first()
        )

    def _find_name_conflict(person_id: int, new_name: str):
        normalized = str(new_name or '').strip().lower()
        if not normalized:
            return None
        return (
            db_s.query(Person.id, Person.display_name)
            .filter(Person.id != person_id)
            .filter(Person.display_name != None)
            .filter(func.lower(func.trim(Person.display_name)) == normalized)
            .order_by(Person.id.asc())
            .first()
        )

    def _resolve_person_ref(person_id: int, query: str):
        pid = int(person_id or 0)
        q = str(query or '').strip()
        person_match = _find_person_match(pid, q)
        if person_match is None:
            return None, q or str(pid)
        return person_match, str(person_match[1] or f'#{int(person_match[0])}')

    if cancel or action == 'mutate.cancel':
        dropped = _pop_pending_action(client_key, confirmation_token)
        summary_action = 'mutate.cancelled' if dropped else 'mutate.confirm.missing'
        summary_text = _voice_summary(summary_action, {}, language)
        data = {
            'reason': 'cancelled' if dropped else 'no_pending_confirmation',
            'pending_action': str(dropped.get('action') or '') if dropped else None,
        }
        return {
            'success': True,
            'phase': 'phase3-confirmation',
            'executed': False,
            'contract': contract,
            'summary_text': summary_text,
            'tts_text': summary_text,
            'data': data,
        }

    if confirm or action == 'mutate.confirm':
        pending = _pop_pending_action(client_key, confirmation_token)
        if pending is None:
            summary_text = _voice_summary('mutate.confirm.missing', {}, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': False,
                'contract': contract,
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': {'reason': 'no_pending_confirmation'},
            }

        pending_action = str(pending.get('action') or '')
        pending_args = dict(pending.get('args') or {})
        if pending_action == 'mutate.person.rename':
            person_id = int(pending_args.get('person_id') or 0)
            new_name = _normalize_person_name(str(pending_args.get('new_name') or ''))
            person = db_s.get(Person, person_id) if person_id > 0 else None
            if person is None:
                data = {
                    'reason': 'person_not_found',
                    'person_id': person_id,
                    'query': pending_args.get('old_query') or person_id,
                }
                summary_text = _voice_summary('mutate.person.rename.person_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }

            old_name = str(person.display_name or f'#{int(person.id)}')
            if old_name.strip().lower() == new_name.lower():
                data = {'reason': 'no_change', 'name': old_name, 'person_id': int(person.id)}
                summary_text = _voice_summary('mutate.person.rename.no_change', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }

            conflict = _find_name_conflict(int(person.id), new_name)
            if conflict is not None:
                conflict_name = str(conflict[1] or f'#{int(conflict[0])}')
                data = {
                    'reason': 'name_conflict',
                    'person_id': int(person.id),
                    'old_name': old_name,
                    'new_name': new_name,
                    'conflict_person_id': int(conflict[0]),
                    'conflict_name': conflict_name,
                }
                summary_text = _voice_summary('mutate.person.rename.name_conflict', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }

            person.display_name = new_name  # type: ignore[attr-defined]
            db_s.commit()
            data = {
                'reason': 'confirmed_and_executed',
                'person_id': int(person.id),
                'old_name': old_name,
                'new_name': new_name,
            }
            summary_text = _voice_summary('mutate.person.rename.done', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': True,
                'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        if pending_action == 'mutate.people.merge':
            source_id = int(pending_args.get('source_person_id') or 0)
            target_id = int(pending_args.get('target_person_id') or 0)
            source_match, source_label = _resolve_person_ref(source_id, str(pending_args.get('source_query') or ''))
            target_match, target_label = _resolve_person_ref(target_id, str(pending_args.get('target_query') or ''))
            if source_match is None:
                data = {'reason': 'person_not_found', 'query': source_label, 'side': 'source'}
                summary_text = _voice_summary('mutate.people.merge.person_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            if target_match is None:
                data = {'reason': 'person_not_found', 'query': target_label, 'side': 'target'}
                summary_text = _voice_summary('mutate.people.merge.person_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            source_person_id = int(source_match[0])
            target_person_id = int(target_match[0])
            if source_person_id == target_person_id:
                data = {'reason': 'invalid_target', 'source_person_id': source_person_id, 'target_person_id': target_person_id}
                summary_text = _voice_summary('mutate.people.merge.invalid_target', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            try:
                merge_result = people_merge_persons(target_id=target_person_id, source_ids=[source_person_id], db_s=db_s)
            except HTTPException as exc:
                data = {'reason': 'merge_failed', 'detail': str(exc.detail), 'source_person_id': source_person_id, 'target_person_id': target_person_id}
                summary_text = str(exc.detail or 'merge failed')
                return {
                    'success': False,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            data = {
                'reason': 'confirmed_and_executed',
                'source_person_id': source_person_id,
                'target_person_id': target_person_id,
                'source_name': str(source_match[1] or source_label),
                'target_name': str(target_match[1] or target_label),
                'moved_faces': int(merge_result.get('moved_faces', 0)),
                'propagation_task_id': merge_result.get('propagation_task_id'),
            }
            summary_text = _voice_summary('mutate.people.merge.done', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': True,
                'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        if pending_action == 'mutate.face.assign_stranger':
            face_id = int(pending_args.get('face_id') or 0)
            try:
                result = people_assign_face_stranger(face_id=face_id, db_s=db_s)
            except HTTPException:
                data = {'reason': 'face_not_found', 'face_id': face_id}
                summary_text = _voice_summary('mutate.face.assign_stranger.face_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            data = {
                'reason': 'confirmed_and_executed',
                'face_id': face_id,
                'person_id': int(result.get('person_id') or 0),
                'person_name': str(result.get('display_name') or 'Stranger'),
                'propagation_task_id': result.get('propagation_task_id'),
            }
            summary_text = _voice_summary('mutate.face.assign_stranger.done', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': True,
                'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        if pending_action == 'mutate.asset.tag_add':
            asset_id = int(pending_args.get('asset_id') or 0)
            tag_name = _normalize_tag_name(str(pending_args.get('tag_name') or ''))
            if not tag_name:
                data = {'reason': 'invalid_tag', 'asset_id': asset_id}
                summary_text = _voice_summary('mutate.asset.tag_add.invalid_tag', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            asset = db_s.get(Asset, asset_id)
            if asset is None:
                data = {'reason': 'asset_not_found', 'asset_id': asset_id}
                summary_text = _voice_summary('mutate.asset.tag_add.asset_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            tag = (
                db_s.query(Tag)
                .filter(func.lower(Tag.name) == tag_name.lower())
                .order_by(Tag.id.asc())
                .first()
            )
            if tag is None:
                tag = Tag(name=tag_name, type='manual')
                db_s.add(tag)
                db_s.flush()
            blocked = db_s.query(AssetTagBlock).filter(AssetTagBlock.asset_id == asset_id, AssetTagBlock.tag_id == tag.id).first()
            if blocked is not None:
                db_s.delete(blocked)
            link = db_s.query(AssetTag).filter(AssetTag.asset_id == asset_id, AssetTag.tag_id == tag.id).first()
            added = False
            if link is None:
                db_s.add(AssetTag(asset_id=asset_id, tag_id=tag.id, source='manual', model='manual'))
                added = True
            else:
                link.source = 'manual'  # type: ignore[attr-defined]
                link.model = 'manual'  # type: ignore[attr-defined]
            db_s.commit()
            data = {
                'reason': 'confirmed_and_executed',
                'asset_id': asset_id,
                'tag_name': tag_name,
                'tag_id': int(tag.id),
                'added': added,
            }
            summary_text = _voice_summary('mutate.asset.tag_add.done', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': True,
                'contract': {'action': pending_action, 'mode': 'mutate', 'needs_confirmation': False, 'args': pending_args},
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        summary_text = _voice_summary('mutate.confirm.missing', {}, language)
        return {
            'success': True,
            'phase': 'phase3-confirmation',
            'executed': False,
            'contract': contract,
            'summary_text': summary_text,
            'tts_text': summary_text,
            'data': {'reason': 'unknown_pending_action', 'pending_action': pending_action},
        }

    if contract.get('mode') == 'mutate':
        if action == 'mutate.person.rename':
            args = dict(contract.get('args') or {})
            person_id = int(args.get('person_id') or 0)
            query = str(args.get('old_query') or '').strip()
            new_name = _normalize_person_name(str(args.get('new_name') or ''))
            person_match = _find_person_match(person_id, query)
            if person_match is None:
                data = {'reason': 'person_not_found', 'query': query or person_id}
                summary_text = _voice_summary('mutate.person.rename.person_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }

            target_person_id = int(person_match[0])
            old_name = str(person_match[1] or f'#{target_person_id}')
            if old_name.strip().lower() == new_name.lower():
                data = {'reason': 'no_change', 'name': old_name, 'person_id': target_person_id}
                summary_text = _voice_summary('mutate.person.rename.no_change', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }

            conflict = _find_name_conflict(target_person_id, new_name)
            if conflict is not None:
                conflict_name = str(conflict[1] or f'#{int(conflict[0])}')
                data = {
                    'reason': 'name_conflict',
                    'person_id': target_person_id,
                    'old_name': old_name,
                    'new_name': new_name,
                    'conflict_person_id': int(conflict[0]),
                    'conflict_name': conflict_name,
                }
                summary_text = _voice_summary('mutate.person.rename.name_conflict', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }

            pending = _put_pending_action(
                client_key,
                'mutate.person.rename',
                {
                    'person_id': target_person_id,
                    'old_query': query,
                    'old_name': old_name,
                    'new_name': new_name,
                },
            )
            expires_in = max(1, int(float(pending['expires_at']) - time.time()))
            data = {
                'reason': 'confirmation_required',
                'pending_action': 'mutate.person.rename',
                'person_id': target_person_id,
                'old_name': old_name,
                'new_name': new_name,
                'confirmation_token': str(pending['token']),
                'expires_in_sec': expires_in,
            }
            summary_text = _voice_summary('mutate.pending.rename', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': False,
                'contract': contract,
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        if action == 'mutate.people.merge':
            args = dict(contract.get('args') or {})
            source_match, source_label = _resolve_person_ref(
                int(args.get('source_person_id') or 0),
                str(args.get('source_query') or ''),
            )
            target_match, target_label = _resolve_person_ref(
                int(args.get('target_person_id') or 0),
                str(args.get('target_query') or ''),
            )
            if source_match is None:
                data = {'reason': 'person_not_found', 'query': source_label, 'side': 'source'}
                summary_text = _voice_summary('mutate.people.merge.person_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            if target_match is None:
                data = {'reason': 'person_not_found', 'query': target_label, 'side': 'target'}
                summary_text = _voice_summary('mutate.people.merge.person_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            source_person_id = int(source_match[0])
            target_person_id = int(target_match[0])
            if source_person_id == target_person_id:
                data = {'reason': 'invalid_target', 'source_person_id': source_person_id, 'target_person_id': target_person_id}
                summary_text = _voice_summary('mutate.people.merge.invalid_target', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            source_name = str(source_match[1] or source_label)
            target_name = str(target_match[1] or target_label)
            pending = _put_pending_action(
                client_key,
                'mutate.people.merge',
                {
                    'source_person_id': source_person_id,
                    'source_query': source_label,
                    'source_name': source_name,
                    'target_person_id': target_person_id,
                    'target_query': target_label,
                    'target_name': target_name,
                },
            )
            expires_in = max(1, int(float(pending['expires_at']) - time.time()))
            data = {
                'reason': 'confirmation_required',
                'pending_action': 'mutate.people.merge',
                'source_person_id': source_person_id,
                'target_person_id': target_person_id,
                'source_name': source_name,
                'target_name': target_name,
                'confirmation_token': str(pending['token']),
                'expires_in_sec': expires_in,
            }
            summary_text = _voice_summary('mutate.pending.merge', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': False,
                'contract': contract,
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        if action == 'mutate.face.assign_stranger':
            args = dict(contract.get('args') or {})
            face_id = int(args.get('face_id') or 0)
            face = db_s.get(FaceDetection, face_id)
            if face is None:
                data = {'reason': 'face_not_found', 'face_id': face_id}
                summary_text = _voice_summary('mutate.face.assign_stranger.face_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            pending = _put_pending_action(client_key, 'mutate.face.assign_stranger', {'face_id': face_id})
            expires_in = max(1, int(float(pending['expires_at']) - time.time()))
            data = {
                'reason': 'confirmation_required',
                'pending_action': 'mutate.face.assign_stranger',
                'face_id': face_id,
                'asset_id': int(face.asset_id),
                'confirmation_token': str(pending['token']),
                'expires_in_sec': expires_in,
            }
            summary_text = _voice_summary('mutate.pending.assign_stranger', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': False,
                'contract': contract,
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        if action == 'mutate.asset.tag_add':
            args = dict(contract.get('args') or {})
            asset_id = int(args.get('asset_id') or 0)
            tag_name = _normalize_tag_name(str(args.get('tag_name') or ''))
            if not tag_name:
                data = {'reason': 'invalid_tag', 'asset_id': asset_id}
                summary_text = _voice_summary('mutate.asset.tag_add.invalid_tag', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            asset = db_s.get(Asset, asset_id)
            if asset is None:
                data = {'reason': 'asset_not_found', 'asset_id': asset_id}
                summary_text = _voice_summary('mutate.asset.tag_add.asset_not_found', data, language)
                return {
                    'success': True,
                    'phase': 'phase3-confirmation',
                    'executed': False,
                    'contract': contract,
                    'summary_text': summary_text,
                    'tts_text': summary_text,
                    'data': data,
                }
            pending = _put_pending_action(client_key, 'mutate.asset.tag_add', {'asset_id': asset_id, 'tag_name': tag_name})
            expires_in = max(1, int(float(pending['expires_at']) - time.time()))
            data = {
                'reason': 'confirmation_required',
                'pending_action': 'mutate.asset.tag_add',
                'asset_id': asset_id,
                'tag_name': tag_name,
                'confirmation_token': str(pending['token']),
                'expires_in_sec': expires_in,
            }
            summary_text = _voice_summary('mutate.pending.tag_add', data, language)
            return {
                'success': True,
                'phase': 'phase3-confirmation',
                'executed': False,
                'contract': contract,
                'summary_text': summary_text,
                'tts_text': summary_text,
                'data': data,
            }

        summary_text = _voice_summary('mutate.request', {}, language)
        return {
            'success': True,
            'phase': 'phase3-confirmation',
            'executed': False,
            'contract': contract,
            'summary_text': summary_text,
            'tts_text': summary_text,
            'data': {'reason': 'confirmation_required'},
        }

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
        'phase': 'phase3-confirmation',
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
