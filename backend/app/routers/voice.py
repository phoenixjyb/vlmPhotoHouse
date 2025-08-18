from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from typing import Optional
import httpx
import base64

from ..config import get_settings

router = APIRouter()


def _require_enabled():
    s = get_settings()
    if not s.voice_enabled:
        raise HTTPException(status_code=501, detail='Voice service disabled')
    if s.voice_provider != 'external' or not s.voice_external_base_url:
        raise HTTPException(status_code=501, detail='External voice service not configured')
    return s


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
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f'ASR proxy failed: {e}')


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
            r.raise_for_status()
            resp = r.json()
            if not resp.get('success'):
                raise HTTPException(status_code=502, detail=f"TTS service error: {resp.get('error','unknown')}")
            audio_b64 = resp.get('audio_base64') or resp.get('audio_data')
            if not audio_b64:
                raise HTTPException(status_code=502, detail='TTS response missing audio data')
            audio_bytes = base64.b64decode(audio_b64)
            media_type = 'audio/wav' if data['output_format'] == 'wav' else 'audio/mpeg'
            return StreamingResponse(iter([audio_bytes]), media_type=media_type)
    except httpx.HTTPError as e:
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
            r.raise_for_status()
            resp = r.json()
            if not resp.get('success'):
                raise HTTPException(status_code=502, detail=f"Conversation error: {resp.get('error','unknown')}")
            audio_b64 = resp.get('audio_base64') or resp.get('audio_data')
            if not audio_b64:
                # return JSON if no audio (degraded mode)
                return JSONResponse(resp)
            audio_bytes = base64.b64decode(audio_b64)
            media_type = resp.get('content_type') or 'audio/wav'
            return StreamingResponse(iter([audio_bytes]), media_type=media_type)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f'Conversation proxy failed: {e}')


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
                const ttsForm = document.getElementById('ttsForm');
                ttsForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const fd = new FormData(ttsForm);
                    const payload = { text: fd.get('text'), language: fd.get('language'), speed: parseFloat(fd.get('speed')||'1.0') };
                    const res = await fetch('/voice/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                    if (!res.ok) { alert('TTS failed'); return; }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    document.getElementById('ttsAudio').src = url;
                });
                const convForm = document.getElementById('convForm');
                convForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const fd = new FormData(convForm);
                    const res = await fetch('/voice/conversation', { method: 'POST', body: fd });
                    if (!res.ok) { alert('Conversation failed'); return; }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    document.getElementById('convAudio').src = url;
                });
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html, media_type='text/html')
