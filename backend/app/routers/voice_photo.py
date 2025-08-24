"""
Enhanced Voice Service for VLM Photo Engine
Integrates TTS/ASR with photo management and RTX 3090 optimization.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body, Depends
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from typing import Optional, List, Dict, Any
import httpx
import base64
import subprocess
import tempfile
import os
import asyncio
import json
from sqlalchemy.orm import Session

from ..config import get_settings
from ..dependencies import get_db
from ..db import Asset
from .voice import _require_enabled, _piper_tts_bytes

router = APIRouter()

@router.post('/voice/describe-photo')
async def describe_photo_with_voice(
    asset_id: int = Form(...),
    language: Optional[str] = Form('en'),
    voice: Optional[str] = Form('default'),
    speed: float = Form(1.0),
    db: Session = Depends(get_db)
):
    """
    Generate audio description of a photo using its caption and metadata.
    Utilizes RTX 3090 for TTS processing.
    """
    s = _require_enabled()
    
    # Fetch the asset from database
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    # Build description from available metadata
    description_parts = []
    
    if asset.caption_text:
        description_parts.append(f"This image shows {asset.caption_text}")
    
    if asset.camera_make and asset.camera_model:
        description_parts.append(f"Photo taken with {asset.camera_make} {asset.camera_model}")
    
    if asset.date_taken:
        description_parts.append(f"captured on {asset.date_taken.strftime('%B %d, %Y')}")
    
    if asset.gps_latitude and asset.gps_longitude:
        description_parts.append(f"at coordinates {asset.gps_latitude:.4f}, {asset.gps_longitude:.4f}")
    
    if asset.file_size_bytes:
        size_mb = asset.file_size_bytes / (1024 * 1024)
        description_parts.append(f"File size: {size_mb:.1f} megabytes")
    
    if not description_parts:
        description_parts.append(f"Photo file: {asset.orig_filename}")
    
    description_text = ". ".join(description_parts) + "."
    
    # Generate TTS using the voice service
    url = s.voice_external_base_url.rstrip('/') + s.voice_tts_path
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            data = {
                'text': description_text,
                'language': language or 'en',
                'voice_speed': speed,
                'output_format': 'wav',
            }
            r = await client.post(url, headers=headers, data=data)
            
            try:
                resp = r.json()
            except Exception:
                resp = {'success': False, 'error': r.text or 'TTS error', 'status': r.status_code}

            audio_bytes: Optional[bytes] = None
            if resp.get('success', False):
                audio_b64 = resp.get('audio_base64') or resp.get('audio_data')
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)

            # Fallback to Piper if configured and no audio
            if audio_bytes is None and getattr(s, 'tts_fallback_provider', 'none') == 'piper' and s.piper_exe_path and s.piper_model_path:
                audio_bytes = _piper_tts_bytes(description_text, s.piper_exe_path, s.piper_model_path)
                if audio_bytes is not None:
                    return StreamingResponse(iter([audio_bytes]), media_type='audio/wav')

            # Return JSON with description if no audio
            if audio_bytes is None:
                return JSONResponse({
                    'success': False, 
                    'error': 'TTS unavailable',
                    'description_text': description_text,
                    'asset_id': asset_id
                }, status_code=200)

            return StreamingResponse(iter([audio_bytes]), media_type='audio/wav')
            
    except httpx.HTTPError as e:
        # Return description text for fallback
        return JSONResponse({
            'success': False,
            'error': f'TTS service failed: {e}',
            'description_text': description_text,
            'asset_id': asset_id
        }, status_code=200)

@router.post('/voice/search-photos')
async def search_photos_by_voice(
    audio: UploadFile = File(...),
    language: Optional[str] = Form('en'),
    max_results: int = Form(10),
    db: Session = Depends(get_db)
):
    """
    Search photos using voice input. Transcribes audio and performs text search.
    """
    s = _require_enabled()
    
    # Transcribe audio to text
    transcribe_url = s.voice_external_base_url.rstrip('/') + s.voice_asr_path
    headers = {'Authorization': f'Bearer {s.voice_api_key}'} if s.voice_api_key else {}
    
    try:
        async with httpx.AsyncClient(timeout=s.voice_timeout_sec, trust_env=False) as client:
            files = {'audio_file': (audio.filename or 'audio.webm', await audio.read(), audio.content_type or 'audio/webm')}
            data = {'language': language or 'en'}
            
            r = await client.post(transcribe_url, headers=headers, files=files, data=data)
            
            try:
                resp = r.json()
            except Exception:
                return JSONResponse({'success': False, 'error': 'ASR transcription failed'}, status_code=200)
            
            if not resp.get('success', False):
                return JSONResponse({'success': False, 'error': 'Voice transcription failed'}, status_code=200)
            
            transcribed_text = resp.get('text', '').strip()
            if not transcribed_text:
                return JSONResponse({'success': False, 'error': 'No text transcribed from audio'}, status_code=200)
            
            # Search photos by caption text
            assets = db.query(Asset).filter(
                Asset.caption_text.ilike(f'%{transcribed_text}%')
            ).limit(max_results).all()
            
            results = []
            for asset in assets:
                results.append({
                    'id': asset.id,
                    'filename': asset.orig_filename,
                    'caption': asset.caption_text,
                    'date_taken': asset.date_taken.isoformat() if asset.date_taken else None,
                    'camera': f"{asset.camera_make} {asset.camera_model}" if asset.camera_make else None
                })
            
            return JSONResponse({
                'success': True,
                'transcribed_text': transcribed_text,
                'results_count': len(results),
                'results': results
            })
            
    except httpx.HTTPError as e:
        return JSONResponse({'success': False, 'error': f'Voice search failed: {e}'}, status_code=200)

@router.get('/voice/rtx3090-status')
async def get_rtx3090_voice_status():
    """
    Check RTX 3090 status for voice services by querying the external voice service.
    """
    s = _require_enabled()
    
    # Check RTX 3090 availability via voice service
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try to get basic response from voice service (test connectivity)
            response = await client.get(f"{s.voice_external_base_url}/")
            if response.status_code == 200:
                # Voice service is responding, check local GPU status
                # Since this is the main VLM Photo Engine, check local RTX 3090
                try:
                    import torch
                    if torch.cuda.is_available():
                        device_count = torch.cuda.device_count()
                        devices = []
                        rtx3090_available = False
                        
                        for i in range(device_count):
                            gpu_name = torch.cuda.get_device_name(i)
                            memory_gb = torch.cuda.get_device_properties(i).total_memory / 1e9
                            devices.append({
                                'id': i,
                                'name': gpu_name,
                                'memory_gb': round(memory_gb, 1)
                            })
                            if "RTX 3090" in gpu_name:
                                rtx3090_available = True
                        
                        return JSONResponse({
                            'success': True,
                            'rtx3090_available': rtx3090_available,
                            'cuda_devices': devices,
                            'voice_service_url': s.voice_external_base_url,
                            'voice_enabled': s.voice_enabled,
                            'voice_service_status': 'connected'
                        })
                    else:
                        return JSONResponse({
                            'success': True,
                            'rtx3090_available': False,
                            'cuda_devices': [],
                            'voice_service_url': s.voice_external_base_url,
                            'voice_enabled': s.voice_enabled,
                            'voice_service_status': 'connected',
                            'error': 'CUDA not available in main environment'
                        })
                except ImportError:
                    return JSONResponse({
                        'success': False,
                        'rtx3090_available': False,
                        'cuda_devices': [],
                        'voice_service_url': s.voice_external_base_url,
                        'voice_enabled': s.voice_enabled,
                        'voice_service_status': 'connected',
                        'error': 'PyTorch not available for GPU detection'
                    })
            else:
                return JSONResponse({
                    'success': False,
                    'rtx3090_available': False,
                    'cuda_devices': [],
                    'voice_service_url': s.voice_external_base_url,
                    'voice_enabled': s.voice_enabled,
                    'error': f'Voice service not responding (HTTP {response.status_code})'
                })
                
    except httpx.HTTPError as e:
        return JSONResponse({
            'success': False,
            'rtx3090_available': False,
            'cuda_devices': [],
            'voice_service_url': s.voice_external_base_url,
            'voice_enabled': s.voice_enabled,
            'error': f'Voice service connection failed: {e}'
        })
    except Exception as e:
        return JSONResponse({
            'success': False,
            'rtx3090_available': False,
            'cuda_devices': [],
            'error': f'Unexpected error: {e}'
        })

@router.get('/voice/photo-demo')
async def voice_photo_demo():
    """
    Demo page for voice-enabled photo interactions.
    """
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Voice Photo Demo - RTX 3090 Enhanced</title>
        <style>
            body{font-family:system-ui,Segoe UI,Arial;margin:2rem;max-width:1000px;background:#f8f9fa;}
            .card{background:white;padding:1.5rem;margin:1rem 0;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);}
            .rtx-badge{background:linear-gradient(45deg,#76b900,#00d4ff);color:white;padding:0.25rem 0.5rem;border-radius:4px;font-size:0.8rem;font-weight:bold;}
            .photo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin:1rem 0;}
            .photo-item{border:1px solid #ddd;border-radius:4px;padding:0.5rem;text-align:center;}
            .photo-item img{max-width:100%;height:150px;object-fit:cover;border-radius:4px;}
            .controls{display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;margin:0.5rem 0;}
            .btn{padding:0.5rem 1rem;border:none;border-radius:4px;cursor:pointer;font-size:0.9rem;}
            .btn-primary{background:#007bff;color:white;}
            .btn-success{background:#28a745;color:white;}
            .btn-warning{background:#ffc107;color:black;}
            .status{padding:0.75rem;border-radius:4px;margin:0.5rem 0;}
            .status.success{background:#d4edda;border:1px solid #c3e6cb;color:#155724;}
            .status.error{background:#f8d7da;border:1px solid #f5c6cb;color:#721c24;}
            #statusInfo{font-family:monospace;font-size:0.85rem;background:#f8f9fa;padding:0.5rem;border-radius:4px;}
        </style>
    </head>
    <body>
        <h1>🎙️ Voice Photo Engine <span class="rtx-badge">RTX 3090</span></h1>
        
        <div class="card">
            <h2>🚀 RTX 3090 Status</h2>
            <button class="btn btn-primary" onclick="checkRTXStatus()">Check RTX 3090 Status</button>
            <div id="statusInfo"></div>
        </div>
        
        <div class="card">
            <h2>🖼️ Voice Photo Description</h2>
            <p>Generate audio descriptions of photos using RTX 3090-powered TTS.</p>
            <div class="controls">
                <label>Asset ID: <input type="number" id="assetId" value="1" min="1"></label>
                <label>Language: <select id="descLang"><option value="en">English</option><option value="zh">Chinese</option></select></label>
                <label>Speed: <input type="number" id="descSpeed" value="1.0" step="0.1" min="0.5" max="2.0"></label>
                <button class="btn btn-success" onclick="describePhoto()">🔊 Describe Photo</button>
            </div>
            <audio id="photoAudio" controls style="width:100%;margin-top:0.5rem;"></audio>
            <div id="photoDescription"></div>
        </div>
        
        <div class="card">
            <h2>🎤 Voice Photo Search</h2>
            <p>Search photos by speaking. Powered by RTX 3090 ASR processing.</p>
            <div class="controls">
                <button class="btn btn-warning" id="searchRecBtn">🎤 Start Voice Search</button>
                <label>Language: <select id="searchLang"><option value="en">English</option><option value="zh">Chinese</option></select></label>
                <label>Max Results: <input type="number" id="maxResults" value="5" min="1" max="20"></label>
            </div>
            <div id="searchResults"></div>
        </div>
        
        <div class="card">
            <h2>🎵 Voice Controls</h2>
            <div class="controls">
                <button class="btn btn-primary" onclick="testTTS()">Test TTS</button>
                <button class="btn btn-primary" onclick="checkVoiceHealth()">Voice Health Check</button>
            </div>
            <div id="voiceStatus"></div>
        </div>

        <script>
            function showStatus(elementId, message, isError = false) {
                const el = document.getElementById(elementId);
                el.innerHTML = `<div class="status ${isError ? 'error' : 'success'}">${message}</div>`;
            }

            async function checkRTXStatus() {
                try {
                    const response = await fetch('/voice/rtx3090-status');
                    const data = await response.json();
                    
                    let statusHtml = `<h3>GPU Status</h3>`;
                    if (data.success) {
                        statusHtml += `<p><strong>RTX 3090 Available:</strong> ${data.rtx3090_available ? '✅ Yes' : '❌ No'}</p>`;
                        statusHtml += `<p><strong>CUDA Devices:</strong></p><ul>`;
                        data.cuda_devices.forEach(device => {
                            statusHtml += `<li>GPU ${device.id}: ${device.name} (${device.memory_gb}GB)</li>`;
                        });
                        statusHtml += `</ul>`;
                        statusHtml += `<p><strong>Voice Service:</strong> ${data.voice_service_url}</p>`;
                    } else {
                        statusHtml += `<p class="status error">Error: ${data.error}</p>`;
                    }
                    
                    document.getElementById('statusInfo').innerHTML = statusHtml;
                } catch (error) {
                    document.getElementById('statusInfo').innerHTML = `<div class="status error">Failed to check RTX status: ${error}</div>`;
                }
            }

            async function describePhoto() {
                const assetId = document.getElementById('assetId').value;
                const language = document.getElementById('descLang').value;
                const speed = document.getElementById('descSpeed').value;
                
                try {
                    const formData = new FormData();
                    formData.append('asset_id', assetId);
                    formData.append('language', language);
                    formData.append('speed', speed);
                    
                    const response = await fetch('/voice/describe-photo', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const contentType = response.headers.get('content-type') || '';
                    if (contentType.startsWith('audio/')) {
                        const blob = await response.blob();
                        const url = URL.createObjectURL(blob);
                        document.getElementById('photoAudio').src = url;
                        showStatus('photoDescription', `🎵 Audio description generated for photo ${assetId}`);
                    } else {
                        const data = await response.json();
                        if (data.description_text) {
                            showStatus('photoDescription', `📝 Description: ${data.description_text}`, !data.success);
                        } else {
                            showStatus('photoDescription', `Error: ${data.error}`, true);
                        }
                    }
                } catch (error) {
                    showStatus('photoDescription', `Failed to describe photo: ${error}`, true);
                }
            }

            async function testTTS() {
                try {
                    const response = await fetch('/voice/tts', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            text: 'RTX 3090 TTS test successful. Voice processing optimized.',
                            language: 'en',
                            speed: 1.0
                        })
                    });
                    
                    const contentType = response.headers.get('content-type') || '';
                    if (contentType.startsWith('audio/')) {
                        const blob = await response.blob();
                        const url = URL.createObjectURL(blob);
                        const audio = new Audio(url);
                        audio.play();
                        showStatus('voiceStatus', '🔊 RTX 3090 TTS test successful');
                    } else {
                        const data = await response.json();
                        showStatus('voiceStatus', `TTS Error: ${data.error}`, true);
                    }
                } catch (error) {
                    showStatus('voiceStatus', `TTS test failed: ${error}`, true);
                }
            }

            async function checkVoiceHealth() {
                try {
                    const response = await fetch('/voice/health');
                    const data = await response.json();
                    showStatus('voiceStatus', `Voice Health: ${JSON.stringify(data, null, 2)}`);
                } catch (error) {
                    showStatus('voiceStatus', `Health check failed: ${error}`, true);
                }
            }

            // Voice search recording
            let mediaRecorder = null;
            let chunks = [];

            document.getElementById('searchRecBtn').addEventListener('click', async () => {
                const btn = document.getElementById('searchRecBtn');
                
                if (!mediaRecorder || mediaRecorder.state === 'inactive') {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                        chunks = [];
                        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                        
                        mediaRecorder.ondataavailable = (e) => {
                            if (e.data && e.data.size) chunks.push(e.data);
                        };
                        
                        mediaRecorder.onstop = async () => {
                            const blob = new Blob(chunks, { type: 'audio/webm' });
                            const formData = new FormData();
                            formData.append('audio', blob, 'search.webm');
                            formData.append('language', document.getElementById('searchLang').value);
                            formData.append('max_results', document.getElementById('maxResults').value);
                            
                            try {
                                const response = await fetch('/voice/search-photos', {
                                    method: 'POST',
                                    body: formData
                                });
                                
                                const data = await response.json();
                                
                                if (data.success) {
                                    let resultsHtml = `<h3>🔍 Search Results for: "${data.transcribed_text}"</h3>`;
                                    resultsHtml += `<p>Found ${data.results_count} photos</p>`;
                                    
                                    if (data.results.length > 0) {
                                        resultsHtml += '<div class="photo-grid">';
                                        data.results.forEach(photo => {
                                            resultsHtml += `
                                                <div class="photo-item">
                                                    <strong>ID: ${photo.id}</strong><br>
                                                    ${photo.filename}<br>
                                                    <em>${photo.caption || 'No caption'}</em><br>
                                                    ${photo.date_taken ? new Date(photo.date_taken).toLocaleDateString() : ''}<br>
                                                    ${photo.camera || ''}
                                                </div>
                                            `;
                                        });
                                        resultsHtml += '</div>';
                                    }
                                    
                                    document.getElementById('searchResults').innerHTML = resultsHtml;
                                } else {
                                    showStatus('searchResults', `Search failed: ${data.error}`, true);
                                }
                                
                            } catch (error) {
                                showStatus('searchResults', `Voice search failed: ${error}`, true);
                            }
                            
                            stream.getTracks().forEach(track => track.stop());
                            btn.textContent = '🎤 Start Voice Search';
                        };
                        
                        mediaRecorder.start();
                        btn.textContent = '⏹️ Stop Recording';
                        
                    } catch (error) {
                        showStatus('searchResults', `Microphone error: ${error}`, true);
                    }
                } else {
                    mediaRecorder.stop();
                }
            });

            // Auto-check RTX status on load
            window.addEventListener('load', () => {
                checkRTXStatus();
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html, media_type='text/html')
