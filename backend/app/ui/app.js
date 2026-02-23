const state = {
  activeTab: "library",
  selectedAsset: null,
  persons: [],
  namedPersons: [],
  assetMap: new Map(),
};

const qs = (id) => document.getElementById(id);

function esc(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function basename(path) {
  const raw = String(path || "");
  const p = raw.replaceAll("\\", "/");
  return p.split("/").pop() || raw;
}

function isVideoAsset(asset) {
  const mime = String(asset?.mime || "").toLowerCase();
  if (mime.startsWith("video/")) {
    return true;
  }
  const p = String(asset?.path || "").toLowerCase();
  return [".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"].some((ext) => p.endsWith(ext));
}

function showToast(message) {
  const toast = qs("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function tabToUrl(tab) {
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  window.history.replaceState(null, "", url.toString());
}

async function api(url, opts = {}) {
  const options = { ...opts };
  options.headers = options.headers || {};
  if (options.body && !(options.body instanceof FormData)) {
    options.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, options);
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = data?.detail || data?.error?.message || data || `HTTP ${res.status}`;
    throw new Error(String(detail));
  }
  return data;
}

function setActiveTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".tab").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((el) => {
    el.classList.toggle("active", el.id === `tab-${tab}`);
  });
  tabToUrl(tab);
}

function renderAssetGrid(items, containerId) {
  const root = qs(containerId);
  items.forEach((asset) => state.assetMap.set(Number(asset.id), asset));
  root.innerHTML = items
    .map((asset) => {
      const id = Number(asset.id);
      const selected = state.selectedAsset && Number(state.selectedAsset.id) === id ? "selected" : "";
      return `
        <article class="asset-card ${selected}" data-asset-id="${id}">
          <div class="thumb">
            <img loading="lazy" src="/assets/${id}/thumbnail?size=256"
                 alt="${esc(basename(asset.path))}"
                 onerror="this.remove(); this.parentElement.querySelector('.fallback').style.display='grid';" />
            <span class="fallback" style="display:none;">No thumbnail</span>
          </div>
          <div class="asset-meta">
            <p class="id">#${id}</p>
            <p class="name" title="${esc(asset.path)}">${esc(basename(asset.path))}</p>
          </div>
        </article>
      `;
    })
    .join("");
}

async function refreshDashboard() {
  try {
    const [health, metrics] = await Promise.all([api("/health"), api("/metrics")]);
    qs("stat-assets").textContent = metrics.assets?.total ?? "-";
    qs("stat-captions").textContent = metrics.captions ?? "-";
    qs("stat-faces").textContent = metrics.faces ?? "-";
    qs("stat-persons").textContent = metrics.persons ?? "-";
    qs("stat-pending").textContent = health.pending_tasks ?? "-";
    qs("stat-health").textContent = health.ok ? "OK" : "DEGRADED";
    qs("stat-health").style.color = health.ok ? "#0f8a66" : "#b73a3a";
  } catch (e) {
    showToast(`Dashboard refresh failed: ${e.message}`);
  }
}

async function loadLibraryLatest() {
  try {
    const data = await api("/assets?page=1&page_size=120");
    const assets = data.assets || [];
    qs("library-result-meta").textContent = `Latest assets: ${assets.length} shown of ${data.total || assets.length}`;
    renderAssetGrid(assets, "library-grid");
  } catch (e) {
    showToast(`Library load failed: ${e.message}`);
  }
}

function parseTagsInput() {
  return String(qs("search-tags").value || "")
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

function normalizeSearch(mode, data) {
  if (mode === "path") {
    return (data.items || []).map((v) => ({ id: v.id, path: v.path }));
  }
  if (mode === "caption") {
    return (data.results || []).map((v) => ({ id: v.asset_id, path: v.path, mime: v.mime }));
  }
  if (mode === "smart") {
    return (data.results || []).map((v) => ({
      id: v.asset_id,
      path: v.path,
      score: v.score,
      mime: v.mime,
    }));
  }
  if (mode === "person") {
    return (data.items || []).map((v) => ({ id: v.id, path: v.path }));
  }
  return [];
}

async function runSearch() {
  const mode = qs("search-mode").value;
  const q = String(qs("search-query").value || "").trim();
  const media = qs("search-media").value;
  const tags = parseTagsInput();

  try {
    let payload = null;
    if (mode === "path") {
      if (!q) {
        await loadLibraryLatest();
        return;
      }
      payload = await api(`/search?q=${encodeURIComponent(q)}&page=1&page_size=120`);
    } else if (mode === "caption") {
      if (!q) {
        showToast("Caption mode needs text");
        return;
      }
      payload = await api("/search/captions", {
        method: "POST",
        body: JSON.stringify({ text: q, k: 120, media }),
      });
    } else if (mode === "smart") {
      payload = await api("/search/smart", {
        method: "POST",
        body: JSON.stringify({
          text: q || null,
          tags: tags.length ? tags : null,
          media,
          k: 120,
        }),
      });
    } else if (mode === "person") {
      if (!q) {
        showToast("Person mode needs a name");
        return;
      }
      payload = await api(`/search/person/name/${encodeURIComponent(q)}?page=1&page_size=120`);
    }

    const items = normalizeSearch(mode, payload || {});
    qs("library-result-meta").textContent = `Mode: ${mode} | Results: ${items.length}`;
    renderAssetGrid(items, "library-grid");
  } catch (e) {
    showToast(`Search failed: ${e.message}`);
  }
}

async function loadAssetInspector(assetId) {
  const asset = state.assetMap.get(Number(assetId));
  if (!asset) {
    return;
  }
  state.selectedAsset = asset;
  renderAssetGrid(Array.from(state.assetMap.values()), "library-grid");

  qs("asset-empty").classList.add("hidden");
  qs("asset-inspector").classList.remove("hidden");
  qs("asset-id").textContent = `Asset #${asset.id}`;
  qs("asset-path").textContent = asset.path || "(unknown path)";

  const preview = qs("asset-preview");
  if (isVideoAsset(asset)) {
    preview.innerHTML = `<video controls preload="metadata" src="/assets/${asset.id}/media"></video>`;
  } else {
    preview.innerHTML = `<img src="/assets/${asset.id}/media" alt="${esc(basename(asset.path))}" />`;
  }

  try {
    const [captions, tags, faces] = await Promise.all([
      api(`/assets/${asset.id}/captions`),
      api(`/assets/${asset.id}/tags`),
      api(`/faces?asset_id=${asset.id}&page=1&page_size=200`),
    ]);
    renderCaptions(captions.captions || []);
    renderTags(tags.tags || []);
    renderFaces(faces.faces || []);
  } catch (e) {
    showToast(`Inspector load failed: ${e.message}`);
  }
}

function renderCaptions(captions) {
  const root = qs("caption-list");
  if (!captions.length) {
    root.innerHTML = `<p class="muted">No captions yet.</p>`;
    return;
  }
  root.innerHTML = captions
    .map(
      (c) => `
        <article class="caption-item" data-caption-id="${c.id}">
          <p class="small muted">#${c.id} | ${esc(c.model || "unknown")} | edited=${Boolean(c.user_edited)}</p>
          <textarea id="caption-text-${c.id}">${esc(c.text || "")}</textarea>
          <div class="controls">
            <button class="btn" data-action="save-caption" data-caption-id="${c.id}">Save</button>
            <button class="btn danger" data-action="delete-caption" data-caption-id="${c.id}">Delete</button>
          </div>
        </article>
      `
    )
    .join("");
}

function renderTags(tags) {
  const root = qs("tag-list");
  if (!tags.length) {
    root.innerHTML = `<span class="muted">No tags.</span>`;
    return;
  }
  root.innerHTML = tags.map((t) => `<span class="tag-chip">${esc(t.name)}</span>`).join("");
}

function personOptions(currentId) {
  const base = [`<option value="">Assign to person...</option>`];
  const merged = [];
  const seen = new Set();
  for (const p of state.namedPersons) {
    if (seen.has(p.id)) continue;
    seen.add(p.id);
    merged.push(p);
  }
  for (const p of state.persons) {
    if (seen.has(p.id)) continue;
    seen.add(p.id);
    merged.push(p);
  }

  for (const p of merged.slice(0, 300)) {
    const name = p.display_name || `Person ${p.id}`;
    const selected = Number(currentId) === Number(p.id) ? "selected" : "";
    base.push(`<option value="${p.id}" ${selected}>${esc(name)}</option>`);
  }
  return base.join("");
}

function renderFaces(faces) {
  const root = qs("face-list");
  if (!faces.length) {
    root.innerHTML = `<p class="muted">No face detections for this asset.</p>`;
    return;
  }
  root.innerHTML = faces
    .map(
      (f) => `
        <article class="face-card">
          <img src="/faces/${f.id}/crop?size=256" alt="face ${f.id}" />
          <div class="face-body">
            <p class="small muted">Face #${f.id}</p>
            <select id="face-person-${f.id}">${personOptions(f.person_id)}</select>
            <div class="controls">
              <button class="btn ghost" data-action="assign-face" data-face-id="${f.id}">Assign</button>
              <button class="btn ghost" data-action="create-person-face" data-face-id="${f.id}">New Person</button>
              <button class="btn danger" data-action="delete-face" data-face-id="${f.id}">Not Face</button>
            </div>
          </div>
        </article>
      `
    )
    .join("");
}

async function loadPeople() {
  try {
    const [data, named] = await Promise.all([
      api("/persons?page=1&page_size=240&include_faces=true&sort_by=face_count&order=desc"),
      api("/persons?page=1&page_size=500&include_faces=false&named_only=true&sort_by=face_count&order=desc"),
    ]);
    state.persons = data.persons || [];
    state.namedPersons = named.persons || [];
    renderPeopleList();
    await loadUnassignedFaces();
  } catch (e) {
    showToast(`People load failed: ${e.message}`);
  }
}

function renderPeopleList() {
  const root = qs("people-list");
  if (!state.persons.length) {
    root.innerHTML = `<p class="muted">No persons yet.</p>`;
    return;
  }
  root.innerHTML = state.persons
    .map((p) => {
      const display = p.display_name || `Person ${p.id}`;
      const samples = (p.sample_faces || [])
        .map((fid) => `<img src="/faces/${fid}/crop?size=256" alt="face ${fid}" />`)
        .join("");
      return `
        <article class="person-card">
          <p><strong>${esc(display)}</strong></p>
          <p class="small muted">id=${p.id} | faces=${p.face_count}</p>
          <input id="person-name-${p.id}" type="text" value="${esc(p.display_name || "")}" placeholder="Display name" />
          <div class="controls">
            <button class="btn ghost" data-action="rename-person" data-person-id="${p.id}">Save Name</button>
            <button class="btn ghost" data-action="view-person-assets" data-person-id="${p.id}">View Assets</button>
          </div>
          <div class="person-samples">${samples}</div>
        </article>
      `;
    })
    .join("");
}

async function loadPersonAssets(personId) {
  try {
    const data = await api(`/search/person/${personId}?page=1&page_size=120`);
    const items = data.items || [];
    qs("person-assets-meta").textContent = `Person ${personId}: ${items.length} assets`;
    const normalized = items.map((x) => ({ id: x.id, path: x.path }));
    renderAssetGrid(normalized, "person-assets-grid");
  } catch (e) {
    showToast(`Person assets load failed: ${e.message}`);
  }
}

async function loadUnassignedFaces() {
  try {
    const data = await api("/faces?unassigned=true&page=1&page_size=120");
    const faces = data.faces || [];
    const root = qs("unassigned-faces");
    if (!faces.length) {
      root.innerHTML = `<p class="muted">No unassigned faces.</p>`;
      return;
    }
    root.innerHTML = faces
      .map(
        (f) => `
          <article class="face-card">
            <img src="/faces/${f.id}/crop?size=256" alt="face ${f.id}" />
            <div class="face-body">
              <p class="small muted">Face #${f.id}, asset #${f.asset_id}</p>
              <select id="face-person-unassigned-${f.id}">${personOptions(null)}</select>
              <div class="controls">
                <button class="btn ghost" data-action="assign-face-unassigned" data-face-id="${f.id}">Assign</button>
                <button class="btn ghost" data-action="create-person-face" data-face-id="${f.id}">New Person</button>
                <button class="btn danger" data-action="delete-face-unassigned" data-face-id="${f.id}">Not Face</button>
              </div>
            </div>
          </article>
        `
      )
      .join("");
  } catch (e) {
    showToast(`Unassigned faces load failed: ${e.message}`);
  }
}

async function loadTasks() {
  try {
    const data = await api("/tasks?page=1&page_size=180");
    const tasks = data.tasks || [];
    const byState = tasks.reduce((acc, t) => {
      acc[t.state] = (acc[t.state] || 0) + 1;
      return acc;
    }, {});
    qs("task-meta").textContent = `Total=${tasks.length} | pending=${byState.pending || 0} | running=${byState.running || 0} | failed=${byState.failed || 0} | dead=${byState.dead || 0}`;
    qs("task-rows").innerHTML = tasks
      .map((t) => {
        const progress = t.progress_total ? `${t.progress_current || 0}/${t.progress_total}` : "-";
        const canCancel = t.state === "pending" || t.state === "running";
        return `
          <tr>
            <td>${t.id}</td>
            <td>${esc(t.type)}</td>
            <td>${esc(t.state)}</td>
            <td>${esc(progress)}</td>
            <td>${t.retry_count || 0}</td>
            <td class="small muted">${esc((t.last_error || "").slice(0, 120))}</td>
            <td>${canCancel ? `<button class="btn danger" data-action="cancel-task" data-task-id="${t.id}">Cancel</button>` : ""}</td>
          </tr>
        `;
      })
      .join("");
  } catch (e) {
    showToast(`Task load failed: ${e.message}`);
  }
}

async function refreshAdminPanels() {
  try {
    const [health, metrics, lvface, caption] = await Promise.all([
      api("/health"),
      api("/metrics"),
      api("/health/lvface"),
      api("/health/caption"),
    ]);
    qs("admin-health").textContent = JSON.stringify(health, null, 2);
    qs("admin-metrics").textContent = JSON.stringify(metrics, null, 2);
    qs("admin-services").textContent = JSON.stringify({ lvface, caption }, null, 2);
  } catch (e) {
    showToast(`Admin refresh failed: ${e.message}`);
  }
}

async function handleCaptionActions(event) {
  const btn = event.target.closest("button[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;
  const captionId = Number(btn.dataset.captionId);
  if (!captionId) return;
  try {
    if (action === "save-caption") {
      const text = qs(`caption-text-${captionId}`).value;
      await api(`/captions/${captionId}`, {
        method: "PATCH",
        body: JSON.stringify({ text, user_edited: true }),
      });
      showToast(`Caption ${captionId} saved`);
    } else if (action === "delete-caption") {
      await api(`/captions/${captionId}`, { method: "DELETE" });
      showToast(`Caption ${captionId} deleted`);
    }
    if (state.selectedAsset) {
      await loadAssetInspector(state.selectedAsset.id);
    }
  } catch (e) {
    showToast(`Caption action failed: ${e.message}`);
  }
}

async function assignFace(faceId, selectorId) {
  const select = qs(selectorId);
  const personId = Number(select?.value || 0);
  if (!personId) {
    showToast("Select a target person first");
    return;
  }
  await api(`/faces/${faceId}/assign`, {
    method: "POST",
    body: JSON.stringify({ person_id: personId }),
  });
}

async function createPersonFromFace(faceId) {
  await api(`/faces/${faceId}/assign`, {
    method: "POST",
    body: JSON.stringify({ create_new: true }),
  });
}

async function deleteFace(faceId) {
  await api(`/faces/${faceId}?prune_empty_person=true`, {
    method: "DELETE",
  });
}

function initEvents() {
  document.querySelectorAll(".tab").forEach((el) => {
    el.addEventListener("click", async () => {
      setActiveTab(el.dataset.tab);
      if (el.dataset.tab === "tasks") await loadTasks();
      if (el.dataset.tab === "admin") await refreshAdminPanels();
      if (el.dataset.tab === "people") await loadPeople();
    });
  });

  qs("btn-refresh-all").addEventListener("click", async () => {
    await Promise.all([refreshDashboard(), loadTasks(), loadPeople(), refreshAdminPanels()]);
    showToast("Refreshed");
  });

  qs("btn-search").addEventListener("click", runSearch);
  qs("btn-library-load").addEventListener("click", loadLibraryLatest);
  qs("search-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch();
  });

  qs("library-grid").addEventListener("click", async (e) => {
    const card = e.target.closest(".asset-card");
    if (!card) return;
    await loadAssetInspector(Number(card.dataset.assetId));
  });

  qs("person-assets-grid").addEventListener("click", async (e) => {
    const card = e.target.closest(".asset-card");
    if (!card) return;
    setActiveTab("library");
    await loadAssetInspector(Number(card.dataset.assetId));
  });

  qs("caption-list").addEventListener("click", handleCaptionActions);

  qs("btn-caption-regenerate").addEventListener("click", async () => {
    if (!state.selectedAsset) return;
    try {
      await api(`/assets/${state.selectedAsset.id}/captions/regenerate`, {
        method: "POST",
        body: JSON.stringify({ force: false }),
      });
      showToast("Caption regeneration task enqueued");
      await loadTasks();
    } catch (e) {
      showToast(`Regenerate failed: ${e.message}`);
    }
  });

  qs("btn-add-tags").addEventListener("click", async () => {
    if (!state.selectedAsset) return;
    const names = String(qs("tag-input").value || "")
      .split(",")
      .map((v) => v.trim())
      .filter((v) => v);
    if (!names.length) {
      showToast("No tag entered");
      return;
    }
    try {
      await api(`/assets/${state.selectedAsset.id}/tags`, {
        method: "POST",
        body: JSON.stringify({ names }),
      });
      qs("tag-input").value = "";
      await loadAssetInspector(state.selectedAsset.id);
      showToast("Tags updated");
    } catch (e) {
      showToast(`Tag update failed: ${e.message}`);
    }
  });

  qs("face-list").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const faceId = Number(btn.dataset.faceId);
    if (!faceId) return;
    try {
      if (btn.dataset.action === "assign-face") {
        await assignFace(faceId, `face-person-${faceId}`);
      } else if (btn.dataset.action === "create-person-face") {
        await createPersonFromFace(faceId);
      } else if (btn.dataset.action === "delete-face") {
        if (!window.confirm(`Delete face #${faceId} as non-face detection?`)) return;
        await deleteFace(faceId);
      }
      await loadPeople();
      if (state.selectedAsset) {
        await loadAssetInspector(state.selectedAsset.id);
      }
      showToast(`Face ${faceId} updated`);
    } catch (err) {
      showToast(`Face assignment failed: ${err.message}`);
    }
  });

  qs("people-list").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const personId = Number(btn.dataset.personId);
    if (!personId) return;
    try {
      if (btn.dataset.action === "rename-person") {
        const name = qs(`person-name-${personId}`).value.trim();
        await api(`/persons/${personId}/name`, {
          method: "POST",
          body: JSON.stringify({ display_name: name }),
        });
        await loadPeople();
        showToast(`Person ${personId} renamed`);
      } else if (btn.dataset.action === "view-person-assets") {
        await loadPersonAssets(personId);
      }
    } catch (err) {
      showToast(`Person action failed: ${err.message}`);
    }
  });

  qs("unassigned-faces").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const faceId = Number(btn.dataset.faceId);
    if (!faceId) return;
    try {
      if (btn.dataset.action === "assign-face-unassigned") {
        await assignFace(faceId, `face-person-unassigned-${faceId}`);
      } else if (btn.dataset.action === "create-person-face") {
        await createPersonFromFace(faceId);
      } else if (btn.dataset.action === "delete-face-unassigned") {
        if (!window.confirm(`Delete face #${faceId} as non-face detection?`)) return;
        await deleteFace(faceId);
      }
      await loadPeople();
      showToast(`Face ${faceId} updated`);
    } catch (err) {
      showToast(`Unassigned face action failed: ${err.message}`);
    }
  });

  qs("btn-refresh-people").addEventListener("click", loadPeople);
  qs("btn-refresh-tasks").addEventListener("click", loadTasks);

  qs("task-rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action='cancel-task']");
    if (!btn) return;
    const taskId = Number(btn.dataset.taskId);
    if (!taskId) return;
    try {
      await api(`/tasks/${taskId}/cancel`, { method: "POST" });
      await loadTasks();
      showToast(`Task ${taskId} cancel requested`);
    } catch (err) {
      showToast(`Cancel failed: ${err.message}`);
    }
  });

  qs("btn-rebuild-index").addEventListener("click", async () => {
    try {
      await api("/vector-index/rebuild", { method: "POST" });
      showToast("Vector index rebuild triggered");
      await refreshAdminPanels();
    } catch (e) {
      showToast(`Rebuild failed: ${e.message}`);
    }
  });

  qs("btn-recluster").addEventListener("click", async () => {
    try {
      await api("/persons/recluster", { method: "POST" });
      showToast("Recluster task queued");
      await loadTasks();
    } catch (e) {
      showToast(`Recluster failed: ${e.message}`);
    }
  });

  qs("btn-ingest").addEventListener("click", async () => {
    const root = String(qs("ingest-root").value || "").trim();
    if (!root) {
      showToast("Provide ingest root path");
      return;
    }
    try {
      await api("/ingest/scan", {
        method: "POST",
        body: JSON.stringify({ roots: [root] }),
      });
      showToast(`Ingest scan started for ${root}`);
      await loadTasks();
    } catch (e) {
      showToast(`Ingest failed: ${e.message}`);
    }
  });
}

async function bootstrap() {
  initEvents();
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab");
  if (tab && ["library", "people", "tasks", "admin"].includes(tab)) {
    setActiveTab(tab);
  }
  const q = params.get("q");
  if (q) {
    qs("search-query").value = q;
  }
  await Promise.all([refreshDashboard(), loadLibraryLatest(), loadPeople(), loadTasks(), refreshAdminPanels()]);
  if (q) {
    await runSearch();
  }

  window.setInterval(async () => {
    await refreshDashboard();
    if (state.activeTab === "tasks") await loadTasks();
  }, 10000);
}

window.addEventListener("DOMContentLoaded", bootstrap);
