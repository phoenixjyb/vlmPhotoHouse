from pathlib import Path


UI_ROOT = Path(__file__).resolve().parents[1] / "app" / "ui"


def test_family_home_is_the_default_ui_surface():
    html = (UI_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'class="tab active" data-tab="home"' in html
    assert 'id="tab-home" class="tab-panel active"' in html
    assert 'id="home-search-query"' in html
    assert 'id="home-recent-grid"' in html
    assert 'id="home-people-list"' in html
    assert 'id="home-story-list"' in html


def test_family_home_uses_existing_read_only_discovery_apis():
    javascript = (UI_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'activeTab: "home"' in javascript
    assert 'api("/assets?page=1&page_size=8")' in javascript
    assert 'api("/persons?page=1&page_size=6&include_faces=true&named_only=true' in javascript
    assert 'api("/albums/stories?media=all&story_type=all' in javascript
    assert 'async function runHomeSearch' in javascript
    assert 'qs("search-mode").value = mode;' in javascript
    assert 'await runSearch(1, false, true);' in javascript


def test_family_home_copy_is_bilingual_and_responsive():
    javascript = (UI_ROOT / "app.js").read_text(encoding="utf-8")
    css = (UI_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'home_title: "Find the moments that matter"' in javascript
    assert 'home_title: "找到真正重要的时刻"' in javascript
    assert 'search_mode_family: "Smart family search"' in javascript
    assert 'search_mode_family: "家庭智能搜索"' in javascript
    assert ".home-search-row" in css
    assert "@media (max-width: 680px)" in css


def test_family_mode_hides_operational_surfaces_until_requested():
    html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (UI_ROOT / "app.js").read_text(encoding="utf-8")
    css = (UI_ROOT / "styles.css").read_text(encoding="utf-8")

    assert '<body data-ui-mode="family">' in html
    assert 'id="btn-ui-mode"' in html
    assert 'class="status-cards advanced-only"' in html
    assert 'data-tab="tasks" data-i18n="tab_tasks"' in html
    assert 'data-tab="admin" data-i18n="tab_admin"' in html
    assert 'body[data-ui-mode="family"] .advanced-only' in css
    assert 'uiMode: "family"' in javascript
    assert 'window.localStorage.setItem("vlm_ui_mode", state.uiMode)' in javascript
    assert 'advanced_mode: "Advanced"' in javascript
    assert 'advanced_mode: "高级模式"' in javascript


def test_tabs_and_photo_cards_have_keyboard_semantics():
    html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (UI_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'class="tabs" role="tablist"' in html
    assert 'data-tab="home" data-i18n="tab_home" role="tab"' in html
    assert 'role="tabpanel" aria-labelledby="tab-button-home"' in html
    assert 'el.setAttribute("aria-selected", String(active));' in javascript
    assert '["ArrowLeft", "ArrowRight", "Home", "End"]' in javascript
    assert 'role="button" tabindex="0" aria-label=' in javascript
    assert '["Enter", " "]' in javascript


def test_bootstrap_only_loads_the_active_surface():
    javascript = (UI_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'async function loadTab(tab)' in javascript
    assert 'const initialLoads = [loadTab(state.activeTab)];' in javascript
    assert 'if (state.uiMode === "advanced") initialLoads.push(refreshDashboard());' in javascript
    assert 'refreshDashboard(), loadHome(), loadLibraryLatest(), loadPeople(), loadTasks()' not in javascript


def test_album_composer_is_bilingual_and_uses_persistent_draft_api():
    html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (UI_ROOT / "app.js").read_text(encoding="utf-8")
    stories_html = html.split('id="tab-stories"', 1)[1].split('id="tab-similarity"', 1)[0]

    assert 'id="album-draft-list"' in html
    assert 'id="album-title"' in html
    assert 'id="album-title-zh"' in html
    assert 'id="album-theme"' in html
    assert 'id="album-cover-asset"' in html
    assert 'id="btn-save-album-draft"' in html
    assert 'api("/albums/drafts?page=1&page_size=50")' in javascript
    assert 'method: "POST"' in javascript
    assert 'method: "PATCH"' in javascript
    assert 'album_drafts_title: "Saved album drafts"' in javascript
    assert 'album_drafts_title: "已保存的相册草稿"' in javascript
    assert stories_html.index('id="album-draft-list"') < stories_html.index('id="album-composer-title"')
