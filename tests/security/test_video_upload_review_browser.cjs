/* Chromium -> real protected ASGI -> synthetic migrated DB, with no listener. */
'use strict';
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'upload-review-browser-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'upload_review_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let next=0,readyResolve;const ready=new Promise(r=>readyResolve=r),pending=new Map();
bridge.stderr.on('data',v=>process.stderr.write(v));
createInterface({input:bridge.stdout}).on('line',line=>{const m=JSON.parse(line);if(m.ready)readyResolve(m);else{pending.get(m.id)?.(m);pending.delete(m.id);}});
function rpc(m){return new Promise(resolve=>{const id=++next;pending.set(id,resolve);bridge.stdin.write(JSON.stringify({...m,id})+'\n');});}
let loseApproval=false,posts=0;const errors=[],outside=[],requests=[];
let browser;
(async()=>{
  const seed=await ready;
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  const context=await browser.newContext({viewport:{width:1200,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){outside.push(url.origin);return route.abort();}
    const headers=await request.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const result=await rpc({method:request.method(),path:url.pathname+url.search,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    requests.push([request.method(),url.pathname,result.status]);
    if(url.pathname.endsWith('/approve')){posts++;if(loseApproval){loseApproval=false;return route.abort();}}
    const outputHeaders={...result.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    await route.fulfill({status:result.status,headers:outputHeaders,body:Buffer.from(result.body,'base64')});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#uploads-panel').waitFor({state:'visible'}).catch(async e=>{console.error(requests,await page.locator('#status').textContent());throw e;});
  loseApproval=false;
  const video=await rpc({command:'seed_video'});
  await page.locator('#uploads-open').click();
  const card=page.locator(`.upload-card[data-upload-id="${video.asset_id}"]`);
  await card.waitFor();
  assert.match(await card.textContent(),/Video/);
  assert.equal(await card.locator('img').count(),0);
  assert.doesNotMatch(await card.textContent(),/null|undefined/);
  await card.locator('button.primary').click();
  await page.locator('#upload-review-dialog').waitFor({state:'visible'});
  assert.match(await page.locator('#upload-review-preview').textContent(),/Video/);
  await page.screenshot({path:path.join(artifacts,'video-review-desktop.png')});
  await page.locator('#upload-review-approve').click();
  await page.locator('#upload-review-dialog').waitFor({state:'hidden'});
  assert.equal(posts,1);
  assert.equal(await page.locator('video').count(),0);
  assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  console.log(JSON.stringify({passed:['real resumable MP4 intake','private video review placeholder','no image decoder or autoplay','explicit owner approval'],artifacts}));
  await context.close();
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();});
