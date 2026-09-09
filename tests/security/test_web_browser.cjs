/* Actual Chromium UI -> pipe bridge -> real ASGI -> migrated synthetic SQLite.
 * No HTTP server/listener. Browser requests are intercepted; unknown hosts abort.
 * Supply PLAYWRIGHT_MODULE to an existing installation; no downloads/install step.
 */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS || fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-web-proof-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0;const pending=new Map();let readyResolve,readyReject;
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{
  const message=JSON.parse(line);if(message.ready){readyResolve();return;}
  const request=pending.get(message.id);if(request){pending.delete(message.id);request.resolve(message);}
});
bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed '+code));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
function rpc(message){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});}
const mutate=scenario=>rpc({command:'mutate',scenario});
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const PASSWORD='Synthetic family passphrase!';
const MEMBER='+12025550102';
let hold=null,abortLogout=false;
const external=[],errors=[],checks=[];
function checkpoint(name){checks.push(name);console.log('PASS '+name);}
function delayNext(predicate){
  let release,arrived;
  const gate=new Promise(resolve=>{release=resolve;});
  const seen=new Promise(resolve=>{arrived=resolve;});
  hold={predicate,gate,arrived};return {release,seen};
}
async function context(browser){
  const ctx=await browser.newContext({viewport:{width:1200,height:900},serviceWorkers:'block'});
  await ctx.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    if(abortLogout&&url.pathname==='/auth/logout'){abortLogout=false;await route.abort();return;}
    const headers=await request.allHeaders();
    delete headers['content-length']; // TestClient recalculates bytes forwarded on the pipe.
    const response=await rpc({method:request.method(),path:url.pathname+url.search,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(hold&&hold.predicate(url,request)) {const delayed=hold;hold=null;delayed.arrived();await delayed.gate;}
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try {await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|canceled|cancelled|Invalid InterceptionId/.test(error.message))throw error;}
  });
  ctx.on('page',page=>page.on('pageerror',error=>errors.push(error.message)));
  return ctx;
}
async function auth(page,phone=MEMBER,code){
  await page.goto('https://photohouse.test/ui');
  await page.locator('#auth').waitFor({state:'visible'});
  if(code)await page.locator('#register-tab').click();
  await page.locator('#phone').fill(phone);await page.locator('#password').fill(PASSWORD);
  if(code)await page.locator('#code').fill(code);
  await page.locator('#auth-submit').click();
  await page.waitForFunction(()=>!document.getElementById('library').hidden||document.getElementById('status').textContent.includes('could not be confirmed')||document.getElementById('status').textContent.includes('unavailable'));
  assert.equal(await page.locator('#library').isVisible(),true,await page.locator('#status').textContent());
  await page.locator('.asset').first().waitFor();
}
async function ids(page){return page.locator('.asset span').allTextContents();}
let browser;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  const memberContext=await context(browser),page=await memberContext.newPage();
  const shell=await page.goto('https://photohouse.test/ui');
  await page.locator('#auth').waitFor({state:'visible'});
  assert.match(shell.headers()['content-security-policy'],/frame-ancestors 'none'/);
  assert.equal(await page.locator('.asset').count(),0);
  await page.screenshot({path:path.join(artifacts,'sign-in-desktop.png'),fullPage:true});
  checkpoint('Public sign-in shell has CSP and no anonymous photos');
  await auth(page);
  assert.equal(await page.locator('.asset').count(),2);
  assert.equal(await page.locator('#owner-panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.cookie),'');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  const cookies=await memberContext.cookies();assert.equal(cookies.length,1);assert(cookies[0].httpOnly&&cookies[0].secure&&cookies[0].sameSite==='Strict');
  await page.locator('.asset img').first().evaluate(img=>img.decode());
  await page.screenshot({path:path.join(artifacts,'gallery-desktop.png'),fullPage:true});
  checkpoint('Phone/password login uses HttpOnly cookie and scoped gallery');
  await mutate('caption-html');
  await page.locator('.asset').filter({hasText:'101'}).click();
  await page.locator('#captions p').waitFor();
  assert.match(await page.locator('#captions').textContent(),/<img src=x/);
  assert.equal(await page.locator('#captions img').count(),0);assert.equal(await page.evaluate(()=>window.syntheticXSS),undefined);
  assert.equal(await page.locator('#original').isVisible(),false);
  await page.locator('#close-viewer').click();
  checkpoint('Captions render as text and viewer cannot download originals');
  const oldViewer=delayNext(url=>url.pathname==='/assets/101/captions');
  await page.locator('.asset').filter({hasText:'101'}).click();await oldViewer.seen;
  await page.locator('#close-viewer').click();await page.locator('.asset').filter({hasText:'102'}).click();
  await page.locator('#captions p').waitFor();oldViewer.release();await pause(150);
  assert.equal(await page.locator('#captions p').textContent(),'caption-102');
  await page.locator('#close-viewer').click();
  checkpoint('Delayed closed viewer cannot overwrite a newer asset');
  await page.setViewportSize({width:390,height:844});await page.locator('#language').click();
  await page.locator('.asset').first().waitFor();assert.equal(await page.locator('#logout').textContent(),'退出登录');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(artifacts,'gallery-mobile-zh.png'),fullPage:true});
  await page.locator('#language').click();await page.setViewportSize({width:1200,height:900});
  checkpoint('English/Chinese gallery fits a narrow mobile viewport');
  const ownerContext=await context(browser),owner=await ownerContext.newPage();
  await auth(owner,'+12025550100');
  await owner.locator('#owner-panel summary').click();
  await owner.locator('#invite-phone').fill('+12025550103');await owner.locator('#invite-form button').click();
  await owner.locator('#created-code').waitFor({state:'visible'});
  const code=await owner.locator('#created-code').inputValue();assert.match(code,/^[a-f0-9]{8}(-[a-f0-9]{8}){3}$/);
  const joinedContext=await context(browser),joined=await joinedContext.newPage();await auth(joined,'+12025550103',code);
  assert.equal(await joined.locator('#owner-panel').isVisible(),false);assert.equal(await joined.locator('.asset').count(),2);
  checkpoint('Owner manually creates phone-bound invitation; registration joins as viewer');
  await owner.locator('#invite-phone').fill('+12025550104');await owner.locator('#invite-form button').click();
  await owner.waitForFunction(previous=>document.getElementById('created-code').value!==previous,code);
  const cancelled=await owner.locator('#created-code').inputValue();await owner.locator('#cancel-invite').click();
  await owner.locator('#invitation-result').waitFor({state:'hidden'});
  await joined.locator('#logout').click();await joined.locator('#auth').waitFor({state:'visible'});
  await joined.locator('#register-tab').click();await joined.locator('#phone').fill('+12025550104');await joined.locator('#password').fill(PASSWORD);await joined.locator('#code').fill(cancelled);await joined.locator('#auth-submit').click();
  await joined.waitForFunction(()=>document.getElementById('status').textContent.includes('could not be confirmed'));
  assert.equal(await joined.locator('.asset').count(),0);
  checkpoint('Cancelled invitation cannot register or disclose photos');
  await mutate('member-second-library');await page.locator('#refresh').click();
  await page.waitForFunction(()=>document.getElementById('library-select').options.length===2);
  const oldPage=delayNext(url=>url.pathname==='/assets'&&url.searchParams.get('library')==='family-a');
  await page.locator('#refresh').click();await oldPage.seen;
  await page.locator('#library-select').selectOption('family-b');
  await page.locator('.asset').filter({hasText:'201'}).waitFor();oldPage.release();await pause(150);
  assert((await ids(page)).every(text=>text.includes('201')));
  checkpoint('Delayed gallery response cannot cross a library switch');
  const logoutPage=delayNext(url=>url.pathname==='/assets');
  await page.locator('#refresh').click();await logoutPage.seen;
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  logoutPage.release();await pause(150);assert.equal(await page.locator('.asset').count(),0);
  assert.equal((await memberContext.cookies()).length,0);
  checkpoint('Logout revokes cookie and discards delayed private responses');
  await auth(page);abortLogout=true;await page.locator('#logout').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('could not be completed'));
  assert.equal(await page.locator('.asset').count(),0);
  await page.locator('#refresh').click();assert.equal(await page.locator('.asset').count(),0);
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  checkpoint('Failed logout keeps photos hidden and supports explicit retry');
  await auth(page);await mutate('revoke-member');await page.locator('#refresh').click();
  await page.waitForFunction(()=>document.getElementById('library-select').options.length===0);
  assert.equal(await page.locator('.asset').count(),0);
  checkpoint('Membership revocation removes available libraries and photos');
  await mutate('restore-member');await page.locator('#refresh').click();await page.locator('.asset').first().waitFor();
  await mutate('expire-sessions');await page.locator('#refresh').click();await page.locator('#auth').waitFor({state:'visible'});
  assert.equal((await memberContext.cookies()).length,0);
  await auth(page);
  checkpoint('Expired session cookie clears and returning login succeeds');
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checks,externalRequests:external,pageErrors:errors,browser:browser.version(),evidence:'Chromium rendered; all HTTP fulfilled via stdin/stdout ASGI bridge; synthetic SQLite/JPEG only'},null,2));
  console.log(`Browser checks: ${checks.length} passed. Artifacts: ${artifacts}`);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(hold){hold=null;}
  if(browser)await browser.close();bridge.stdin.end(JSON.stringify({command:'quit'})+'\n');
});
