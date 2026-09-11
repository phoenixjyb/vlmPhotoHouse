#!/usr/bin/env node
// Browser-level UI regression checks. Uses synthetic fixtures only, no live API.
// npm install --no-save playwright; npx playwright install chromium
// node scripts/test-family-ui-browser.cjs
// PLAYWRIGHT_MODULE_PATH may point to an existing Playwright installation.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

const ui = path.resolve(__dirname, '../backend/app/ui');
const assets = [1, 2, 3].map(id => ({
  id, path: `fixture-${id}.${id === 3 ? 'mp4' : 'jpg'}`,
  mime: id === 3 ? 'video/mp4' : 'image/jpeg', taken_at: '2026-05-04T12:00:00',
}));
const cover = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect width="800" height="600" fill="#c49c7c"/><circle cx="400" cy="260" r="140" fill="#eee1c9"/></svg>';
const photo = (width, height) => `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#c49c7c"/><rect x="2" y="2" width="${width - 4}" height="${height - 4}" fill="none" stroke="white" stroke-width="4"/></svg>`;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const server = http.createServer(async (req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const name = { '/ui': 'index.html', '/ui/': 'index.html', '/ui/app.js': 'app.js', '/ui/styles.css': 'styles.css' }[pathname];
    if (!name) { res.writeHead(404); res.end(); return; }
    res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }[path.extname(name)]);
    res.end(await fs.readFile(path.join(ui, name)));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const artifacts = process.env.PHOTOHOUSE_UI_ARTIFACTS;
    if (artifacts) await fs.mkdir(artifacts, { recursive: true });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let failStories = true, empty = false, brokenImages = false, delayedCaption = false, lastQuery = null, searchCalls = 0;
    let longCaptions = false, failOriginal = false, delayOriginal = false, originals = 0;
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.hostname !== '127.0.0.1') return route.abort();
      if (url.pathname.startsWith('/ui')) return route.continue();
      if (url.pathname.includes('/thumbnail')) {
        if (brokenImages) return route.fulfill({ status: 404 });
        const id = Number(url.pathname.split('/')[2]);
        return route.fulfill({ contentType: 'image/svg+xml', body: id === 1 ? photo(768, 1024) : id === 2 ? photo(1024, 512) : cover });
      }
      if (url.pathname.endsWith('/media')) {
        const id = Number(url.pathname.split('/')[2]);
        if (id !== 3) {
          originals++;
          if (delayOriginal) await sleep(600);
          return failOriginal ? route.fulfill({ status: 404 }) : route.fulfill({ contentType: 'image/svg+xml', body: id === 1 ? photo(2400, 3200) : photo(4000, 2000) });
        }
        await sleep(300);
        return route.fulfill({ status: 404 });
      }
      let data = {};
      if (url.pathname === '/assets') data = { assets: empty ? [] : assets, total: empty ? 0 : assets.length };
      if (url.pathname === '/persons') data = { persons: [] };
      if (url.pathname === '/albums/stories') {
        await sleep(150);
        if (failStories) return route.fulfill({ status: 503, json: { detail: 'Fixture unavailable' } });
        data = { stories: [{ id: 'trip', type: 'tag', title: 'A day outside', count: 3, items: assets }] };
      }
      if (/\/assets\/\d+\/captions$/.test(url.pathname)) {
        const id = Number(url.pathname.split('/')[2]);
        if (id === 1 && delayedCaption) await sleep(600);
        data = { captions: [{ text: `EN: Memory ${id}\nZH-CN: 回忆 ${id}` + (longCaptions ? '\nA family memory. 家庭回忆。'.repeat(120) : '') }] };
      }
      if (url.pathname === '/search/smart') {
        searchCalls++;
        lastQuery = request.postDataJSON();
        data = { results: [{ asset_id: 2, path: 'fixture-2.jpg', mime: 'image/jpeg' }] };
      }
      await route.fulfill({ json: data });
    });
    const base = `http://127.0.0.1:${server.address().port}/ui`;
    await page.goto(base);
    await page.locator('#btn-home-retry').waitFor();
    assert.equal(await page.locator('#home-recent-grid .asset-card').count(), 3, 'Photos survive album API failure');
    failStories = false;
    await page.locator('#btn-home-retry').click();
    await page.locator('#home-story-list .home-story-row').waitFor();
    await page.locator('#home-load-status').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('[data-tab="admin"]').isVisible(), false);

    delayedCaption = true;
    const card = page.locator('#home-recent-grid .asset-card').first();
    await card.focus();
    await page.keyboard.press('Enter');
    await page.locator('#preview-modal').waitFor({ state: 'visible' });
    assert.equal(await page.locator('.app-shell').evaluate(el => el.inert), true);
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => document.querySelector('#preview-caption').textContent.includes('Memory 2'));
    await sleep(750);
    assert.match(await page.locator('#preview-caption').innerText(), /Memory 2\nZH-CN: 回忆 2/, 'Late captions cannot replace current photo');
    await page.locator('#preview-caption').focus();
    await page.keyboard.press('ArrowRight');
    assert.match(await page.locator('#preview-position').innerText(), /2.*3/, 'Caption keyboard scrolling does not change photos');
    const firstControl = page.locator('#btn-preview-play');
    await firstControl.focus();
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.locator('#preview-filmstrip button').last().evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Tab');
    assert.equal(await firstControl.evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Escape');
    assert.equal(await card.evaluate(el => el === document.activeElement), true, 'Closing restores photo focus');
    assert.equal(await page.locator('.app-shell').evaluate(el => el.inert), false);

    // Measure the image itself, not just the modal. The old hidden overflow
    // made a 1477px portrait look contained inside a 479px stage to modal-only tests.
    longCaptions = true;
    for (const [width, height] of [[1440, 900], [1280, 720], [768, 844], [390, 844], [320, 568], [844, 390]]) {
      await page.setViewportSize({ width, height });
      for (const id of [1, 2]) {
        await page.locator(`#home-recent-grid [data-asset-id="${id}"]`).click();
        await page.waitForFunction(() => document.querySelector('#preview-modal-body img')?.naturalWidth > 0);
        await page.waitForFunction(() => document.querySelector('#preview-caption').textContent.length > 500);
        await page.waitForFunction(() => {
          const body = document.querySelector('#preview-modal-body'), img = body.querySelector('img');
          const b = body.getBoundingClientRect(), r = img.getBoundingClientRect();
          return r.width > 0 && r.height > 0 && r.left >= b.left - 1 && r.top >= b.top - 1 && r.right <= b.right + 1 && r.bottom <= b.bottom + 1;
        });
        assert.equal(await page.locator('#btn-viewer-fit').getAttribute('aria-pressed'), 'true');
        assert.ok(await page.locator('#preview-modal-body').evaluate(el => el.clientHeight > 80 && el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1), `Whole ${id === 1 ? 'portrait' : 'landscape'} fits at ${width}x${height}`);
        if (artifacts && id === 1 && [1280, 390].includes(width)) await page.screenshot({ path: path.join(artifacts, `viewer-fit-${width}.png`) });
        await page.keyboard.press('Escape');
      }
    }
    assert.equal(originals, 0, 'Fit loads only lightweight previews');
    await page.setViewportSize({ width: 1280, height: 720 });
    await card.click();
    await page.locator('#btn-viewer-actual').click();
    await page.waitForFunction(() => document.querySelector('#preview-modal-body img')?.naturalWidth === 2400);
    assert.equal(await page.locator('#viewer-zoom').innerText(), '100%');
    const viewport = page.locator('#preview-modal-body');
    assert.equal(await viewport.locator('img').evaluate(el => el.getBoundingClientRect().width), 2400, 'Actual size uses original pixels, not thumbnail pixels');
    assert.ok(await viewport.evaluate(el => el.scrollWidth > el.clientWidth && el.scrollHeight > el.clientHeight), 'Actual-size overflow is scrollable on both axes');
    if (artifacts) await page.screenshot({ path: path.join(artifacts, 'viewer-actual.png') });
    await viewport.evaluate(el => { el.scrollLeft = 0; el.scrollTop = 0; });
    const box = await viewport.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 100, box.y + box.height / 2 - 70, { steps: 4 });
    await page.mouse.up();
    assert.ok(await viewport.evaluate(el => el.scrollLeft >= 99 && el.scrollTop >= 69), 'Mouse drag pans without changing photos');
    assert.equal(await viewport.evaluate(el => el.classList.contains('is-dragging')), false);
    await page.mouse.wheel(0, -100);
    await page.waitForFunction(() => document.querySelector('#preview-modal-body img').getBoundingClientRect().width > 2400);
    await page.locator('#btn-viewer-zoom-out').click();
    await page.locator('#btn-viewer-fit').click();
    assert.equal(await viewport.evaluate(el => el.scrollTop + el.scrollLeft), 0, 'Fit resets pan');
    await viewport.dblclick();
    assert.equal(await page.locator('#btn-viewer-actual').getAttribute('aria-pressed'), 'true');
    await page.keyboard.press('0');
    assert.equal(await page.locator('#btn-viewer-fit').getAttribute('aria-pressed'), 'true');
    await page.keyboard.press('1');
    assert.equal(await page.locator('#viewer-zoom').innerText(), '100%');
    await page.locator('#btn-preview-next').click();
    await page.waitForFunction(() => document.querySelector('#preview-modal-body img')?.naturalWidth === 1024);
    assert.equal(await page.locator('#btn-viewer-fit').getAttribute('aria-pressed'), 'true', 'Changing photo resets zoom');
    if (await page.evaluate(() => document.fullscreenEnabled)) {
      await page.locator('#btn-viewer-fullscreen').click();
      await page.waitForFunction(() => document.fullscreenElement?.id === 'preview-modal');
      assert.equal(await page.locator('#btn-viewer-fullscreen').innerText(), 'Exit full screen');
      await page.locator('#btn-viewer-fullscreen').click();
      await page.waitForFunction(() => !document.fullscreenElement);
    }
    await page.keyboard.press('Escape');
    failOriginal = true;
    await page.reload(); // Drop decoded originals from the previous viewer.
    await card.click();
    await page.locator('#btn-viewer-actual').click();
    await page.waitForFunction(() => document.querySelector('#viewer-image-status').textContent.includes('Original unavailable'));
    assert.equal(await page.locator('#btn-viewer-actual').isDisabled(), true);
    assert.equal(await viewport.locator('img').evaluate(el => el.naturalWidth), 768, 'Unsupported original leaves the preview intact');
    assert.equal(await page.locator('#btn-viewer-fit').getAttribute('aria-pressed'), 'true');
    await page.keyboard.press('Escape');
    failOriginal = false;
    delayOriginal = true;
    await page.reload();
    await card.click();
    await page.locator('#btn-viewer-actual').click();
    await page.locator('#btn-preview-next').click();
    await sleep(750);
    assert.equal(await viewport.locator('img').evaluate(el => el.naturalWidth), 1024, 'Late original cannot replace the next photo');
    await page.keyboard.press('Escape');
    delayOriginal = false;
    longCaptions = false;
    await page.setViewportSize({ width: 1440, height: 1000 });

    delayedCaption = false;
    await page.clock.install();
    await page.locator('#btn-home-slideshow').click();
    assert.equal(await firstControl.getAttribute('aria-pressed'), 'true');
    await page.clock.fastForward(6100);
    assert.match(await page.locator('#preview-position').innerText(), /2.*3/);
    await page.keyboard.press('Escape');
    await page.clock.fastForward(6500);
    assert.equal(await page.locator('#preview-modal').isVisible(), false, 'Closed slideshow stays closed');
    await card.click();
    assert.equal(await firstControl.getAttribute('aria-pressed'), 'false');
    await page.locator('#preview-filmstrip button').last().click();
    const video = page.locator('#preview-modal-body video');
    assert.equal(await video.evaluate(el => el.autoplay), false, 'Video never autoplays');
    assert.equal(await video.evaluate(el => el.controls && el.playsInline), true);
    assert.equal(await page.locator('#btn-viewer-actual').isDisabled(), true, 'Image zoom controls do not hijack videos');
    await page.keyboard.press('Escape');

    await card.click();
    await page.locator('#btn-preview-details').click();
    await page.locator('#asset-inspector').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#tab-library .left-panel').isVisible(), false);
    await page.locator('#btn-asset-back').click();
    assert.equal(await page.locator('#tab-home').getAttribute('aria-hidden'), 'false', 'Details returns to its original view');

    await page.locator('.lang-btn[data-lang="zh"]').click();
    await card.click();
    assert.equal(await page.locator('#btn-viewer-fit').innerText(), '适应窗口');
    assert.equal(await page.locator('#btn-viewer-actual').innerText(), '实际大小');
    assert.equal(await page.locator('#btn-viewer-fullscreen').innerText(), '全屏');
    await page.keyboard.press('Escape');
    await page.locator('[data-home-query]').first().click();
    await page.locator('#library-grid .asset-card').waitFor();
    assert.match(lastQuery.text, /[\u4e00-\u9fff]/, 'Chinese suggestion sends Chinese query');
    const query = await page.locator('#search-query').inputValue();
    await page.locator('[data-tab="home"]').click();
    await page.locator('[data-tab="library"]').click();
    assert.equal(await page.locator('#search-query').inputValue(), query);
    assert.equal(await page.locator('#library-grid .asset-card').count(), 1);
    assert.equal(searchCalls, 1, 'Tab navigation keeps results without refetching');
    await page.keyboard.press('/');
    assert.equal(await page.locator('#home-search-query').evaluate(el => el === document.activeElement), true);

    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No horizontal overflow at ${width}px`);
      await card.click();
      const fits = await page.locator('#preview-modal').evaluate(el => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight);
      assert.ok(fits, `Viewer stays inside viewport at ${width}px`);
      await page.keyboard.press('Escape');
    }
    await page.locator('.lang-btn[data-lang="en"]').click();
    await page.locator('#btn-ui-mode').click();
    assert.equal(await page.locator('[data-tab="admin"]').isVisible(), true, 'Advanced functions remain available');
    await page.locator('#btn-ui-mode').click();
    brokenImages = true;
    await page.goto(base);
    await page.locator('#home-recent-grid .fallback').first().waitFor({ state: 'visible' });
    await page.locator('#home-featured-photos .home-cover-placeholder').first().waitFor({ state: 'visible' });
    brokenImages = false;
    empty = true;
    await page.goto(base);
    await page.waitForFunction(() => document.querySelector('#tab-home').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#btn-home-slideshow').isDisabled(), true);
    assert.equal(await page.locator('#home-recent-grid .asset-card').count(), 0);
    assert.ok((await page.locator('#home-recent-grid').innerText()).length > 0);
    assert.deepEqual(errors, [], 'No uncaught browser errors');
    console.log('PASS: whole-image fit at six viewport sizes; portrait/landscape and long bilingual captions; lazy original/actual size; mouse pan/wheel zoom; keyboard/double-click reset; fullscreen; failed/stale originals; partial loading/retry; caption races; focus/keyboard; slideshow; video; bilingual search; retained navigation; advanced mode; empty state.');
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
