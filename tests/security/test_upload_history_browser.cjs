/* Chromium -> real protected ASGI -> synthetic migrated DB, with no listener. */
'use strict';
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'upload-history-browser-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'upload_history_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let next=0,readyResolve;const ready=new Promise(r=>readyResolve=r),pending=new Map();
bridge.stderr.on('data',v=>process.stderr.write(v));
createInterface({input:bridge.stdout}).on('line',line=>{const m=JSON.parse(line);if(m.ready)readyResolve(m);else{pending.get(m.id)?.(m);pending.delete(m.id);}});
function rpc(m){return new Promise(resolve=>{const id=++next;pending.set(id,resolve);bridge.stdin.write(JSON.stringify({...m,id})+'\n');});}
let historyUnavailable=false,holdHistory=false,releaseHistory,historyHeld;const errors=[],outside=[],requests=[];
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
    if(url.pathname==='/uploads'&&request.method()==='GET'){
      if(historyUnavailable)return route.fulfill({status:503,contentType:'application/json',body:'{}'});
      if(holdHistory){holdHistory=false;await new Promise(resolve=>{releaseHistory=resolve;historyHeld?.();});}
    }
    const outputHeaders={...result.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    await route.fulfill({status:result.status,headers:outputHeaders,body:Buffer.from(result.body,'base64')});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#my-uploads-open').waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('#grid .asset').length>0&&document.querySelector('#status').textContent==='');
  assert.equal(await page.locator('#uploads-open').isVisible(),false);
  await page.locator('#my-uploads-open').click();
  await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10).catch(async error=>{console.error(requests,errors,await page.locator('#my-uploads-status').textContent(),await page.locator('#my-uploads-panel').evaluate(e=>e.open));throw error;});
  assert.match(await page.locator('.receipt-card').first().textContent(),/awaiting owner review/);
  assert.equal(await page.locator('.receipt-card button').count(),0);
  await page.locator('#my-uploads-next').click();
  await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===2);
  await page.locator('#my-uploads-previous').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  await rpc({command:'approve'});await page.locator('#my-uploads-refresh').click();
  await page.locator('.receipt-card button').waitFor();
  await page.locator('#my-uploads-panel').screenshot({path:path.join(artifacts,'my-uploads-desktop.png')});
  await page.locator('.receipt-card button').click();
  await page.waitForFunction(()=>document.querySelector('#viewer-media .viewer-surface img')?.naturalWidth>0).catch(async error=>{console.error(requests.slice(-20),errors,await page.locator('#status').textContent(),await page.locator('#viewer').evaluate(e=>e.open),await page.locator('#view-quality').textContent());throw error;});
  assert.match(await page.locator('#viewer-title').textContent(),new RegExp(String(seed.asset_id)));
  await page.locator('#close-viewer').click();
  await page.setViewportSize({width:390,height:844});await page.locator('#language').click();
  await page.waitForFunction(()=>document.querySelector('#my-uploads-open').textContent==='我的上传');
  await page.locator('#my-uploads-open').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  assert.match(await page.locator('.receipt-card').first().textContent(),/已加入相册库/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  await page.locator('#my-uploads-panel').screenshot({path:path.join(artifacts,'my-uploads-phone-zh.png')});
  await page.locator('#my-uploads-panel summary').click();
  await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===0);
  await page.locator('#my-uploads-open').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  historyUnavailable=true;await page.locator('#my-uploads-refresh').click();
  await page.waitForFunction(()=>document.querySelector('#my-uploads-status').textContent.includes('暂时无法'));
  assert.equal(await page.locator('.receipt-card').count(),0);
  assert.equal(await page.locator('#library').isVisible(),true);
  historyUnavailable=false;await page.locator('#my-uploads-refresh').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  holdHistory=true;const held=new Promise(resolve=>historyHeld=resolve);
  await page.locator('#my-uploads-refresh').click();await held;
  await page.locator('#my-uploads-panel summary').click();releaseHistory();
  await page.waitForFunction(()=>!document.querySelector('#my-uploads-panel').open&&document.querySelectorAll('.receipt-card').length===0);
  await page.locator('#my-uploads-open').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  await rpc({command:'revoke'});await page.locator('#my-uploads-refresh').click();
  await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('.receipt-card').count(),0);
  assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  console.log(JSON.stringify({passed:['member history distinct from owner review','10 plus 2 pagination','pending has no open','real promotion reflected after refresh','approved opens authorized viewer','Chinese narrow layout','closing clears receipts','503 clears rows while gallery remains usable','late closed-panel response discarded','revocation clears private history'],artifacts}));
  await context.close();
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();});
