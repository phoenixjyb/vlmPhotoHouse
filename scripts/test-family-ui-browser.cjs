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
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let failStories = true, empty = false, brokenImages = false, delayedCaption = false, lastQuery = null, searchCalls = 0;
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.hostname !== '127.0.0.1') return route.abort();
      if (url.pathname.startsWith('/ui')) return route.continue();
      if (url.pathname.includes('/thumbnail')) {
        if (brokenImages) return route.fulfill({ status: 404 });
        return route.fulfill({ contentType: 'image/svg+xml', body: cover });
      }
      if (url.pathname.endsWith('/media')) {
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
        data = { captions: [{ text: `EN: Memory ${id}\nZH-CN: 回忆 ${id}` }] };
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
    await page.keyboard.press('Escape');

    await card.click();
    await page.locator('#btn-preview-details').click();
    await page.locator('#asset-inspector').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#tab-library .left-panel').isVisible(), false);
    await page.locator('#btn-asset-back').click();
    assert.equal(await page.locator('#tab-home').getAttribute('aria-hidden'), 'false', 'Details returns to its original view');

    await page.locator('.lang-btn[data-lang="zh"]').click();
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
    console.log('PASS: partial loading/retry; viewer and caption races; focus/keyboard; slideshow; video; bilingual search; retained navigation; four responsive widths; advanced mode; empty state.');
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
