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
  await page.locator('#uploads-open').click();
  await page.locator('.upload-card').first().waitFor();assert.equal(await page.locator('.upload-card').count(),3);
  await page.waitForFunction(()=>[...document.querySelectorAll('.upload-card img')].filter(img=>img.naturalWidth>0).length===3);
  await page.locator('#uploads-panel').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'upload-inbox-desktop.png'),fullPage:true});
  await page.locator('.upload-card button.primary').first().click();await page.locator('#upload-review-dialog').waitFor({state:'visible'});
  assert.match(await page.locator('#upload-review-copy').textContent(),/family-a/);
  await page.screenshot({path:path.join(artifacts,'upload-confirm-desktop.png')});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(artifacts,'upload-confirm-phone.png')});
  assert.equal(await page.evaluate(()=>{const r=document.querySelector('#upload-review-dialog').getBoundingClientRect();return r.left>=0&&r.right<=window.innerWidth;}),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  loseApproval=true;await page.locator('#upload-review-approve').click();
  await page.waitForFunction(()=>!document.querySelector('#upload-review-approve').disabled);
  assert.equal(await page.locator('#upload-review-dialog').isVisible(),true);
  await page.locator('#upload-review-approve').click();
  await page.locator('#upload-review-dialog').waitFor({state:'hidden'});
  await page.waitForFunction(()=>document.querySelectorAll('.upload-card').length===2);
  assert.equal(posts,2);
  await page.locator('#refresh').click();
  await page.locator(`.asset`).filter({hasText:String(seed.asset_id)}).waitFor();
  await page.locator('#language').click();
  await page.waitForFunction(()=>document.querySelector('#uploads-open').textContent==='上传审核'&&document.querySelectorAll('.upload-card').length===2);
  // Revocation while a second confirmation is open must clear all private UI.
  await page.locator('.upload-card button.primary').first().click();
  await page.locator('#upload-review-dialog').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.querySelector('#upload-review-preview img')?.naturalWidth>0);
  await page.screenshot({path:path.join(artifacts,'upload-confirm-phone-zh.png')});
  await rpc({command:'revoke'});
  await page.locator('#upload-review-approve').click();
  await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('#upload-review-dialog').isVisible(),false);
  assert.equal(await page.locator('.upload-card').count(),0);
  assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  console.log(JSON.stringify({passed:['private inbox preview','target confirmation','desktop and phone layout','lost approval response then idempotent retry','approved photo appears in gallery','revoked session clears private inbox and dialog'],artifacts}));
  await context.close();
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();});
