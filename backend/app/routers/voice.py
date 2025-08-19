from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from typing import Optional
import httpx
import base64
import subprocess
import tempfile
import os

from ..config import get_settings

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
                ttsForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const fd = new FormData(ttsForm);
                    const payload = { text: fd.get('text'), language: fd.get('language'), speed: parseFloat(fd.get('speed')||'1.0') };
                    const res = await fetch('/voice/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                    if (!res.ok) { alert('TTS failed ('+res.status+')'); return; }
                    const ct = res.headers.get('content-type') || '';
                    if (ct.startsWith('audio/')) {
                        const blob = await res.blob();
                        const url = URL.createObjectURL(blob);
                        document.getElementById('ttsAudio').src = url;
                    } else {
                        const j = await res.json().catch(()=>null);
                        const msg = j?.error || j?.text || j?.text_response || payload.text || 'TTS unavailable';
                        speak(msg, payload.language || 'en');
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
