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
const bridge=spawn(process.env.PH_BROWSER_PYTHON || path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
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
let hold=null,abortLogout=false,loseStorySave=false,loseStoryDelete=false;
let loseFaceSave=false;
let loseAlbumSave=false;
let failNextPath=null;
let failNextMoveRefreshPath=null;
let failNextPlaybackGet=false;
const playbackOverrides=[];
let assignmentPosts=0;
const external=[],errors=[],checks=[],browserRequests=[];let syntheticFetchMetadata=0;
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
    browserRequests.push({method:request.method(),path:url.pathname+url.search});
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    if(abortLogout&&url.pathname==='/auth/logout'){abortLogout=false;await route.abort();return;}
    const headers=await request.allHeaders();
    // DevTools request interception here omits network-generated Fetch Metadata.
    // Model it explicitly from the requesting frame for the ASGI contract. This
    // is a test assumption, not proof of actual browser/proxy header emission.
    if(!headers['sec-fetch-site']) {
      let frameOrigin='';try{frameOrigin=new URL(request.frame().url()).origin;}catch{}
      headers['sec-fetch-site']=frameOrigin===url.origin?'same-origin':'none';
      syntheticFetchMetadata++;
    }
    delete headers['content-length']; // TestClient recalculates bytes forwarded on the pipe.
    let response=await rpc({method:request.method(),path:url.pathname+url.search,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(failNextMoveRefreshPath&&request.method()==='GET'&&url.pathname===failNextMoveRefreshPath){failNextMoveRefreshPath=null;response={...response,status:503,headers:{'content-type':'application/json'},body:Buffer.from(JSON.stringify({detail:'synthetic refresh failure'})).toString('base64')};}
    if(request.method()==='HEAD'&&url.pathname==='/assets/105/playback'&&playbackOverrides.length){const override=playbackOverrides.shift();response.status=override.status;response.headers={...response.headers,...override.headers};response.body='';}
    if(failNextPath&&url.pathname===failNextPath){failNextPath=null;await route.abort();return;}
    if(failNextPlaybackGet&&request.method()==='GET'&&url.pathname==='/assets/105/playback'){failNextPlaybackGet=false;await route.abort();return;}
    if(loseStorySave&&request.method()==='POST'&&url.pathname.endsWith('/stories')){loseStorySave=false;await route.abort();return;}
    if(loseStoryDelete&&request.method()==='DELETE'&&url.pathname.startsWith('/stories/')){loseStoryDelete=false;await route.abort();return;}
    if(request.method()==='POST'&&url.pathname.endsWith('/assignment'))assignmentPosts++;
    if(loseFaceSave&&request.method()==='POST'&&(/\/(assignment|unassign|new-person)$/.test(url.pathname))){loseFaceSave=false;await route.abort();return;}
    if(loseAlbumSave&&request.method()==='POST'&&url.pathname==='/admin/albums'){loseAlbumSave=false;await route.abort();return;}
    if(hold&&hold.predicate(url,request)) {const delayed=hold;hold=null;delayed.arrived();await delayed.gate;}
    const outputHeaders={...response.headers};if(request.method()!=='HEAD')delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try {await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|canceled|cancelled|Invalid InterceptionId/.test(error.message))throw error;}
  });
  ctx.on('page',page=>page.on('pageerror',error=>errors.push(error.message)));
  return ctx;
}
async function auth(page,phone=MEMBER,code){
  await page.goto('https://photohouse.test/ui');
  await page.locator('#auth').waitFor({state:'visible'});
  await page.locator(code?'#register-tab':'#login-tab').click();
  await page.locator('#phone').fill(phone);await page.locator('#password').fill(PASSWORD);
  if(code){await page.locator('#code').fill(code);await page.locator('#name').fill('Synthetic joined member');}
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
  assert.match(await page.locator('#phone-help').textContent(),/China \(\+86\)/);
  await mutate('china-login');
  await auth(page,'10000000000');
  assert.equal(await page.locator('#account-label').textContent(),'+8610000000000');
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  await page.locator('#language').click();
  assert.match(await page.locator('#phone-help').textContent(),/默认中国区号 \+86/);
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(artifacts,'sign-in-default86-mobile-zh.png'),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.setViewportSize({width:1200,height:900});
  await page.locator('#language').click();await mutate('international-login');
  checkpoint('Bare phone defaults to +86; international login and bilingual help remain available');
  await auth(page);
  assert.equal(await page.locator('.asset').count(),2);
  assert.equal(await page.locator('#owner-panel').isVisible(),false);
  assert.equal(await page.locator('#people-panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.cookie),'');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  const cookies=await memberContext.cookies();assert.equal(cookies.length,1);assert(cookies[0].httpOnly&&cookies[0].secure&&cookies[0].sameSite==='Strict');
  await page.locator('.asset img').first().evaluate(img=>img.decode());
  await page.screenshot({path:path.join(artifacts,'gallery-desktop.png'),fullPage:true});
  checkpoint('Phone/password login uses HttpOnly cookie and scoped gallery');
  let legacyProbeStatus=null;
  await memberContext.route('https://sibling.photohouse.test/**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><img id="probe" src="https://photohouse.test/assets/101/thumbnail?library=family-a">'}));
  const legacyMediaRoute=async route=>{
    const headers=await route.request().allHeaders();delete headers['sec-fetch-site'];delete headers.origin;
    const response=await rpc({method:'GET',path:'/assets/101/thumbnail?library=family-a',headers});
    legacyProbeStatus=response.status;
    const output={...response.headers};delete output['content-length'];
    await route.fulfill({status:response.status,headers:output,body:Buffer.from(response.body,'base64')});
  };
  await memberContext.route('https://photohouse.test/assets/101/thumbnail?library=family-a',legacyMediaRoute);
  const sibling=await memberContext.newPage();await sibling.goto('https://sibling.photohouse.test/');
  await sibling.waitForFunction(()=>document.getElementById('probe').complete);
  assert.equal(legacyProbeStatus,403);
  assert.equal(await sibling.locator('#probe').evaluate(img=>img.naturalWidth),0);
  await sibling.close();await memberContext.unroute('https://photohouse.test/assets/101/thumbnail?library=family-a',legacyMediaRoute);
  checkpoint('Server denies sibling cookie embedding when same-origin signals are absent');
  await mutate('caption-html');
  await page.locator('.asset').filter({hasText:'101'}).click();
  await page.locator('#captions p').waitFor({state:'attached'});
  assert.match(await page.locator('#captions').textContent(),/<img src=x/);
  assert.equal(await page.locator('#captions img').count(),0);assert.equal(await page.evaluate(()=>window.syntheticXSS),undefined);
  assert.equal(await page.locator('#original').isVisible(),false);
  assert.equal(await page.locator('#face-panel').isVisible(),false);
  await page.locator('#close-viewer').click();
  checkpoint('Captions render as text and viewer cannot download originals');
  const oldViewer=delayNext(url=>url.pathname==='/assets/101/captions');
  await page.locator('.asset').filter({hasText:'101'}).click();await oldViewer.seen;
  await page.locator('#close-viewer').click();await page.locator('.asset').filter({hasText:'102'}).click();
  await page.locator('#captions p').waitFor({state:'attached'});oldViewer.release();await pause(150);
  assert.equal(await page.locator('#captions p').textContent(),'caption-102');
  // The describe control is offered only where a photo has no description, and every fixture
  // asset has one, so opening this photo must show its caption and no form. The write path
  // itself is covered by the source tests; this only pins that the control is not offered
  // where the route would refuse it.
  assert.equal(await page.locator('#captions form').count(),0);
  assert.equal(await page.locator('#captions input').count(),0);
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
  await owner.locator('#people-panel > summary').click();
  await owner.locator('.person-card').first().waitFor();
  assert.equal(await owner.locator('.person-card').count(),25);
  await owner.locator('#people-next').click();
  await owner.waitForFunction(()=>document.getElementById('people-page-label').textContent.includes('2 of 2'));
  assert.equal(await owner.locator('.person-card').count(),4);
  await owner.locator('#people-previous').click();await owner.locator('[data-person-id="1"]').waitFor();
  const alice=owner.locator('[data-person-id="1"]');
  await alice.getByRole('button',{name:'Review faces',exact:true}).click();
  await alice.locator('img').evaluate(img=>img.decode());
  await alice.locator('.face-review').click();await owner.locator('#viewer').waitFor({state:'visible'});
  await owner.locator('#close-viewer').click();
  await alice.locator('input').fill('家人 Alice');await alice.getByRole('button',{name:'Save name',exact:true}).click();
  await owner.waitForFunction(()=>document.getElementById('people-status').textContent==='Name saved.');
  await owner.locator('#people-query').fill('家人');await owner.locator('#people-search button').click();
  await owner.waitForFunction(()=>document.querySelectorAll('.person-card').length===1);
  assert.equal(await owner.locator('.person-card h3').textContent(),'家人 Alice');
  checkpoint('Owner searches paginated names, opens scoped faces and saves an audited name');
  await mutate('person-name-html');
  await owner.locator('.person-card input').fill('Stale edit');await owner.locator('.person-card form button').click();
  await owner.waitForFunction(()=>document.getElementById('people-status').textContent.includes('This person changed'));
  await owner.locator('#people-query').fill('');await owner.locator('#people-search button').click();
  await owner.locator('[data-person-id="1"]').waitFor();
  assert.equal(await owner.locator('[data-person-id="1"] h3 img').count(),0);
  assert.equal(await owner.evaluate(()=>window.syntheticXSS),undefined);
  await owner.locator('#people-query').fill('Shared');await owner.locator('#people-search button').click();
  await owner.waitForFunction(()=>document.querySelectorAll('.person-card').length===1);
  assert.equal(await owner.locator('.person-card input').count(),0);
  checkpoint('Stale rename conflicts safely, names render as text, shared-person rename is unavailable');
  await owner.locator('#people-query').fill('Person');await owner.locator('#people-search button').click();
  await owner.waitForFunction(()=>document.querySelectorAll('.person-card').length===25);
  await owner.locator('#people-query').fill('Person 10');await owner.locator('#people-search button').click();
  await owner.waitForFunction(()=>document.querySelectorAll('.person-card').length===1);
  await owner.locator('.person-card').getByRole('button',{name:'Review faces',exact:true}).click();
  await owner.locator('.person-card img').evaluate(img=>img.decode());
  await owner.locator('#people-panel').screenshot({path:path.join(artifacts,'people-owner-desktop.png')});
  await owner.setViewportSize({width:390,height:844});await owner.locator('#language').click();
  await owner.locator('.person-card').first().waitFor();
  assert(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await owner.locator('#people-panel').screenshot({path:path.join(artifacts,'people-owner-mobile-zh.png')});
  await owner.locator('#language').click();await owner.setViewportSize({width:1200,height:900});
  await owner.locator('.person-card').first().waitFor();
  checkpoint('Owner people management renders in English and Chinese on desktop and narrow screens');
  const oldPeople=delayNext(url=>url.pathname==='/admin/people'&&url.searchParams.get('q')==='Person');
  await owner.locator('#people-query').fill('Person');await owner.locator('#people-search button').click();await oldPeople.seen;
  await owner.locator('#people-query').fill('Shared');await owner.locator('#people-search button').click();
  await owner.waitForFunction(()=>document.querySelector('.person-card h3')?.textContent==='Shared person');
  oldPeople.release();await pause(150);
  assert.equal(await owner.locator('.person-card').count(),1);
  assert.equal(await owner.locator('.person-card h3').textContent(),'Shared person');
  const logoutPeople=delayNext(url=>url.pathname==='/admin/people');
  await owner.locator('#people-search button').click();await logoutPeople.seen;
  await owner.locator('#logout').click();await owner.locator('#auth').waitFor({state:'visible'});
  logoutPeople.release();await pause(150);
  assert.equal(await owner.locator('.person-card').count(),0);
  assert.equal(await owner.locator('#people-panel').isVisible(),false);
  await auth(owner,'+12025550100');
  await owner.locator('#people-panel > summary').click();
  await owner.locator('.person-card').first().waitFor();
  checkpoint('Delayed people search cannot replace newer results or reappear after logout');
  await owner.locator('#people-panel > summary').click();
  await owner.locator('.asset').filter({hasText:'102'}).click();

  const photoViewer=owner.locator('#photo-viewer'),photoStage=owner.locator('#viewer-media'),photoImage=photoStage.locator('.viewer-surface img');
  await photoViewer.waitFor({state:'visible'});await photoImage.evaluate(img=>img.decode());
  assert.deepEqual(await photoImage.evaluate(img=>[img.naturalWidth,img.naturalHeight]),[400,300]);
  assert.match(await owner.locator('#view-quality').textContent(),/Thumbnail preview/);
  assert(await owner.evaluate(()=>{const s=document.getElementById('viewer-media');return s.scrollWidth===s.clientWidth&&s.scrollHeight===s.clientHeight;}));
  await owner.screenshot({path:path.join(artifacts,'viewer-desktop-fit.png')});

  await owner.locator('#view-actual').click();
  assert.equal(await owner.locator('#view-scale').textContent(),'100%');
  assert.deepEqual(await photoImage.evaluate(img=>[Math.round(img.getBoundingClientRect().width),Math.round(img.getBoundingClientRect().height)]),[400,300]);
  assert.equal(await owner.locator('#view-actual').getAttribute('aria-pressed'),'true');
  await owner.locator('#view-width').click();
  const widthFit=await owner.evaluate(()=>{const s=document.getElementById('viewer-media'),img=s.querySelector('img');return {scale:parseFloat(document.getElementById('view-scale').textContent)/100,stage:[s.clientWidth,s.clientHeight],image:[img.getBoundingClientRect().width,img.getBoundingClientRect().height]};});
  assert(Math.abs(widthFit.image[0]/widthFit.image[1]-4/3)<0.02);assert(Math.abs(widthFit.image[0]-widthFit.stage[0])<=1);
  await owner.locator('#view-height').click();
  const heightFit=await owner.evaluate(()=>{const s=document.getElementById('viewer-media'),img=s.querySelector('img');return {scale:parseFloat(document.getElementById('view-scale').textContent)/100,stage:[s.clientWidth,s.clientHeight],image:[img.getBoundingClientRect().width,img.getBoundingClientRect().height]};});
  assert(Math.abs(heightFit.image[0]/heightFit.image[1]-4/3)<0.02);assert(Math.abs(heightFit.image[1]-heightFit.stage[1])<=1);
  await owner.locator('#view-in').click({clickCount:8});
  assert(await owner.evaluate(()=>{const s=document.getElementById('viewer-media');return s.scrollWidth>s.clientWidth&&s.scrollHeight>s.clientHeight;}));
  await owner.screenshot({path:path.join(artifacts,'viewer-desktop-zoom-pan.png')});
  const beforeDrag=await photoStage.evaluate(s=>[s.scrollLeft,s.scrollTop]);const box=await photoStage.boundingBox();
  await owner.mouse.move(box.x+box.width/2,box.y+box.height/2);await owner.mouse.down();await owner.mouse.move(box.x+box.width/2-120,box.y+box.height/2-90);await owner.mouse.up();
  const afterDrag=await photoStage.evaluate(s=>[s.scrollLeft,s.scrollTop]);assert(afterDrag[0]!==beforeDrag[0]||afterDrag[1]!==beforeDrag[1]);
  await photoStage.evaluate(s=>{s.scrollLeft=(s.scrollWidth-s.clientWidth)/2;s.scrollTop=(s.scrollHeight-s.clientHeight)/2;});
  const anchor={x:box.width*.7,y:box.height*.65};const beforeAnchor=await photoStage.evaluate((s,p)=>{const i=s.querySelector('img'),r=s.getBoundingClientRect(),ir=i.getBoundingClientRect(),scale=ir.width/i.naturalWidth;return [(p.x-(ir.left-r.left))/scale,(p.y-(ir.top-r.top))/scale];},anchor);
  const beforeWheel=await owner.locator('#view-scale').textContent();await owner.mouse.move(box.x+anchor.x,box.y+anchor.y);await owner.mouse.wheel(0,-100);
  await owner.waitForFunction(before=>document.getElementById('view-scale').textContent!==before,beforeWheel);
  const afterWheel=await owner.locator('#view-scale').textContent();assert(Number.parseInt(afterWheel)>Number.parseInt(beforeWheel));assert(Number.parseInt(afterWheel)<=1600);
  const afterAnchor=await photoStage.evaluate((s,p)=>{const i=s.querySelector('img'),r=s.getBoundingClientRect(),ir=i.getBoundingClientRect(),scale=ir.width/i.naturalWidth;return [(p.x-(ir.left-r.left))/scale,(p.y-(ir.top-r.top))/scale];},anchor);assert(Math.abs(afterAnchor[0]-beforeAnchor[0])<1&&Math.abs(afterAnchor[1]-beforeAnchor[1])<1);
  await photoStage.dispatchEvent('wheel',{deltaY:100000,clientX:box.x+box.width/2,clientY:box.y+box.height/2});assert(Number.parseInt(await owner.locator('#view-scale').textContent())>=1);
  await owner.locator('#view-in').click({clickCount:30});assert.equal(await owner.locator('#view-in').isDisabled(),true);
  await photoStage.evaluate(s=>{const r=s.getBoundingClientRect();for(let i=0;i<20;i++)s.dispatchEvent(new WheelEvent('wheel',{deltaY:1000,clientX:r.left+r.width/2,clientY:r.top+r.height/2,cancelable:true}));});
  assert.equal(await owner.locator('#view-scale').textContent(),'1%');assert.equal(await owner.locator('#view-out').isDisabled(),true);
  await photoStage.focus();await photoStage.press('0');assert.equal(await owner.locator('#view-fit').getAttribute('aria-pressed'),'true');
  await owner.locator('#view-fullscreen').click();await owner.waitForFunction(()=>document.fullscreenElement?.id==='photo-viewer');await owner.waitForFunction(()=>document.getElementById('view-fullscreen').textContent.includes('Exit fullscreen'));
  await owner.screenshot({path:path.join(artifacts,'viewer-desktop-fullscreen.png')});
  await owner.locator('#view-fullscreen').click();await owner.waitForFunction(()=>!document.fullscreenElement);
  await owner.locator('#close-viewer').click();await owner.locator('.asset').filter({hasText:'102'}).click();await owner.locator('#photo-viewer').waitFor({state:'visible'});await photoStage.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.equal(await owner.locator('#view-fit').getAttribute('aria-pressed'),'true');assert.equal(await owner.locator('#view-scale').textContent(),`${await owner.evaluate(()=>{const s=document.getElementById('viewer-media'),i=s.querySelector('img');return Math.round(Math.min(s.clientWidth/i.naturalWidth,s.clientHeight/i.naturalHeight)*100);})}%`);
  await owner.locator('#close-viewer').click();await owner.setViewportSize({width:390,height:844});await owner.locator('#language').click();await owner.locator('.asset').filter({hasText:'102'}).click();await owner.locator('#photo-viewer').waitFor({state:'visible'});await photoStage.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert(await owner.locator('#viewer').evaluate(d=>d.scrollWidth<=d.clientWidth));
  await owner.screenshot({path:path.join(artifacts,'viewer-mobile-zh.png')});await owner.locator('#close-viewer').click();await owner.locator('#language').click();await owner.setViewportSize({width:1200,height:900});await owner.locator('.asset').filter({hasText:'102'}).click();await owner.locator('#face-panel summary').click();
  checkpoint('Viewer fit modes preserve aspect ratio, native actual pixels, bounded zoom/pan, fullscreen, reset and narrow Chinese layout');

  const face=owner.locator('[data-face-id="200"]');await face.waitFor();
  await face.locator('img').evaluate(img=>img.decode());
  assert.equal(await face.locator('h4').textContent(),'Unassigned');
  await face.getByRole('button',{name:'Choose a person',exact:true}).click();
  await owner.locator('.person-choice').first().waitFor();
  assert.equal(await owner.locator('.person-choice').count(),25);
  await owner.locator('.face-picker').getByRole('button',{name:'Next',exact:true}).click();
  const sharedChoice=owner.getByRole('button',{name:'Shared person · 2',exact:true});
  const assignmentPostsBeforeRestricted=assignmentPosts;
  assert.equal(await sharedChoice.isDisabled(),true);
  assert.match(await sharedChoice.locator('xpath=..').locator('p').textContent(),/ownership needs review/i);
  await sharedChoice.click({force:true});await pause(100);assert.equal(assignmentPosts,assignmentPostsBeforeRestricted);
  await owner.getByRole('button',{name:'Person 36 · 36',exact:true}).click();
  assert.equal(await face.locator('h4').textContent(),'Unassigned');
  await owner.locator('.assignment-review img').evaluate(img=>img.decode());
  assert(await owner.locator('.assignment-review').evaluate(node=>{const r=node.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}));
  await owner.screenshot({path:path.join(artifacts,'face-assignment-confirm-desktop.png')});
  await owner.getByRole('button',{name:'Confirm assignment',exact:true}).click();
  await owner.waitForFunction(()=>document.getElementById('face-status').textContent.startsWith('Assignment saved'));
  assert.equal(await face.locator('h4').textContent(),'Person 36');
  checkpoint('Owner reviews a face, pages through saved people and explicitly confirms assignment');
  async function chooseTen(){
    await face.getByRole('button',{name:'Choose a person',exact:true}).click();
    await owner.locator('.face-picker input').fill('Person 10');await owner.locator('.face-picker form button').click();
    await owner.getByRole('button',{name:'Person 10 · 10',exact:true}).click();
  }
  await chooseTen();await mutate('face-assignment-changed');
  await owner.getByRole('button',{name:'Confirm assignment',exact:true}).click();
  await owner.waitForFunction(()=>document.querySelector('.face-picker')?.textContent.includes('The face or person changed'));
  await owner.locator('#face-refresh').click();await face.waitFor();
  assert.equal(await face.locator('h4').textContent(),'Person 36');
  await chooseTen();loseFaceSave=true;
  await owner.getByRole('button',{name:'Confirm assignment',exact:true}).click();
  await owner.waitForFunction(()=>document.querySelector('.face-picker')?.textContent.includes('Save not confirmed'));
  assert.equal(await owner.getByRole('button',{name:'Confirm assignment',exact:true}).count(),0);
  await owner.locator('#face-refresh').click();await face.waitFor();
  assert.equal(await face.locator('h4').textContent(),'Person 10');
  checkpoint('Stale face correction is refused; lost save response requires fresh assignment readback');
  const delayedFaces=delayNext(url=>url.pathname==='/admin/assets/102/faces');
  await owner.locator('#face-refresh').click();await delayedFaces.seen;
  await owner.locator('#close-viewer').click();await owner.locator('.asset').filter({hasText:'101'}).click();
  await owner.locator('#face-panel summary').click();await owner.locator('.face-label-card').first().waitFor();
  delayedFaces.release();await pause(150);
  assert.equal(await owner.locator('[data-face-id="200"]').count(),0);
  assert.equal(await owner.locator('.face-label-card').count(),25);
  await owner.locator('#face-next').click();await owner.locator('[data-face-id="36"]').waitFor();
  assert.equal(await owner.locator('.face-label-card').count(),4);
  await owner.locator('#close-viewer').click();
  await owner.setViewportSize({width:390,height:844});await owner.locator('#language').click();
  await owner.locator('.asset').filter({hasText:'102'}).click();await owner.locator('#face-panel summary').click();await face.waitFor();
  await face.getByRole('button',{name:'选择人物',exact:true}).click();
  await owner.locator('.face-picker input').fill('Person 36');await owner.locator('.face-picker form button').click();
  await owner.getByRole('button',{name:'Person 36 · 36',exact:true}).click();
  await owner.locator('.assignment-review img').evaluate(img=>img.decode());
  await owner.screenshot({path:path.join(artifacts,'face-assignment-confirm-mobile-zh.png')});
  assert(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert(await owner.locator('#viewer').evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth));
  await owner.locator('#close-viewer').click();await owner.locator('#language').click();await owner.setViewportSize({width:1200,height:900});
  await owner.locator('.asset').first().waitFor();
  checkpoint('Face pages discard closed-viewer responses; Chinese narrow-screen confirmation renders');
  await owner.locator('.asset').filter({hasText:'102'}).click();await owner.locator('#face-panel summary').click();await face.waitFor();
  await face.getByRole('button',{name:'Create a new person',exact:true}).click();
  await owner.locator('.new-person-form input').fill('家人新名字');owner.once('dialog',dialog=>dialog.accept());
  await owner.getByRole('button',{name:'Create and assign',exact:true}).click();
  await owner.waitForFunction(()=>document.querySelector('[data-face-id="200"] h4')?.textContent==='家人新名字');
  owner.once('dialog',dialog=>dialog.accept());loseFaceSave=true;await face.getByRole('button',{name:'Remove this assignment',exact:true}).click();
  await owner.waitForFunction(()=>document.querySelector('[data-face-id="200"] .face-action-status')?.textContent.includes('Save not confirmed'));
  assert.equal(await face.getByRole('button',{name:'Remove this assignment',exact:true}).isDisabled(),false);
  await owner.locator('#face-refresh').click();await face.waitFor();
  await owner.waitForFunction(()=>document.querySelector('[data-face-id="200"] h4')?.textContent==='Unassigned');
  await face.getByRole('button',{name:'Choose a person',exact:true}).click();
  await owner.locator('.face-picker input').fill('家人新名字');await owner.locator('.face-picker form button').click();
  await owner.locator('.person-choice').filter({hasText:'家人新名字'}).click();
  await owner.getByRole('button',{name:'Confirm assignment',exact:true}).click();
  await owner.waitForFunction(()=>document.querySelector('[data-face-id="200"] h4')?.textContent==='家人新名字');
  await owner.locator('#close-viewer').click();
  checkpoint('New named person remains selectable after removing their last face assignment');
  await owner.locator('#albums-panel > summary').click();await owner.locator('#album-create').click();
  await owner.locator('#album-title').fill('Our seaside trip');await owner.locator('#album-title_zh').fill('全家的海边旅行');
  await owner.locator('#album-description').fill('A weekend together. 一起看海。');await owner.locator('#album-theme').selectOption('trip');
  await owner.locator('#album-choices [data-asset-id="101"]').click();await owner.locator('#album-choices [data-asset-id="102"]').click();
  await owner.locator('#album-selected [data-asset-id="102"]').getByRole('button',{name:'Move earlier',exact:true}).click();
  await owner.locator('#album-selected [data-asset-id="102"]').getByRole('button',{name:'Use as cover',exact:true}).click();
  assert.deepEqual(await owner.locator('#album-selected .album-selection').evaluateAll(rows=>rows.map(row=>row.dataset.assetId)),['102','101']);
  await owner.locator('#album-save').scrollIntoViewIfNeeded();await owner.screenshot({path:path.join(artifacts,'album-editor-desktop.png')});
  loseAlbumSave=true;await owner.locator('#album-save').click();
  await owner.waitForFunction(()=>document.getElementById('album-editor-status').textContent.includes('Save not confirmed'));
  assert.equal(await owner.locator('#album-title').isDisabled(),true);
  await owner.locator('#album-save').click();await owner.locator('#album-editor').waitFor({state:'hidden'});
  await owner.locator('.album-card').waitFor();assert.equal(await owner.locator('.album-card').count(),1);
  await page.locator('#albums-panel > summary').click();await page.locator('.album-card').waitFor();
  assert.equal(await page.locator('#album-create').isVisible(),false);assert.equal(await page.getByRole('button',{name:'Edit album',exact:true}).count(),0);
  await page.locator('.album-strip button').first().click();await page.locator('#viewer').waitFor({state:'visible'});await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.equal(await page.locator('#view-position').textContent(),'This album · 1 / 2');
  assert.equal(await page.locator('#view-previous').isDisabled(),true);await page.locator('#view-next').click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.match(await page.locator('#viewer-title').textContent(),/101/);assert.equal(await page.locator('#view-next').isDisabled(),true);await page.locator('#close-viewer').click();
  checkpoint('Owner builds a bilingual themed album with ordered photos and cover; creation retry is not duplicated; members can view');
  owner.once('dialog',dialog=>dialog.accept());
  await owner.locator('.album-card').getByRole('button',{name:'Put away',exact:true}).click();
  await owner.waitForFunction(()=>document.querySelectorAll('#album-list .album-card').length===0);
  await owner.locator('#album-archived-panel > summary').click();
  await owner.locator('.album-archived-card').waitFor();
  assert.equal(await owner.locator('.album-archived-card h3').textContent(),'Our seaside trip');
  await owner.locator('#album-archived-panel').screenshot({path:path.join(artifacts,'archived-album.png')});
  await owner.locator('.album-archived-card').getByRole('button',{name:'Bring back',exact:true}).click();
  await owner.locator('.album-card').waitFor();
  assert.equal(await owner.locator('.album-card h3').textContent(),'Our seaside trip');
  checkpoint('Owner can put an album away and bring it back without losing its photos');
  await owner.getByRole('button',{name:'Edit album',exact:true}).click();await owner.locator('#album-title').fill('Unsaved private draft');
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  assert.equal(await owner.locator('#album-editor').isVisible(),false);assert.equal(await owner.locator('#album-title').count(),0);
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
  await owner.locator('#album-title').waitFor();assert.equal(await owner.locator('#album-title').inputValue(),'Unsaved private draft');
  owner.once('dialog',dialog=>dialog.accept());await owner.locator('#album-editor').getByRole('button',{name:'Cancel',exact:true}).click();
  checkpoint('Album draft clears from background DOM and returns only after same-owner revalidation');
  await owner.getByRole('button',{name:'Edit album',exact:true}).click();await owner.locator('#album-description').fill('Stale draft');
  await mutate('album-title-changed');await owner.locator('#album-save').click();
  await owner.waitForFunction(()=>document.getElementById('album-editor-status').textContent.includes('Album changed'));
  assert.equal(await owner.locator('#album-save').isDisabled(),true);
  owner.once('dialog',dialog=>dialog.accept());await owner.locator('#album-editor').getByRole('button',{name:'Cancel',exact:true}).click();
  await owner.locator('#albums-panel > summary').click();await owner.locator('#albums-panel > summary').click();
  await owner.waitForFunction(()=>document.querySelector('.album-card h3')?.textContent==='Changed elsewhere');
  await owner.getByRole('button',{name:'Edit album',exact:true}).click();
  await owner.locator('#album-selected').getByRole('button',{name:'Remove',exact:true}).first().click();
  await owner.locator('#album-selected').getByRole('button',{name:'Remove',exact:true}).first().click();
  await owner.locator('#album-save').click();await owner.locator('#album-editor').waitFor({state:'hidden'});
  // Closing the editor precedes the asynchronous album-list readback.
  await owner.locator('.album-card').waitFor();
  assert.equal(await owner.locator('.album-card').count(),1);assert.equal(await owner.locator('.album-card img').count(),0);
  await owner.setViewportSize({width:390,height:844});await owner.locator('#language').click();await owner.locator('.album-card').waitFor();
  await owner.getByRole('button',{name:'编辑相册',exact:true}).click();await owner.locator('#album-title').scrollIntoViewIfNeeded();
  await owner.screenshot({path:path.join(artifacts,'album-editor-mobile-zh.png')});
  assert(await owner.locator('#album-editor').evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth));
  await owner.locator('#album-editor').getByRole('button',{name:'取消',exact:true}).click();
  await owner.locator('#language').click();await owner.setViewportSize({width:1200,height:900});await owner.locator('.asset').first().waitFor();
  checkpoint('Album stale edits are refused; empty albums retain ownership; Chinese mobile editor fits');
  await owner.locator('#owner-panel summary').click();
  await owner.locator('#invite-phone').fill('+12025550103');await owner.locator('#invite-form button').click();
  await owner.locator('#created-code').waitFor({state:'visible'});
  const code=await owner.locator('#created-code').inputValue();assert.match(code,/^[a-f0-9]{8}(-[a-f0-9]{8}){3}$/);
  const joinedContext=await context(browser),joined=await joinedContext.newPage();await auth(joined,'+12025550103',code);
  assert.equal(await joined.locator('#owner-panel').isVisible(),false);assert.equal(await joined.locator('.asset').count(),2);
  checkpoint('Owner manually creates phone-bound invitation; registration joins as viewer');
  await owner.locator('#owner-panel summary').click();
  await owner.locator('#members-panel summary').click();
  const joinedRow=owner.locator('.member-row').filter({hasText:'+12025550103'});
  await joinedRow.getByRole('button',{name:'Revoke access',exact:true}).click();
  await owner.screenshot({path:path.join(artifacts,'owner-revocation-review.png'),fullPage:true});
  await mutate('change-joined-membership');
  await joinedRow.getByRole('button',{name:'Confirm revocation',exact:true}).click();
  await owner.waitForFunction(()=>document.getElementById('status').textContent.includes('Membership changed'));
  await joined.locator('#refresh').click();await joined.locator('.asset').first().waitFor();
  await joinedRow.getByRole('button',{name:'Revoke access',exact:true}).click();
  await joinedRow.getByRole('button',{name:'Confirm revocation',exact:true}).click();
  await owner.waitForFunction(()=>document.getElementById('status').textContent==='Access revoked.');
  await joined.locator('#refresh').click();
  await joined.waitForFunction(()=>document.getElementById('library-select').options.length===0);
  assert.equal(await joined.locator('.asset').count(),0);
  checkpoint('Owner revocation requires fresh review and stops the member next read');
  await owner.locator('#owner-panel summary').click();
  await owner.locator('#invite-phone').fill('+12025550104');await owner.locator('#invite-form button').click();
  await owner.waitForFunction(previous=>document.getElementById('created-code').value!==previous,code);
  const cancelled=await owner.locator('#created-code').inputValue();await owner.locator('#cancel-invite').click();
  await owner.locator('#invitation-result').waitFor({state:'hidden'});
  await joined.locator('#logout').click();await joined.locator('#auth').waitFor({state:'visible'});
  await joined.setViewportSize({width:390,height:844});
  await joined.locator('#register-tab').click();await joined.locator('#phone').fill('+12025550104');await joined.locator('#password').fill(PASSWORD);await joined.locator('#name').fill('Cancelled invite member');await joined.locator('#code').fill(cancelled);await joined.locator('#auth-submit').click();
  await joined.waitForFunction(()=>document.getElementById('status').textContent.includes('could not be confirmed'));
  assert.equal(await joined.locator('#auth-feedback').isVisible(),true);
  assert.match(await joined.locator('#auth-feedback').textContent(),/could not be confirmed/);
  const authButtonBox=await joined.locator('#auth-submit').boundingBox();
  const authFeedbackBox=await joined.locator('#auth-feedback').boundingBox();
  assert(authButtonBox&&authFeedbackBox&&authFeedbackBox.y>=authButtonBox.y&&authFeedbackBox.y<844);
  await joined.screenshot({path:path.join(artifacts,'registration-error-mobile.png'),fullPage:true});
  assert.equal(await joined.locator('.asset').count(),0);
  checkpoint('Cancelled invitation cannot register or disclose photos');
  await joined.locator('#language').click();
  assert.match(await joined.locator('#auth-feedback').textContent(),/无法确认/);
  await joined.locator('#login-tab').click();
  assert.equal(await joined.locator('#auth-feedback').textContent(),'');
  await joined.locator('#register-tab').click();
  await joined.locator('#password').fill(PASSWORD);await joined.locator('#code').fill(cancelled);await joined.locator('#name').fill('');
  await joined.locator('#auth-submit').click();
  assert.match(await joined.locator('#auth-feedback').textContent(),/名字/);
  await joined.locator('#name').fill('Synthetic member');await joined.locator('#code').fill('');
  await joined.locator('#auth-submit').click();
  assert.match(await joined.locator('#auth-feedback').textContent(),/邀请码/);
  await joined.locator('#auth-feedback').scrollIntoViewIfNeeded();
  await joined.screenshot({path:path.join(artifacts,'registration-validation-mobile-zh.png'),fullPage:true});
  checkpoint('Authentication feedback translates, clears on mode switch and includes native field validation');
  await owner.locator('.asset').filter({hasText:'101'}).click();
  await owner.locator('#story-add').waitFor();await owner.locator('#story-add').click();
  const longStory='Her first visit to Grandma’s garden. 奶奶的花园，第一次浇花。\n'.repeat(90)+'<img src=x onerror="window.storyXSS=true">';
  await owner.locator('#story-title').fill('A morning in Grandma’s garden');await owner.locator('#story-byline').fill('Dad');
  await owner.locator('#story-language').selectOption('mixed');await owner.locator('#story-text').fill(longStory);
  owner.once('dialog',dialog=>dialog.dismiss());await owner.locator('#close-viewer').click();
  assert.equal(await owner.locator('#story-text').inputValue(),longStory);
  await owner.locator('#story-text').scrollIntoViewIfNeeded();
  await owner.screenshot({path:path.join(artifacts,'family-story-editor-desktop.png'),fullPage:true});
  loseStorySave=true;await owner.locator('#story-save').click();
  await owner.waitForFunction(()=>document.getElementById('story-status').textContent.includes('Save not confirmed'));
  assert.equal(await owner.locator('#story-text').isDisabled(),true);
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
  await owner.locator('#story-form').waitFor({state:'visible'});
  assert.equal(await owner.locator('#story-text').isDisabled(),true);
  await owner.locator('#story-save').click();await owner.locator('#story-form').waitFor({state:'hidden'});
  assert.equal(await owner.locator('#story-list .story-card').count(),1);
  assert.equal(await owner.locator('#story-list .story-text').textContent(),longStory);
  assert.equal(await owner.locator('#story-list img').count(),0);assert.equal(await owner.evaluate(()=>window.storyXSS),undefined);
  checkpoint('Long bilingual story survives a lost save response without duplication; text is not HTML');
  await owner.locator('#story-list').getByRole('button',{name:'Edit',exact:true}).click();
  await owner.locator('#story-text').fill('Our draft: 奶奶花园的快乐早晨。');
  await owner.evaluate(async()=>{
    const profile=await (await fetch('/auth/session')).json();
    const stories=await (await fetch('/assets/101/stories?library=family-a')).json();const story=stories.items[0];
    const response=await fetch(`/stories/${story.id}?library=family-a`,{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':profile.csrf_token},body:JSON.stringify({title:story.title,text:'Another tab’s story',byline:'Dad',language:'en',revision:String(story.revision),mutation_id:crypto.randomUUID()})});
    if(!response.ok)throw new Error('Synthetic concurrent save failed');
  });
  await owner.locator('#story-save').click();await owner.locator('#story-compare').waitFor();
  assert.equal(await owner.locator('#story-text').inputValue(),'Our draft: 奶奶花园的快乐早晨。');
  await owner.locator('#story-compare').click();await owner.locator('#story-conflict .story-text').waitFor();
  assert.equal(await owner.locator('#story-conflict .story-text').textContent(),'Another tab’s story');
  owner.once('dialog',dialog=>dialog.accept());await owner.locator('#story-conflict button').click();await owner.locator('#story-save').click();
  await owner.locator('#story-form').waitFor({state:'hidden'});
  await owner.locator('#story-list').getByRole('button',{name:'History',exact:true}).click();
  await owner.locator('#story-history .story-card').first().waitFor();assert.equal(await owner.locator('#story-history .story-card').count(),3);
  assert.equal(await owner.locator('#story-history .story-text').last().textContent(),longStory);
  checkpoint('Concurrent edits require explicit comparison; all three revisions survive');
  await owner.locator('#close-viewer').click();await owner.locator('#search-text').fill('奶奶');await owner.locator('#story-search button[type=submit]').click();
  await owner.locator('.search-excerpt').waitFor();assert.equal(await owner.locator('.asset').count(),1);
  assert.match(await owner.locator('.search-excerpt').textContent(),/Found in a family story/);
  await owner.locator('.asset').click();await owner.locator('#story-list .story-text').waitFor();
  assert.equal(await owner.locator('#story-list .story-text').textContent(),'Our draft: 奶奶花园的快乐早晨。');
  await owner.locator('#story-list .story-text').scrollIntoViewIfNeeded();
  await owner.screenshot({path:path.join(artifacts,'family-story-saved-desktop.png'),fullPage:true});
  await owner.locator('#close-viewer').click();await owner.locator('#language').click();await owner.locator('.asset').waitFor();
  await owner.setViewportSize({width:390,height:844});await owner.locator('.asset').click();await owner.locator('#story-list .story-text').waitFor();
  assert(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await owner.screenshot({path:path.join(artifacts,'family-story-mobile-zh.png'),fullPage:true});
  checkpoint('Saved stories reload and are searchable in Chinese; narrow Chinese viewer renders');
  await owner.locator('#close-viewer').click();await owner.locator('#language').click();await owner.locator('.asset').waitFor();
  await owner.setViewportSize({width:1200,height:900});
  await page.locator('.asset').filter({hasText:'101'}).click();await page.locator('#story-list .story-text').waitFor();
  assert.equal(await page.locator('#story-add').isVisible(),false);assert.equal(await page.locator('#story-list button').count(),0);
  await page.locator('#close-viewer').click();
  checkpoint('Viewer can read family stories but cannot edit or read restricted history');
  await owner.locator('.asset').click();await owner.locator('#story-list .story-text').waitFor();
  await owner.locator('#story-list').getByRole('button',{name:'Edit',exact:true}).click();
  await owner.locator('#story-text').fill('Memory-only draft after background');
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  assert.equal(await owner.locator('#story-text').inputValue(),'');assert.equal(await owner.locator('#viewer').isVisible(),false);
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
  await owner.waitForFunction(()=>document.getElementById('story-status').textContent.includes('draft was restored'));
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  const interruptedRestore=delayNext(url=>url.pathname==='/auth/session');
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
  await interruptedRestore.seen;
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  interruptedRestore.release();await pause(250);
  assert.equal(await owner.locator('#viewer').isVisible(),false);
  assert.equal(await owner.locator('#story-text').inputValue(),'');
  await owner.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
  await owner.waitForFunction(()=>document.getElementById('story-status').textContent.includes('draft was restored'));
  assert.equal(await owner.locator('#story-text').inputValue(),'Memory-only draft after background');
  assert.equal(await owner.evaluate(()=>localStorage.length+sessionStorage.length),0);
  owner.once('dialog',dialog=>dialog.accept());await owner.locator('#story-cancel').click();
  await owner.locator('#story-list').getByRole('button',{name:'History',exact:true}).click();
  await owner.locator('#story-history .story-card').first().waitFor();
  await owner.locator('#story-history button').last().click();
  assert.equal(await owner.locator('#story-text').inputValue(),longStory);
  owner.once('dialog',dialog=>dialog.accept());await owner.locator('#story-cancel').click();
  await owner.locator('#close-viewer').click();
  checkpoint('Background clears private DOM; same-account revalidation restores draft; history can seed a new draft');
  await owner.locator('.asset').click();await owner.locator('#story-list .story-text').waitFor();
  loseStoryDelete=true;owner.once('dialog',dialog=>dialog.accept());
  await owner.locator('#story-list').getByRole('button',{name:'Remove story',exact:true}).click();
  await owner.waitForFunction(()=>!document.getElementById('story-status').textContent.includes('Loading')&&document.getElementById('story-list').children.length>0);
  await pause(100);
  owner.once('dialog',dialog=>dialog.accept());
  await owner.locator('#story-list').getByRole('button',{name:'Remove story',exact:true}).click();
  await owner.waitForFunction(()=>document.getElementById('story-status').textContent==='Story removed.');
  await owner.locator('#story-history').getByRole('button',{name:'History',exact:true}).click();
  await owner.locator('#story-history .story-card').first().waitFor();
  assert.equal(await owner.locator('#story-history .story-card').count(),4);
  checkpoint('Lost delete response retries the same mutation and keeps one tombstone revision');
  await owner.locator('#close-viewer').click();await owner.locator('#clear-search').click();await owner.locator('.asset').first().waitFor();
  await owner.evaluate(async()=>{
    const profile=await (await fetch('/auth/session')).json();
    for(let i=1;i<=11;i++){
      const response=await fetch('/assets/101/stories?library=family-a',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':profile.csrf_token},body:JSON.stringify({title:'Page story '+i,text:'Paged memory '+i,byline:'Synthetic author',language:'en',mutation_id:crypto.randomUUID()})});
      if(!response.ok)throw new Error('Synthetic story page setup failed');
    }
  });
  await owner.locator('.asset').filter({hasText:'101'}).click();await owner.locator('#story-more').waitFor();
  const storyPage=delayNext(url=>url.pathname==='/assets/101/stories'&&url.searchParams.get('page')==='2');
  await owner.locator('#story-more').click();await storyPage.seen;
  await owner.evaluate(()=>document.getElementById('story-more').click());
  storyPage.release();await owner.waitForFunction(()=>document.querySelectorAll('#story-list .story-card').length===10);
  await owner.locator('#story-more').click();await owner.waitForFunction(()=>document.querySelectorAll('#story-list .story-card').length===11);
  assert.equal(new Set(await owner.locator('#story-list h4').allTextContents()).size,11);
  checkpoint('Repeated More clicks cannot skip an in-flight story page');
  const firstHistory=delayNext(url=>url.pathname.endsWith('/history'));
  await owner.locator('#story-list .story-card').nth(0).getByRole('button',{name:'History',exact:true}).click();await firstHistory.seen;
  await owner.locator('#story-list .story-card').nth(1).getByRole('button',{name:'History',exact:true}).click();
  const secondTitle=await owner.locator('#story-list .story-card').nth(1).locator('h4').textContent();
  await owner.waitForFunction(title=>document.querySelector('#story-history .story-card h4')?.textContent===title,secondTitle);
  firstHistory.release();await pause(150);
  assert.equal(await owner.locator('#story-history .story-card h4').textContent(),secondTitle);
  await owner.locator('#close-viewer').click();
  checkpoint('Delayed history for another story cannot replace the selected history');
  await owner.locator('#search-text').fill('Page story 11');await owner.locator('#story-search button[type=submit]').click();
  await owner.locator('.asset').waitFor();assert.equal(await owner.locator('.asset').count(),1);
  await owner.locator('.asset').click();await owner.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.equal(await owner.locator('#view-position').textContent(),'This page · 1 / 1');
  assert.equal(await owner.locator('#view-previous').isDisabled(),true);assert.equal(await owner.locator('#view-next').isDisabled(),true);
  await owner.locator('#close-viewer').click();await owner.locator('#clear-search').click();await owner.locator('.asset').first().waitFor();
  checkpoint('Search-result sequence is limited to the returned subset, not the entire library');
  const preparedStart=browserRequests.length;await mutate('prepare-1024-thumbnail');
  await page.locator('.asset').filter({hasText:'101'}).click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  const preparedRequests=browserRequests.slice(preparedStart);
  assert(preparedRequests.some(item=>item.method==='HEAD'&&item.path.includes('/assets/101/thumbnail?')&&item.path.includes('size=1024')));
  assert(preparedRequests.some(item=>item.method==='GET'&&item.path.includes('/assets/101/thumbnail?')&&item.path.includes('size=1024')));
  await page.locator('#close-viewer').click();await page.locator('.asset').filter({hasText:'102'}).click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  const fallbackRequests=browserRequests.slice(preparedStart).filter(item=>item.path.includes('/assets/102/thumbnail'));
  assert(fallbackRequests.some(item=>item.method==='HEAD'&&item.path.includes('size=1024')));
  // The size-less 256 URL is byte-identical to the one the gallery grid already
  // fetched, so a correct fallback is served from the HTTP cache and emits no
  // second request for interception to observe. Assert the resolved image
  // instead: the viewer must abandon size=1024 and render real pixels.
  const fallbackImage=page.locator('.viewer-surface img').last();
  assert.equal(String(await fallbackImage.getAttribute('src')).includes('size=1024'),false,
    'absent 1024 must fall back off the size=1024 URL');
  assert((await fallbackImage.evaluate(image=>image.naturalWidth))>0,
    'the fallback preview must render pixels');
  await page.locator('#close-viewer').click();checkpoint('Prepared 1024 preview uses authorized HEAD/GET; missing 1024 falls back once to 256');
  await mutate('thumbnail-head-503');await page.locator('.asset').filter({hasText:'101'}).click();await pause(150);
  assert.equal(await page.locator('.viewer-surface img').count(),0);assert.equal(await page.locator('#view-play').getAttribute('aria-pressed'),'false');
  await page.locator('#close-viewer').click();
  const stalePreview=delayNext(url=>url.pathname==='/assets/101/thumbnail'&&url.searchParams.get('size')==='1024');
  await page.locator('.asset').filter({hasText:'101'}).click();await stalePreview.seen;await page.locator('#close-viewer').click();stalePreview.release();await pause(150);
  assert.equal(await page.locator('.viewer-surface img').count(),0);assert.equal(await page.locator('#viewer').isVisible(),false);
  checkpoint('Preview HEAD 503 does not retry/fallback; stale HEAD after close cannot inject an image');
  // Synthetic sequence contract: a gallery page is the sequence boundary.
  // The protected gallery orders taken_at DESC, id DESC, and test_library_reads
  // pins items[0] to 102, so this synthetic page reads 102 then 101.
  await page.locator('.asset').first().waitFor();
  await page.locator('.asset').filter({hasText:'102'}).click();
  await page.locator('#photo-viewer').waitFor({state:'visible'});
  await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.equal(await page.locator('#view-position').textContent(),'This page · 1 / 2');
  assert.equal(await page.locator('#view-previous').isDisabled(),true);
  assert.equal(await page.locator('#view-next').isDisabled(),false);
  await page.locator('#view-next').click();await page.locator('#viewer-title').waitFor();
  await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.match(await page.locator('#viewer-title').textContent(),/101/);
  assert.equal(await page.locator('#view-position').textContent(),'This page · 2 / 2');
  assert.equal(await page.locator('#view-next').isDisabled(),true);
  await page.locator('#view-previous').click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.match(await page.locator('#viewer-title').textContent(),/102/);
  checkpoint('Gallery sequence exposes current-page order, position, and previous/next bounds');
  await page.locator('#view-actual').click();
  await page.locator('#view-fullscreen').click();await page.waitForFunction(()=>document.fullscreenElement?.id==='photo-viewer');
  await page.locator('#view-next').click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.equal(await page.evaluate(()=>document.fullscreenElement?.id),'photo-viewer');
  assert.equal(await page.locator('#view-fit').getAttribute('aria-pressed'),'true');
  await page.locator('#view-fullscreen').click();await page.waitForFunction(()=>!document.fullscreenElement);
  checkpoint('Manual navigation resets fit mode and retains fullscreen across a step');
  // The filmstrip mirrors the legacy strip over the same loaded order, and reuses the
  // gallery grid's already-authorized 256 URL rather than escalating to a larger variant.
  const filmstrip=page.locator('#viewer-filmstrip');
  assert.equal(await filmstrip.getAttribute('aria-label'),'Photos in this view');
  assert.equal(await filmstrip.locator('button').count(),2);
  assert.equal(await filmstrip.locator('button').first().locator('img').getAttribute('src'),'/assets/102/thumbnail?library=family-a');
  assert.equal(await filmstrip.locator('button[aria-current="true"]').getAttribute('data-viewer-index'),'1');
  assert.equal(await filmstrip.locator('button').first().getAttribute('aria-label'),'Photo 1 / 2');
  await filmstrip.locator('img').first().evaluate(img=>img.decode());
  assert((await filmstrip.locator('img').first().evaluate(img=>img.naturalWidth))>0);
  await filmstrip.locator('button').first().click();
  await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.match(await page.locator('#viewer-title').textContent(),/102/);
  assert.equal(await page.locator('#view-position').textContent(),'This page · 1 / 2');
  assert.equal(await filmstrip.locator('button[aria-current="true"]').getAttribute('data-viewer-index'),'0');
  assert.equal(await page.locator('#view-play').getAttribute('aria-pressed'),'false');
  checkpoint('Viewer filmstrip mirrors the loaded order, marks the current item, and jumps to it');
  await page.locator('#close-viewer').click();
  assert.equal(await filmstrip.locator('button').count(),0);
  await page.locator('.asset').filter({hasText:'102'}).click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  if(page.clock&&typeof page.clock.install==='function')await page.clock.install();
  await page.locator('#view-interval').selectOption('5000');await page.locator('#view-play').click();
  assert.equal(await page.locator('#view-play').getAttribute('aria-pressed'),'true');
  if(page.clock&&typeof page.clock.fastForward==='function')await page.clock.fastForward(5000);else await pause(5200);
  await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.equal(await page.locator('#view-position').textContent(),'This page · 2 / 2');
  if(page.clock&&typeof page.clock.fastForward==='function')await page.clock.fastForward(5000);else await pause(5200);
  assert.equal(await page.locator('#view-play').getAttribute('aria-pressed'),'false');
  assert.equal(await page.locator('#view-position').textContent(),'This page · 2 / 2');
  if(page.clock&&typeof page.clock.uninstall==='function')await page.clock.uninstall();
  // A modal <dialog> makes the rest of the page inert, so the language toggle is
  // only reachable with the viewer closed — the order used elsewhere in this file.
  await page.locator('#close-viewer').click();
  await page.setViewportSize({width:1200,height:900});await page.locator('#language').click();
  await page.locator('.asset').filter({hasText:'102'}).click();
  await page.locator('#photo-viewer').waitFor({state:'visible'});
  await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  await page.screenshot({path:path.join(artifacts,'viewer-sequence-desktop-zh.png')});
  await page.locator('#close-viewer').click();await page.locator('#language').click();
  checkpoint('Slideshow advances after image load, stops at the final item, and supports interval control');
  // A delayed next response must not repopulate a closed or changed viewer.
  await page.locator('.asset').filter({hasText:'102'}).click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  const delayedSequence=delayNext(url=>url.pathname==='/assets/detail/101');
  await page.locator('#view-next').click();await delayedSequence.seen;await page.locator('#close-viewer').click();
  delayedSequence.release();await pause(150);assert.equal(await page.locator('#viewer').isVisible(),false);
  await page.locator('.asset').filter({hasText:'102'}).click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  failNextPath='/assets/detail/101';await page.locator('#view-next').click();await pause(150);
  assert.equal(await page.locator('#view-play').getAttribute('aria-pressed'),'false');
  // A step commits to the requested item immediately: closeViewer drops the previous
  // photo before the new detail is fetched, so a failed step reports that item's
  // error instead of silently staying on the photo the user just left. What must not
  // happen is advancing *past* the requested item, retrying, or leaving a stale image.
  assert.match(await page.locator('#viewer-title').textContent(),/101/);
  assert.equal(await page.locator('#view-position').textContent(),'This page · 2 / 2');
  assert.equal(await page.locator('#view-next').isDisabled(),true);
  assert.equal(await page.locator('.viewer-surface img').count(),0);
  // The failed step stays recoverable: Previous re-opens the item the user came from.
  await page.locator('#view-previous').click();await page.locator('.viewer-surface img').evaluate(img=>img.decode());
  assert.equal(await page.locator('#view-position').textContent(),'This page · 1 / 2');
  await page.locator('#close-viewer').click();
  checkpoint('Closed, delayed, and failed sequence steps stop without repopulating or skipping items');
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
  await page.evaluate(()=>{const other=new BroadcastChannel('photohouse-session');other.postMessage('session-changed');setTimeout(()=>other.close(),100);window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  await pause(150);assert.equal(await page.locator('.asset').count(),0);
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
  // Run last: this grows family-a past one gallery page, which changes how many cards
  // and which page boundaries every earlier checkpoint sees.
  await mutate('many-assets');await page.locator('#refresh').click();
  await page.locator('.asset').first().waitFor();
  assert.equal(await page.locator('.asset').count(),24);
  assert.equal(await page.locator('#page-input').inputValue(),'1');
  assert.equal(await page.locator('#page-input').getAttribute('max'),'2');
  // Two independent refusals, neither of which may move the gallery: the input's own
  // min/max stops an out-of-range page before the form submits at all, and the submit
  // handler refuses a value that is not a page number if it is reached.
  await page.locator('#page-input').fill('9');
  await page.locator('#page-jump button[type="submit"]').click();
  assert.equal(await page.locator('#page-input').evaluate(input=>input.validity.rangeOverflow),true);
  assert.equal(await page.locator('.asset').count(),24);
  await page.locator('#page-input').fill('');
  await page.locator('#page-jump button[type="submit"]').click();
  assert.match(await page.locator('#status').textContent(),/between 1 and the last page/);
  assert.equal(await page.locator('.asset').count(),24);
  await page.locator('#page-input').fill('2');
  await page.locator('#page-jump button[type="submit"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.asset').length===7);
  assert.equal(await page.locator('#page-input').inputValue(),'2');
  assert.equal(await page.locator('#previous').isDisabled(),false);
  assert.equal(await page.locator('#next').isDisabled(),true);
  await page.screenshot({path:path.join(artifacts,'gallery-page-jump.png')});
  checkpoint('Gallery page jump accepts an in-range page and refuses an out-of-range one');
  // Run last for the same reason: it adds an unnamed cluster and a fresh unassigned
  // face, which changes directory counts and the worklist, and the owner session was
  // expired by an earlier checkpoint, so the owner signs in again here.
  await mutate('unnamed-cluster');
  // Checked only once the unnamed cluster exists, so "the member never sees an unnamed
  // cluster" is a real assertion instead of a vacuous one. The member view is narrower
  // than the owner's: a name and one thumbnail each, and no control that changes a name.
  // Absolute page-2 counts are avoided because earlier checkpoints create people.
  await page.locator('#directory-panel > summary').click();
  await page.locator('#directory-list .directory-card').first().waitFor();
  const firstCard=page.locator('#directory-list .directory-card').first();
  assert.equal(await firstCard.getAttribute('data-person-id'),'1');
  assert.match(await firstCard.locator('img').getAttribute('src'),/^\/faces\/1\/crop\?library=family-a$/);
  await firstCard.locator('img').evaluate(img=>img.decode());
  assert.equal(await page.locator('#directory-list .directory-card').count(),25);
  assert.equal(await page.locator('#directory-page-label').textContent(),'Page 1 of 2');
  const shownNames=await page.locator('#directory-list .directory-card .person-name').allTextContents();
  assert(shownNames.every(name=>name.length>0));
  assert(shownNames.some(name=>/^Person \d\d$/.test(name)));
  assert.equal(await page.locator('#directory-list .directory-card',{hasText:'Unnamed person'}).count(),0);
  // A name stored as markup stays text: the control that opens a person has no element
  // children, and no injected img[src=x] exists anywhere in the directory.
  assert.equal(await page.locator('#directory-list .person-name').evaluateAll(nodes=>nodes.every(node=>node.children.length===0)),true);
  assert.equal(await page.locator('#directory-list img[src="x"]').count(),0);
  // The owner surfaces stay hidden while a member reads the directory.
  assert.equal(await page.locator('#directory-list input').count(),0);
  assert.equal(await page.locator('#people-panel').isVisible(),false);
  assert.equal(await page.locator('#members-panel').isVisible(),false);
  await page.locator('#directory-next').click();
  await page.waitForFunction(()=>document.getElementById('directory-page-label').textContent==='Page 2 of 2');
  const lastPage=await page.locator('#directory-list .directory-card').count();
  assert(lastPage>=1&&lastPage<=24);
  assert.equal(await page.locator('#directory-next').isDisabled(),true);
  // An unnamed cluster would render as an empty heading, so a blank name on either page
  // is exactly the leak this checkpoint exists to catch.
  const lateNames=await page.locator('#directory-list .directory-card .person-name').allTextContents();
  assert(lateNames.every(name=>name.length>0));
  await page.screenshot({path:path.join(artifacts,'member-people-directory.png'),fullPage:true});
  // Opening one person's photos. The route is member-scoped and read-only, so the panel
  // gains a list and a pager and still no form and no owner control.
  await page.locator('#directory-list .directory-card .person-name').first().click();
  await page.locator('#person-assets .person-asset-card').first().waitFor();
  assert((await page.locator('#person-assets .person-asset-card').count())>=1);
  await page.locator('#person-assets .person-asset-card img').first().evaluate(img=>img.decode());
  assert.equal(await page.locator('#person-assets input').count(),0);
  assert.equal(await page.locator('#person-assets form').count(),0);
  // Closing the person leaves the directory exactly as it was.
  await page.locator('#person-assets h4 button').click();
  await page.waitForFunction(()=>document.querySelectorAll('#person-assets .person-asset-card').length===0);
  await page.locator('#directory-panel > summary').click();
  await page.locator('#directory-panel > summary').click();
  await page.locator('#directory-list .directory-card').first().waitFor();
  assert((await page.locator('#directory-list .directory-card').count())>=1);
  checkpoint('Member opens the photos of a person listed in the directory');
  await page.locator('#directory-panel > summary').click();
  checkpoint('Member browses the library people directory by name with thumbnails and no owner controls');
  // Read-only tag catalog. The panel is a sibling of the owner panels, so a member can open
  // it at all; the counts are this library's own visible photos and nothing else.
  await page.locator('#tags-panel > summary').click();
  await page.locator('#tag-list .tag-card').first().waitFor();
  assert.equal(await page.locator('#tags-panel').isVisible(),true);
  assert.equal(await page.locator('#tag-list .tag-card').count(),2);
  const tags=await page.locator('#tag-list .tag-card').allTextContents();
  assert(tags.some(text=>text.includes('beach')&&text.includes('2')));
  assert(tags.some(text=>text.includes('cake')&&text.includes('1')));
  // A tag whose photos belong to another library, and a tag only on a deleted photo, are
  // neither listed nor probeable: the server refuses them rather than answering empty.
  const catalogText=await page.locator('#tag-list').textContent();
  for(const hidden of ['foreign-only','deleted-only'])assert.equal(catalogText.includes(hidden),false);
  await page.locator('#tag-list .tag-card',{hasText:'beach'}).getByRole('button').click();
  await page.locator('#tag-assets .tag-asset-card').first().waitFor();
  assert.equal(await page.locator('#tag-assets .tag-asset-card').count(),2);
  await page.locator('#tag-assets .tag-asset-card img').first().evaluate(img=>img.decode());
  // Read-only by construction: the only input and the only form in the panel are the
  // search box and its submit, so there is no control that could add or remove a tag.
  assert.equal(await page.locator('#tags-panel input').count(),1);
  assert.equal(await page.locator('#tags-panel form').count(),1);
  assert.equal(await page.locator('#tag-assets input').count(),0);
  assert.equal(await page.locator('#tag-assets form').count(),0);
  assert.equal(await page.locator('#people-panel').isVisible(),false);
  await page.screenshot({path:path.join(artifacts,'member-tag-catalog.png'),fullPage:true});
  await page.locator('#tags-panel > summary').click();
  checkpoint('Member browses the read-only tag catalog and its photos without tag controls');
  // Exact duplicate groups. Read-only: the panel has no form and no control that could
  // delete, hide or merge a copy. The fixture gives 101 and 102 the same hash; 103 is
  // deleted and 201 belongs to family-b, so the group must contain exactly the two visible
  // family-a copies and the panel must not name a path, a filename or a hash.
  await page.locator('#duplicates-panel > summary').click();
  await page.locator('#duplicate-list .duplicate-group').first().waitFor();
  assert.equal(await page.locator('#duplicate-list .duplicate-group').count(),1);
  assert.equal(await page.locator('#duplicate-list .duplicate-copy').count(),2);
  const copyIds=await page.locator('#duplicate-list .duplicate-copy').evaluateAll(nodes=>nodes.map(n=>n.dataset.assetId));
  assert.deepEqual(copyIds.slice().sort(),['101','102']);
  await page.locator('#duplicate-list .duplicate-crop').first().evaluate(img=>img.decode());
  assert.equal(await page.locator('#duplicates-panel input').count(),0);
  assert.equal(await page.locator('#duplicates-panel form').count(),0);
  const duplicateText=await page.locator('#duplicates-panel').textContent();
  for(const leaked of ['private-synthetic','private-hash','dup-shared','.jpg'])assert.equal(duplicateText.includes(leaked),false);
  await page.screenshot({path:path.join(artifacts,'member-duplicates.png'),fullPage:true});
  await page.locator('#duplicates-panel > summary').click();
  checkpoint('Member sees photos saved twice, with no way to delete or merge a copy');
  // Date/media narrowing over the reviewed discovery index. The transport is mounted in
  // the default app but the index is an operator opt-in, so the panel is offered only
  // where one exists. This harness supplies one via the real producer. The artifact is a
  // whole-library snapshot, so refresh it first: earlier scenarios changed captions and
  // faces, which the snapshot covers, and a stale one is refused rather than answered.
  await mutate('refresh-discovery-index');
  // Reload rather than re-authenticate: the member's session survives, and the reload is
  // what makes the page re-probe availability against the rebuilt app.
  await page.goto('https://photohouse.test/ui');
  await page.locator('#library').waitFor({state:'visible'});
  await page.locator('#discovery-panel').waitFor({state:'visible'});
  assert.equal(await page.locator('#discovery-panel').isVisible(),true);
  await page.locator('#discovery-panel > summary').click();
  // Reviewed named places are offered from the locations facet, with their server
  // counts. Selecting one is read-only and joins the existing date/media filters.
  await page.locator('#discovery-place-list .place-choice').first().waitFor();
  assert.equal(await page.locator('#discovery-place-list .place-choice').count(),1);
  assert.match(await page.locator('#discovery-place-list .place-choice').first().textContent(),/Example region/);
  await page.locator('#discovery-place-list .place-choice').first().click();
  assert.equal(await page.locator('#discovery-place-list .place-choice').first().getAttribute('aria-pressed'),'true');
  await page.locator('#discovery-place-query').fill('nowhere');
  await page.locator('#discovery-place-search button').click();
  await page.waitForFunction(()=>document.getElementById('discovery-places-status').textContent.includes('No matching place'));
  assert.equal(await page.locator('#discovery-place-selected button').count(),1);
  await page.locator('#discovery-place-query').fill('EXAMPLELAND');
  await page.locator('#discovery-place-search button').click();
  await page.locator('#discovery-place-list .place-choice').first().waitFor();
  assert.equal(await page.locator('#discovery-place-list .place-choice').first().getAttribute('aria-pressed'),'true');
  const slowPlace=delayNext(url=>url.pathname.endsWith('/discovery/v1/facets')&&url.searchParams.get('q')==='nowhere');
  await page.locator('#discovery-place-query').fill('nowhere');
  await page.locator('#discovery-place-search button').click();await slowPlace.seen;
  await page.locator('#discovery-place-query').fill('测试地区');
  await page.locator('#discovery-place-search button').click();
  await page.locator('#discovery-place-list .place-choice').first().waitFor();
  slowPlace.release();await pause(120);
  assert.equal(await page.locator('#discovery-place-list .place-choice').count(),1);
  await page.locator('#discovery-place-selected button').click();
  assert.equal(await page.locator('#discovery-place-list .place-choice').first().getAttribute('aria-pressed'),'false');
  await page.locator('#discovery-place-list .place-choice').first().click();
  await page.locator('#discovery-panel').screenshot({path:path.join(artifacts,'bilingual-place-search-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#discovery-panel').screenshot({path:path.join(artifacts,'bilingual-place-search-phone.png')});
  await page.setViewportSize({width:1200,height:900});

  await page.locator('#discovery-media').selectOption('image');
  await page.locator('#discovery-from').fill('2026-01-01');
  await page.locator('#discovery-to').fill('2026-01-01');
  await page.locator('#discovery-form button[type="submit"]').click();
  await page.locator('#discovery-list .asset').first().waitFor();
  assert.equal(await page.locator('#discovery-list .asset').count(),1);
  await page.screenshot({path:path.join(artifacts,'member-place-filter.png'),fullPage:true});
  // Clearing filters cancels a pending result, even if its server response was
  // already computed. A late response must not repopulate the cleared panel.
  const oldDiscovery=delayNext(url=>url.pathname.endsWith('/discovery/v1/search'));
  await page.locator('#discovery-form button[type="submit"]').click();
  await oldDiscovery.seen;
  await page.locator('#discovery-clear').click();
  oldDiscovery.release();await pause(180);
  // Nothing is listed until a filter is chosen: the panel narrows, it does not duplicate
  // the gallery below it.
  assert.equal(await page.locator('#discovery-list .asset').count(),0);
  assert((await page.locator('#discovery-status').textContent()).length>0);
  // Media narrowing. Every visible family-a photo is an image, so photos match and
  // videos do not; the video case is the load-bearing one, because it can only return
  // zero if the filter actually reached the server rather than the client showing
  // everything. The library is already past one page here, because the page-jump
  // checkpoint grew it, so the photo case also exercises bounded pagination.
  await page.locator('#discovery-media').selectOption('image');
  await page.locator('#discovery-form button[type="submit"]').click();
  await page.locator('#discovery-list .asset').first().waitFor();
  assert.equal(await page.locator('#discovery-list .asset').count(),24);
  await page.locator('#discovery-list img').first().evaluate(img=>img.decode());
  await page.locator('#discovery-list').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'discovery-grid-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#discovery-list').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'discovery-grid-phone.png')});
  await page.setViewportSize({width:1200,height:900});
  await page.locator('#discovery-list .asset').first().click();
  await page.locator('#viewer-media img').evaluate(img=>img.decode());
  assert.match(await page.locator('#view-position').textContent(),/1 \/ 24/);
  await page.locator('#view-next').click();
  await page.waitForFunction(()=>document.getElementById('view-position').textContent.includes('2 / 24'));
  await page.locator('#viewer-media img').evaluate(img=>img.decode());
  await page.locator('#close-viewer').click();


  assert.equal(await page.locator('#discovery-pages').isVisible(),true);
  // Editing the draft without Apply must not change the query/fingerprint
  // paginated by Next. This remains the second page of images.
  await page.locator('#discovery-media').selectOption('video');
  await page.locator('#discovery-next').click();
  await page.waitForFunction(()=>document.getElementById('discovery-page-label').textContent==='2 / 2');
  assert(await page.locator('#discovery-list .asset').count()>0);
  await page.locator('#discovery-list .asset img').first().evaluate(img=>img.decode());
  await page.locator('#discovery-media').selectOption('video');
  // Wait on the response itself, not on a DOM state: the list is cleared and the status
  // set to the loading text before the request goes out, so an empty list or a non-empty
  // status are both also true mid-flight and would pass even if the filter were ignored.
  const videoSearch=page.waitForResponse(response=>response.url().includes('/discovery/v1/search'));
  await page.locator('#discovery-form button[type="submit"]').click();
  await videoSearch;
  await pause(120);
  assert.equal(await page.locator('#discovery-list .asset').count(),0);
  assert.equal(await page.locator('#discovery-pages').isVisible(),false);
  // Date narrowing, bounded by what the facets route reported as the captured range. Only
  // asset 102 was captured on or after this date, so this is a single-row answer.
  await page.locator('#discovery-media').selectOption('all');
  await page.locator('#discovery-from').fill('2026-01-02');
  await page.locator('#discovery-form button[type="submit"]').click();
  await page.locator('#discovery-list .asset').first().waitFor();
  assert.equal(await page.locator('#discovery-list .asset').count(),1);
  assert.equal(await page.locator('#discovery-list .asset').getAttribute('data-asset-id'),'102');
  // A date outside the reported captured range is refused before any request: the native
  // bounds carry the first refusal, and the previous result set is left untouched rather
  // than replaced by an empty or unfiltered one.
  await page.locator('#discovery-from').fill('2026-01-03');
  await page.locator('#discovery-form button[type="submit"]').click();
  await pause(150);
  assert.equal(await page.locator('#discovery-list .asset').count(),1);
  assert.equal(await page.locator('#discovery-list .asset').getAttribute('data-asset-id'),'102');
  // Read-only by construction: one form, one select, and nothing that could write.
  assert.equal(await page.locator('#discovery-panel form').count(),2);
  assert.equal(await page.locator('#discovery-panel select').count(),1);
  assert.equal(await page.locator('#discovery-panel input[type="file"]').count(),0);
  assert.equal(await page.locator('#people-panel').isVisible(),false);
  await page.screenshot({path:path.join(artifacts,'member-discovery-filter.png'),fullPage:true});
  await page.locator('#discovery-panel > summary').click();
  checkpoint('Member combines named places/date/media; paging freezes applied filters and Clear rejects late results');
  await auth(owner,'+12025550100');
  await owner.locator('#people-panel > summary').click();
  await owner.locator('.person-card').first().waitFor();
  // 'all' is the default, so an unnamed cluster is included without asking for it.
  assert.equal(await owner.locator('.person-card h3',{hasText:'Unnamed person 50'}).count(),1);
  await owner.locator('#people-named').selectOption('unnamed');
  await owner.waitForFunction(()=>document.getElementById('people-page-label').textContent==='Page 1 of 1');
  assert.equal(await owner.locator('.person-card').count(),1);
  assert.equal(await owner.locator('.person-card h3').textContent(),'Unnamed person 50');
  await owner.locator('#people-named').selectOption('named');
  await owner.waitForFunction(()=>document.querySelectorAll('.person-card').length===25);
  assert.equal(await owner.locator('.person-card h3',{hasText:'Unnamed person'}).count(),0);
  await owner.locator('#people-next').click();
  await owner.waitForFunction(()=>document.getElementById('people-page-label').textContent==='Page 2 of 2');
  const namedLastPage=await owner.locator('.person-card').count();
  // The filter narrows, it does not mask: 'all' adds the unnamed cluster and nothing
  // else. Absolute counts are deliberately avoided because earlier checkpoints create
  // people of their own.
  await owner.locator('#people-named').selectOption('all');
  await owner.waitForFunction(()=>document.getElementById('people-page-label').textContent==='Page 1 of 2');
  await owner.locator('#people-next').click();
  await owner.waitForFunction(()=>document.getElementById('people-page-label').textContent==='Page 2 of 2');
  assert.equal(await owner.locator('.person-card').count(),namedLastPage+1);
  checkpoint('Owner directory separates named people from unnamed clusters');
  await owner.locator('#unassigned-section summary').click();
  await owner.locator('.unassigned-card').first().waitFor();
  assert.equal(await owner.locator('.unassigned-card').count(),1);
  assert.equal(await owner.locator('.unassigned-card h4').textContent(),'Unassigned · Photo 102');
  await owner.locator('.unassigned-card img').evaluate(img=>img.decode());
  // The nav follows the directory's own convention: it is hidden only when there is
  // nothing to page through, so a single row still reports its one page.
  assert.equal(await owner.locator('#unassigned-page-label').textContent(),'Page 1 of 1');
  // The worklist row carries a live revision, so it is actionable in place.
  await owner.locator('.unassigned-card').getByRole('button',{name:'Choose a person',exact:true}).click();
  const worklistPicker=owner.locator('#unassigned-list .face-picker');
  await worklistPicker.locator('input').fill('Person 10');
  await worklistPicker.locator('form button').click();
  await worklistPicker.locator('.person-choice').filter({hasText:'Person 10 · 10'}).click();
  await worklistPicker.getByRole('button',{name:'Confirm assignment',exact:true}).click();
  await owner.waitForFunction(()=>document.getElementById('unassigned-status').textContent.startsWith('Assignment saved'));
  await owner.waitForFunction(()=>document.querySelectorAll('.unassigned-card').length===0);
  await owner.locator('#unassigned-section summary').click();
  checkpoint('Owner works the unassigned-face list and assigns without leaving it');
  await mutate('missing-caption');
  await owner.locator('#refresh').click();
  await owner.locator('.asset').filter({hasText:'104'}).waitFor();
  await owner.locator('.asset').filter({hasText:'104'}).click();
  if(await owner.locator('.ai-descriptions').getAttribute('open')===null)
    await owner.locator('.ai-descriptions > summary').click();
  await owner.locator('#captions form').waitFor();
  await owner.locator('#caption-text').fill('Grandma at the beach');
  await owner.locator('#captions form').getByRole('button',{name:'Save description',exact:true}).click();
  await owner.waitForFunction(()=>document.querySelector('#captions p[role="status"]')?.textContent==='Saved. Thank you.');
  assert.equal(await owner.locator('#captions form').count(),0);
  assert.equal(await owner.locator('#captions p').filter({hasText:'No description is available yet.'}).count(),0);
  assert.equal(await owner.locator('#captions p').filter({hasText:'Grandma at the beach'}).textContent(),'Grandma at the beach');
  await owner.locator('#captions').screenshot({path:path.join(artifacts,'saved-caption.png')});
  await owner.locator('#close-viewer').click();
  checkpoint('Member can fill an absent caption and the saved text is rendered after the write');
  await mutate('prepared-video-unavailable');
  await owner.locator('#refresh').click();
  await owner.locator('.asset').filter({hasText:'105'}).waitFor();
  const videoRequestsStart=browserRequests.length;
  await owner.locator('.asset').filter({hasText:'105'}).click();
  await owner.waitForFunction(()=>document.getElementById('view-quality').textContent.includes('unavailable'));
  assert.equal(await owner.locator('#viewer-media video').count(),0);
  assert.equal(await owner.locator('#viewer-media').getByRole('button',{name:'Retry video',exact:true}).count(),1);
  const videoRequests=browserRequests.slice(videoRequestsStart);
  assert(videoRequests.some(item=>item.method==='HEAD'&&item.path==='/assets/105/playback?library=family-a'));
  assert(!videoRequests.some(item=>item.method==='GET'&&item.path.includes('/assets/105/media')));
  await owner.screenshot({path:path.join(artifacts,'prepared-video-unavailable.png'),fullPage:true});
  await owner.locator('#close-viewer').click();
  const delayedVideo=delayNext(url=>url.pathname==='/assets/105/playback');
  await owner.locator('.asset').filter({hasText:'105'}).click();await delayedVideo.seen;
  await owner.locator('#close-viewer').click();delayedVideo.release();await pause(150);
  assert.equal(await owner.locator('#viewer-media video').count(),0);
  assert.equal(await owner.locator('#viewer').isVisible(),false);
  checkpoint('Prepared video performs protected HEAD readiness, shows unavailable without original fallback, and cannot reappear after close');
  // The same viewer path stays bounded when the readiness HEAD is offline: an
  // explicit retry can fail again without an unhandled promise or stale DOM write.
  failNextPath='/assets/105/playback';
  await owner.locator('.asset').filter({hasText:'105'}).click();
  await owner.locator('#viewer-media').getByRole('button',{name:'Retry video',exact:true}).waitFor();
  failNextPath='/assets/105/playback';
  await owner.locator('#viewer-media').getByRole('button',{name:'Retry video',exact:true}).click();
  await owner.locator('#viewer-media').getByRole('button',{name:'Retry video',exact:true}).waitFor();
  await owner.locator('#close-viewer').click();
  checkpoint('Initial and repeated offline playback retries remain explicit, bounded, and page-error free');
  await mutate('prepared-video-ready');
  await owner.locator('#refresh').click();await owner.locator('.asset').filter({hasText:'105'}).click();
  const video=owner.locator('#viewer-media video');await video.waitFor();
  await owner.waitForFunction(()=>document.querySelector('#viewer-media video')?.readyState>=1);
  await video.evaluate(async element=>{element.muted=true;await element.play();});
  await owner.waitForFunction(()=>document.querySelector('#viewer-media video')?.currentTime>0);
  const duration=await video.evaluate(element=>element.duration);assert(duration>0);
  const seekTarget=Math.max(0.05,duration/2);
  await video.evaluate((element,target)=>new Promise(resolve=>{const finish=()=>resolve();if(Math.abs(target-element.currentTime)<0.02)finish();else element.addEventListener('seeked',finish,{once:true});element.currentTime=target;}),seekTarget);
  assert(Math.abs(await video.evaluate(element=>element.currentTime)-seekTarget)<0.2);
  const playbackRequests=browserRequests.slice(videoRequestsStart);
  assert(playbackRequests.some(item=>item.method==='HEAD'&&item.path==='/assets/105/playback?library=family-a'));
  assert(playbackRequests.some(item=>item.method==='GET'&&item.path==='/assets/105/playback?library=family-a'));
  await owner.screenshot({path:path.join(artifacts,'prepared-video-playing.png'),fullPage:true});
  await owner.locator('#close-viewer').click();
  checkpoint('Prepared video passes HEAD metadata validation, native decode/play, and seek against synthetic MP4');
  failNextPlaybackGet=true;await owner.locator('.asset').filter({hasText:'105'}).click();
  await owner.locator('#viewer-media').getByRole('button',{name:'Retry video',exact:true}).waitFor();
  assert.equal(await owner.locator('#viewer-media video').count(),0);await owner.locator('#close-viewer').click();
  checkpoint('Native playback failure releases the video source and offers a fresh retry');
  const expectPlaybackError=async(status,headers,text)=>{
    playbackOverrides.push({status,headers});
    await owner.locator('.asset').filter({hasText:'105'}).click();
    if(status===401||status===403){await owner.locator('#viewer').waitFor({state:'hidden'});await owner.locator('#library').waitFor({state:'visible'});await owner.locator('#refresh').click();await owner.locator('.asset').first().waitFor();return;}
    await owner.waitForFunction(value=>document.getElementById('view-quality').textContent.includes(value),text);
    assert.equal(await owner.locator('#viewer-media video').count(),0);
    await owner.locator('#close-viewer').click();
  };
  await expectPlaybackError(404,{},'not prepared');
  await expectPlaybackError(409,{},'changed');
  playbackOverrides.push({status:429,headers:{'Retry-After':'1'}});await owner.locator('.asset').filter({hasText:'105'}).click();
  const retryButton=owner.locator('#viewer-media').getByRole('button',{name:'Retry video',exact:true});await retryButton.waitFor();assert.equal(await retryButton.isDisabled(),true);await owner.waitForTimeout(1100);assert.equal(await retryButton.isDisabled(),false);await owner.locator('#close-viewer').click();
  playbackOverrides.push({status:429,headers:{'Retry-After':new Date(Date.now()+3000).toUTCString()}});await owner.locator('.asset').filter({hasText:'105'}).click();
  const dateRetry=owner.locator('#viewer-media').getByRole('button',{name:'Retry video',exact:true});await dateRetry.waitFor();assert.equal(await dateRetry.isDisabled(),true);await owner.waitForTimeout(3100);assert.equal(await dateRetry.isDisabled(),false);await owner.locator('#close-viewer').click();
  playbackOverrides.push({status:200,headers:{'content-type':'text/plain'}});await owner.locator('.asset').filter({hasText:'105'}).click();await owner.waitForFunction(()=>document.getElementById('view-quality').textContent.includes('unavailable'));assert.equal(await owner.locator('#viewer-media video').count(),0);await owner.locator('#close-viewer').click();
  await expectPlaybackError(403,{},'');
  checkpoint('Prepared playback rejects 404, 409, 429 seconds/date waits, malformed success metadata, and 403 without fallback');
  await mutate('library-organization');
  await owner.locator('#refresh').click();await owner.locator('[data-transfer-id="9501"]').waitFor();
  assert.equal(await owner.locator('#library-select option[value="documents"]').textContent(),'Documents');
  await owner.locator('[data-transfer-id="9501"]').check();await owner.locator('[data-transfer-id="9502"]').check();
  assert.equal(await owner.locator('#viewer').evaluate(el=>el.open),false);
  await owner.locator('#transfer-move').click();await owner.waitForFunction(()=>!document.getElementById('transfer-review-confirm').disabled);
  const oldReview=delayNext(url=>url.pathname==='/admin/library-transfers/review');
  await owner.locator('#transfer-destination').selectOption('scenery');await oldReview.seen;
  await owner.locator('#transfer-destination').selectOption('documents');
  await owner.waitForFunction(()=>!document.getElementById('transfer-review-confirm').disabled);
  oldReview.release();await pause(50);
  assert((await owner.locator('#transfer-review-summary').textContent()).includes('Documents'));
  await owner.screenshot({path:path.join(artifacts,'library-move-review.png'),fullPage:true});
  failNextMoveRefreshPath='/assets';
  await owner.locator('#transfer-review-confirm').click();await owner.locator('#transfer-review').waitFor({state:'hidden'});
  await owner.waitForFunction(()=>document.getElementById('transfer-status').textContent.includes('completed'));
  assert(!((await owner.locator('#transfer-status').textContent()).includes('could not be completed')));
  await owner.locator('#refresh').click();await owner.locator('.asset').first().waitFor();
  assert.equal(await owner.locator('#grid [data-asset-id="9501"]').count(),0);
  await owner.locator('#library-select').selectOption('documents');await owner.locator('#grid [data-asset-id="9501"]').waitFor();
  assert.equal(await owner.locator('#grid [data-asset-id="9502"]').count(),1);
  await owner.locator('#language').click();await owner.waitForFunction(()=>document.querySelector('#library-select option[value="documents"]').textContent==='文档');
  await owner.setViewportSize({width:390,height:844});await owner.screenshot({path:path.join(artifacts,'library-move-phone-zh.png'),fullPage:true});
  assert(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  checkpoint('Admin moves selected photo/video to the reviewed destination; late reviews cannot replace a newer choice; bilingual catalogue fits phone');
  await mutate('family-default');
  await owner.locator('#refresh').click();
  await owner.waitForFunction(()=>document.querySelector('#library-select option')?.value==='family');
  assert.equal(await owner.locator('#library-select').inputValue(),'documents');
  checkpoint('Family is first in the picker; refreshing keeps a manually selected library');
  await owner.reload();await owner.locator('#grid [data-asset-id="9601"]').waitFor();
  assert.equal(await owner.locator('#library-select').inputValue(),'family');
  await owner.locator('#language').click();
  await owner.screenshot({path:path.join(artifacts,'family-default-phone-zh.png'),fullPage:true});
  await owner.locator('#language').click();
  assert.equal(await owner.locator('#library-select').inputValue(),'family');
  await owner.setViewportSize({width:1200,height:900});
  await owner.screenshot({path:path.join(artifacts,'family-default-desktop-en.png'),fullPage:true});
  await owner.locator('#library-select').selectOption('documents');await owner.locator('#grid [data-asset-id="9501"]').waitFor();
  await owner.locator('#refresh').click();await owner.locator('#grid [data-asset-id="9501"]').waitFor();
  assert.equal(await owner.locator('#library-select').inputValue(),'documents');
  await owner.locator('#logout').click();await owner.locator('#auth').waitFor({state:'visible'});
  await auth(owner,'+12025550100');
  assert.equal(await owner.locator('#library-select').inputValue(),'family');
  checkpoint('Cold restore and new login load Family despite alphabetically earlier libraries; bilingual manual switching remains available');
  await mutate('family-default-unavailable');
  const fallbackStart=browserRequests.length;
  await owner.locator('#refresh').click();await owner.waitForFunction(()=>document.getElementById('library-select').value==='chuan-work');
  await owner.locator('#empty').waitFor({state:'visible'});
  assert(!browserRequests.slice(fallbackStart).some(item=>item.path.startsWith('/assets?')&&new URL(item.path,'https://photohouse.test').searchParams.get('library')==='family'));
  assert.equal(await owner.locator('#library-select option[value="family"]').count(),0);
  await mutate('family-default-no-access');
  const noAccessStart=browserRequests.length;
  await owner.locator('#refresh').click();await owner.waitForFunction(()=>document.getElementById('library-select').options.length===0);
  assert.equal(await owner.locator('#grid .asset').count(),0);
  assert(!browserRequests.slice(noAccessStart).some(item=>item.path.startsWith('/assets?')));
  checkpoint('Unavailable Family falls back to an accessible library; no memberships means no media requests');
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checks,externalRequests:external,pageErrors:errors,browser:browser.version(),syntheticFetchMetadataRequests:syntheticFetchMetadata,transportLimitation:'DevTools interception omits Fetch Metadata here; same-origin signals are explicitly modeled from the requesting frame. Real network header emission and CORP enforcement remain unverified.',evidence:'Chromium rendered; all HTTP fulfilled via stdin/stdout ASGI bridge and explicit ExistingDatabase adapter; synthetic migrated SQLite/JPEG/MP4 only'},null,2));
  console.log(`Browser checks: ${checks.length} passed. Artifacts: ${artifacts}`);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(hold){hold=null;}
  if(browser)await browser.close();bridge.stdin.end(JSON.stringify({command:'quit'})+'\n');
});
