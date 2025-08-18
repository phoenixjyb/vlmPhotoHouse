from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/ui")
async def ui_home():
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset='utf-8'>
      <title>VLM Photo House — UI</title>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        body{font-family:system-ui,Segoe UI,Arial;margin:1.5rem;line-height:1.4}
        header{display:flex;gap:1rem;align-items:center}
        .cmd{display:flex;gap:.5rem;align-items:center}
        input[type=text]{flex:1;min-width:360px;padding:.6rem .8rem;border:1px solid #ccc;border-radius:8px}
        button{padding:.5rem .8rem;border:1px solid #888;border-radius:8px;background:#fafafa;cursor:pointer}
        .row{display:flex;gap:2rem;align-items:flex-start;margin-top:1rem}
        .card{border:1px solid #e5e5e5;border-radius:10px;padding:1rem}
        .muted{color:#666}
        pre{background:#f6f8fa;padding:.75rem;border-radius:8px;max-height:300px;overflow:auto}
        .pill{display:inline-block;padding:.1rem .5rem;border:1px solid #ddd;border-radius:999px;margin-left:.5rem;color:#555}
      </style>
    </head>
    <body>
      <header>
        <h2 style="margin:0">VLM Photo House</h2>
        <a class="pill" href="/ui/search">Search</a>
        <a class="pill" href="/ui/admin">Admin</a>
      </header>
      <section class="card">
        <h3 style="margin-top:0">Command Bar</h3>
        <div class="cmd">
          <input id="q" type="text" placeholder="Search or type /cmd… (Ctrl/⌘+K)" />
          <button id="btnSearch">Search</button>
          <button id="btnMic">🎤 Hold to Talk</button>
          <select id="lang">
            <option value="en" selected>EN</option>
            <option value="zh">中文</option>
          </select>
        </div>
        <p class="muted" style="margin:.5rem 0 0">Tip: Hold the mic button to record; release to send. Space also works while focused.</p>
        <div id="sttOut" class="muted" style="margin-top:.75rem"></div>
      </section>

      <section class="row">
        <div class="card" style="flex:2">
          <h3 style="margin-top:0">Quick Voice Test</h3>
          <p class="muted">Sends recorded audio to /voice/conversation and plays the AI reply if available.</p>
          <audio id="play" controls style="width:100%"></audio>
        </div>
        <div class="card" style="flex:1">
          <h3 style="margin-top:0">Voice Health</h3>
          <pre id="vh">Loading…</pre>
        </div>
      </section>

      <script>
        // Health load
        fetch('/voice/health').then(r=>r.json()).then(j=>{
          document.getElementById('vh').textContent = JSON.stringify(j, null, 2)
        }).catch(e=>{document.getElementById('vh').textContent = String(e)})

        // Search submit (placeholder: redirects to /ui/search?q=...)
        document.getElementById('btnSearch').addEventListener('click', ()=>{
          const q = document.getElementById('q').value || ''
          location.href = '/ui/search?q=' + encodeURIComponent(q)
        })

        // Simple PTT using MediaRecorder
        let media, rec, chunks=[]
        const btn = document.getElementById('btnMic')
        const langSel = document.getElementById('lang')
        const sttOut = document.getElementById('sttOut')
        async function startRec(){
          if(!media){ media = await navigator.mediaDevices.getUserMedia({audio:true}); }
          chunks=[]
          rec = new MediaRecorder(media, {mimeType: 'audio/webm'});
          rec.ondataavailable = e=>{ if(e.data.size>0) chunks.push(e.data) }
          rec.onstop = async ()=>{
            const blob = new Blob(chunks, {type:'audio/webm'})
            const fd = new FormData()
            fd.append('audio', blob, 'audio.webm')
            fd.append('language', langSel.value)
            const r = await fetch('/voice/conversation', { method:'POST', body: fd })
            if(r.ok){
              const ct = r.headers.get('content-type')||''
              if(ct.startsWith('audio/')){
                const b = await r.blob();
                document.getElementById('play').src = URL.createObjectURL(b)
                sttOut.textContent = 'Voice reply ready.'
              } else {
                const j = await r.json();
                sttOut.textContent = (j && j.text_response) ? j.text_response : JSON.stringify(j)
              }
            } else {
              sttOut.textContent = 'Voice conversation failed ('+r.status+')'
            }
          }
          rec.start()
          btn.textContent = '● Recording… Release to send'
        }
        function stopRec(){ if(rec && rec.state!=='inactive'){ rec.stop(); btn.textContent = '🎤 Hold to Talk' } }
        btn.addEventListener('mousedown', startRec)
        btn.addEventListener('touchstart', (e)=>{e.preventDefault(); startRec()})
        btn.addEventListener('mouseup', stopRec)
        btn.addEventListener('mouseleave', stopRec)
        btn.addEventListener('touchend', (e)=>{e.preventDefault(); stopRec()})
        // Spacebar PTT when button is focused
        btn.addEventListener('keydown', (e)=>{ if(e.code==='Space'){ e.preventDefault(); startRec() } })
        btn.addEventListener('keyup', (e)=>{ if(e.code==='Space'){ e.preventDefault(); stopRec() } })
      </script>
    </body>
    </html>
    """
    return HTMLResponse(html)


@router.get("/ui/search")
async def ui_search(q: str | None = None):
    # Placeholder page; a real version would render results and filters
    html = f"""
    <!doctype html>
    <html>
    <head><meta charset='utf-8'><title>Search</title>
    <style>body{{font-family:system-ui; margin:1.5rem}} a.pill{{display:inline-block;padding:.1rem .5rem;border:1px solid #ddd;border-radius:999px;margin-right:.5rem}}</style>
    </head>
    <body>
      <h2>Search</h2>
      <p><a class='pill' href='/ui'>Home</a><a class='pill' href='/ui/admin'>Admin</a></p>
      <form method='GET' action='/ui/search'>
        <input type='text' name='q' value="{(q or '').replace('"','&quot;')}" placeholder='Query…' style='padding:.5rem .7rem;min-width:360px'>
        <button type='submit'>Search</button>
      </form>
      <p style='color:#666'>Query: <strong>{(q or '(none)')}</strong></p>
      <p>Results UI coming next: filters, grid, and lightbox. This page is a scaffold.</p>
    </body>
    </html>
    """
    return HTMLResponse(html)


@router.get("/ui/admin")
async def ui_admin():
    html = """
    <!doctype html>
    <html>
    <head><meta charset='utf-8'><title>Admin</title>
    <style>
      body{font-family:system-ui; margin:1.5rem}
      .grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
      .card{border:1px solid #e5e5e5;border-radius:10px;padding:1rem}
      pre{background:#f6f8fa;padding:.75rem;border-radius:8px;max-height:360px;overflow:auto}
    </style>
    </head>
    <body>
      <h2>Admin</h2>
      <p><a href='/ui'>← Back to UI</a></p>
      <div class='grid'>
        <div class='card'>
          <h3>Health</h3>
          <pre id='h'>Loading…</pre>
        </div>
        <div class='card'>
          <h3>Metrics</h3>
          <pre id='m'>Loading…</pre>
        </div>
        <div class='card'>
          <h3>Voice Health</h3>
          <pre id='vh'>Loading…</pre>
        </div>
        <div class='card'>
          <h3>Actions</h3>
          <p><a href='/voice/demo' target='_blank'>Open Voice Demo</a></p>
          <p style='color:#666'>Next steps: toggles for VIDEO_ENABLED, caption profile, and tooling (rebuild index, re-embed, recluster).</p>
        </div>
      </div>
      <script>
        fetch('/health').then(r=>r.json()).then(j=>{document.getElementById('h').textContent=JSON.stringify(j,null,2)})
        fetch('/metrics').then(r=>r.json()).then(j=>{document.getElementById('m').textContent=JSON.stringify(j,null,2)})
        fetch('/voice/health').then(r=>r.json()).then(j=>{document.getElementById('vh').textContent=JSON.stringify(j,null,2)})
      </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
