'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {language:'en', mode:'login', generation:0, controllers:new Set(), profile:null,
    csrf:null, library:null, viewerGeneration:0, page:1, busy:false, locked:false, invite:null, total:0};
  const words = {
    en: {tagline:'A place for our memories',eyebrow:'YOUR FAMILY, TOGETHER',welcome:'The moments we keep close.',intro:'A private home for family photos. Sign in, or join with the invitation your library owner sent you.',signIn:'Sign in',join:'Join with an invitation',phone:'Phone number',phoneHelp:'Include the country code. Your phone number is your sign-in name.',password:'Password',passwordHelp:'Choose a passphrase of 15–128 characters.',invitation:'Invitation code',inviteHelp:'Use the code sent for this phone number. An accepted invitation opens that library.',help:'Need an invitation or help signing in? Contact your library owner.',yourLibrary:'YOUR FAMILY LIBRARY',gallery:'Little moments. Lasting memories.',signOut:'Sign out',libraryLabel:'Library',refresh:'Refresh',previous:'Previous',next:'Next',anotherInvite:'Have an invitation to another library?',accept:'Accept invitation',inviteSomeone:'Invite someone to this library',ownerHelp:'Create a code for their phone number, then send it privately. They join as a viewer. Original downloads are not included.',createInvite:'Create invitation',sendCode:'Send this code privately. It expires in 24 hours.',cancelInvite:'Cancel this invitation',close:'Close',download:'Download original',captionNote:'Generated descriptions may be inaccurate. Original downloads require separate permission.',footer:'PhotoHouse · Shared by invitation',checking:'Checking your session…',loading:'Loading your library…',denied:'Access could not be confirmed. Check your details or contact your library owner.',unavailable:'PhotoHouse is unavailable. Please try again later.',limited:'Too many attempts. Please wait before trying again.',changed:'Your access changed. Refresh or contact your library owner.',noLibrary:'No library is currently available. Ask your owner for an invitation.',noPhotos:'No photos are available in this library yet.',signedOut:'You are signed out.',logoutFailed:'Sign out could not be completed. Your photos are hidden; try Sign out again.',accepted:'Invitation accepted.',cancelled:'Invitation cancelled.',noCaptions:'No description is available yet.',edited:'Family description',generated:'Generated description',moreCaptions:'Only the first 20 descriptions are shown.',truncated:'Description shortened.',photo:'Photo',video:'Video',other:'Media',previewMissing:'Preview unavailable',working:'Please wait…',invalidPhone:'Include an explicit country code, for example +86.',invalidPassword:'Choose a passphrase of 15–128 characters.',page:'Page',of:'of',photos:'items'},
    zh: {tagline:'珍藏一家人的时光',eyebrow:'属于我们一家人的回忆',welcome:'把美好时光，留在身边。',intro:'一个私密的家庭相册。登录，或使用相册主人发给你的邀请码加入。',signIn:'登录',join:'使用邀请码加入',phone:'手机号码',phoneHelp:'请包含国家区号。手机号码用作登录名。',password:'密码',passwordHelp:'请设置 15–128 个字符的密码或短语。',invitation:'邀请码',inviteHelp:'请使用为此手机号码生成的邀请码。验证成功后即可访问对应相册。',help:'需要邀请码或登录帮助？请联系相册主人。',yourLibrary:'我们的家庭相册',gallery:'小小瞬间，长长回忆。',signOut:'退出登录',libraryLabel:'相册库',refresh:'刷新',previous:'上一页',next:'下一页',anotherInvite:'收到另一个相册库的邀请码？',accept:'接受邀请',inviteSomeone:'邀请家人加入这个相册库',ownerHelp:'为对方的手机号码生成邀请码，再私下发送。对方将以浏览者身份加入，不包含原文件下载权限。',createInvite:'生成邀请码',sendCode:'请私下发送此邀请码，有效期为 24 小时。',cancelInvite:'取消此邀请',close:'关闭',download:'下载原文件',captionNote:'自动生成的描述可能不准确。下载原文件需要单独授权。',footer:'PhotoHouse · 受邀共享的家庭相册',checking:'正在检查登录状态…',loading:'正在加载相册…',denied:'暂时无法确认访问权限。请检查信息或联系相册主人。',unavailable:'PhotoHouse 暂时不可用，请稍后重试。',limited:'尝试次数过多，请稍后再试。',changed:'访问权限已发生变化，请刷新或联系相册主人。',noLibrary:'目前没有可访问的相册库，请向相册主人索取邀请。',noPhotos:'这个相册库暂时没有可浏览的照片。',signedOut:'已退出登录。',logoutFailed:'暂时未能完成退出。照片已隐藏，请再次点击退出登录。',accepted:'已接受邀请。',cancelled:'已取消邀请。',noCaptions:'暂时没有描述。',edited:'家人描述',generated:'自动生成的描述',moreCaptions:'仅显示前 20 条描述。',truncated:'描述已缩短。',photo:'照片',video:'视频',other:'媒体',previewMissing:'预览暂不可用',working:'请稍候…',invalidPhone:'请包含国家区号，例如 +86。',invalidPassword:'请设置 15–128 个字符的密码或短语。',page:'第',of:'/',photos:'项'}
  };
  const t = key => words[state.language][key] || key;
  let statusKey = '';
  function status(key) { statusKey = key; $('status').textContent = key ? t(key) : ''; }
  function translate() {
    document.documentElement.lang = state.language === 'zh' ? 'zh-CN' : 'en';
    document.querySelectorAll('[data-i18n]').forEach(node => {node.textContent=t(node.dataset.i18n);});
    $('language').textContent = state.language === 'en' ? '中文' : 'English';
    $('auth-submit').textContent=t(state.busy?'working':state.mode==='login'?'signIn':'join');
    status(statusKey);
  }
  function closeViewer() {
    state.viewerGeneration++;
    if ($('viewer').open) $('viewer').close();
    $('viewer-media').querySelectorAll('video').forEach(video => {video.pause();video.removeAttribute('src');video.load();});
    $('viewer-media').replaceChildren(); $('captions').replaceChildren(); $('viewer-title').textContent='';
    $('original').removeAttribute('href'); $('original').hidden=true;
  }
  function clearPhotos() {
    closeViewer(); $('grid').replaceChildren(); $('pagination').hidden=true; $('empty').hidden=true;
    $('created-code').value=''; $('invitation-result').hidden=true; state.invite=null;
    $('accept-code').value=''; $('invite-phone').value='';
  }
  function invalidate() {
    state.generation++;
    for (const controller of state.controllers) controller.abort();
    state.controllers.clear(); clearPhotos();
    return state.generation;
  }
  function stale(epoch) {return epoch !== state.generation;}
  async function request(path, {method='GET',body,epoch=state.generation}={}) {
    const controller=new AbortController(); state.controllers.add(controller);
    const headers={Accept:'application/json'};
    if (body !== undefined) headers['Content-Type']='application/json';
    if (method!=='GET' && state.csrf) headers['X-CSRF-Token']=state.csrf;
    try {
      const response=await fetch(path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),
        credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      if(stale(epoch)) throw new DOMException('Stale request','AbortError');
      if(!response.ok) {const error=new Error('Request failed');error.status=response.status;throw error;}
      const result=await response.json();
      if(stale(epoch)) throw new DOMException('Stale request','AbortError');
      return result;
    } finally {state.controllers.delete(controller);}
  }
  function showAuth() {
    state.profile=null;state.csrf=null;state.library=null;state.locked=false;
    $('account-label').textContent='';$('library-select').replaceChildren();$('owner-panel').hidden=true;
    $('library').hidden=true;$('auth').hidden=false;$('password').value='';$('code').value='';
  }
  function errorStatus(error) {return error.status===429?'limited':error.status===401||error.status===403?'denied':'unavailable';}
  async function failure(error,epoch) {
    if(error.name==='AbortError'||stale(epoch))return;
    if(error.status===401||error.status===403) {
      invalidate(); status('changed');
      await restore(false);
    } else {status(errorStatus(error));}
  }
  function libraryPath(path,extra={}) {return path+'?'+new URLSearchParams({library:state.library,...extra});}
  function assetLabel(item) {return `${t(item.kind==='image'?'photo':item.kind)} ${item.id}${item.taken_at?' · '+String(item.taken_at).slice(0,10):''}`;}
  function safeMediaURL(id,variant,extra={}) {return libraryPath(`/assets/${id}/${variant}`,extra);}
  async function openAsset(item) {
    if(state.locked)return;
    const epoch=state.generation;
    closeViewer(); const viewerGeneration=state.viewerGeneration; $('viewer').showModal(); $('viewer-title').textContent=assetLabel(item);
    try {
      const detail=await request(libraryPath(`/assets/detail/${item.id}`),{epoch});
      const captions=await request(libraryPath(`/assets/${item.id}/captions`),{epoch});
      if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
      const image=document.createElement('img');image.alt=assetLabel(item);image.src=safeMediaURL(item.id,'thumbnail');
      $('viewer-media').append(image);
      if(detail.originals_allowed) { $('original').href=safeMediaURL(item.id,'media',{download:'true'});$('original').hidden=false; }
      if(!captions.items.length) {const p=document.createElement('p');p.textContent=t('noCaptions');$('captions').append(p);}
      for(const caption of captions.items) {
        const label=document.createElement('small');label.textContent=t(caption.user_edited?'edited':'generated');
        const p=document.createElement('p');p.textContent=caption.text;
        $('captions').append(label,p);
        if(caption.truncated) {const small=document.createElement('small');small.textContent=t('truncated');$('captions').append(small);}
      }
      if(captions.has_more) {const p=document.createElement('p');p.textContent=t('moreCaptions');$('captions').append(p);}
    } catch(error) {await failure(error,epoch);}
  }
  async function loadGallery() {
    if(!state.library||state.locked)return;
    const epoch=invalidate();status('loading');
    try {
      const result=await request(libraryPath('/assets',{page:String(state.page),page_size:'24'}),{epoch});
      if(stale(epoch))return;
      state.total=result.total;
      for(const item of result.items) {
        const card=document.createElement('button');card.type='button';card.className='asset';
        const image=document.createElement('img');image.loading='lazy';image.alt=assetLabel(item);
        image.src=safeMediaURL(item.id,'thumbnail');
        image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
        const label=document.createElement('span');label.textContent=assetLabel(item);card.append(image,label);
        card.addEventListener('click',()=>{void openAsset(item);});$('grid').append(card);
      }
      $('empty').hidden=result.items.length>0;$('empty').textContent=t('noPhotos');
      const pages=Math.max(1,Math.ceil(result.total/24));
      $('pagination').hidden=result.total===0;$('previous').disabled=state.page===1;$('next').disabled=state.page>=pages;
      $('page-label').textContent=`${t('page')} ${state.page} ${t('of')} ${pages} · ${result.total} ${t('photos')}`;
      status('');
    } catch(error) {await failure(error,epoch);}
  }
  async function restore(load=true) {
    const epoch=invalidate();
    try {
      const profile=await request('/auth/session',{epoch});
      if(stale(epoch))return;
      state.profile=profile;state.csrf=profile.csrf_token;state.locked=false;
      $('auth').hidden=true;$('library').hidden=false;$('account-label').textContent=profile.phone_login;
      const available=profile.memberships.filter(m=>m.available===true);
      if(!available.some(m=>m.library_id===state.library)) state.library=available[0]?.library_id||null;
      $('library-select').replaceChildren();
      for(const member of available) {const option=document.createElement('option');option.value=member.library_id;option.textContent=member.library_id;$('library-select').append(option);}
      $('library-select').value=state.library||'';
      $('owner-panel').hidden=!available.some(m=>m.library_id===state.library&&m.role==='owner');
      if(!state.library) {$('empty').hidden=false;$('empty').textContent=t('noLibrary');status('');}
      else if(load) await loadGallery();
    } catch(error) {
      if(error.name==='AbortError'||stale(epoch))return;
      if(error.status===401) {showAuth();status('');}
      else {showAuth();status(errorStatus(error));}
    }
  }
  function setMode(mode) {
    if(state.busy)return;state.mode=mode;
    $('login-tab').setAttribute('aria-pressed',String(mode==='login'));
    $('register-tab').setAttribute('aria-pressed',String(mode==='register'));
    $('registration-fields').hidden=mode!=='register';$('code').required=mode==='register';
    $('password').autocomplete=mode==='register'?'new-password':'current-password';
    $('password').minLength=mode==='register'?15:1;$('password').value='';$('code').value='';translate();
  }
  async function signIn(event) {
    event.preventDefault();if(state.busy)return;
    const phone=$('phone').value,password=$('password').value;
    if(!/^\+[1-9][0-9]{7,14}$/.test(phone.replace(/[ ()-]/g,''))) {status('invalidPhone');return;}
    if(state.mode==='register'&&(Array.from(password).length<15||Array.from(password).length>128)){status('invalidPassword');return;}
    state.busy=true;$('auth-submit').disabled=true;translate();const epoch=invalidate();
    const body={phone,password,transport:'web'};if(state.mode==='register')body.code=$('code').value;
    try {
      await request('/auth/'+state.mode,{method:'POST',body,epoch});
      if(!stale(epoch)) {$('password').value='';$('code').value='';await restore();}
    } catch(error) {if(error.name!=='AbortError'&&!stale(epoch))status(errorStatus(error));}
    finally {state.busy=false;$('auth-submit').disabled=false;translate();}
  }
  async function signOut() {
    if(state.busy)return;state.busy=true;state.locked=true;const epoch=invalidate();status('working');
    try {
      await request('/auth/logout',{method:'POST',epoch});
      if(!stale(epoch)){showAuth();status('signedOut');channel?.postMessage('session-changed');}
    } catch(error) {if(error.name!=='AbortError'&&!stale(epoch))status('logoutFailed');}
    finally {state.busy=false;}
  }
  async function invite(event) {
    event.preventDefault();if(state.busy||state.locked)return;state.busy=true;const epoch=state.generation;
    const library=state.library;
    try {
      const result=await request(`/libraries/${encodeURIComponent(library)}/invitations`,{method:'POST',body:{phone:$('invite-phone').value},epoch});
      state.invite={code:result.code,library};$('created-code').value=result.code;$('invitation-result').hidden=false;status('');
    } catch(error){await failure(error,epoch);}finally{state.busy=false;}
  }
  async function cancelInvite() {
    if(state.busy||state.locked||!state.invite)return;state.busy=true;const epoch=state.generation;
    try {
      await request(`/libraries/${encodeURIComponent(state.invite.library)}/invitations/cancel`,{method:'POST',body:{code:state.invite.code},epoch});
      $('created-code').value='';$('invitation-result').hidden=true;state.invite=null;status('cancelled');
    } catch(error){await failure(error,epoch);}finally{state.busy=false;}
  }
  async function accept(event) {
    event.preventDefault();if(state.busy||state.locked)return;state.busy=true;const epoch=state.generation;
    try {await request('/auth/invitations/accept',{method:'POST',body:{code:$('accept-code').value},epoch});await restore();status('accepted');}
    catch(error){await failure(error,epoch);}finally{state.busy=false;}
  }
  const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('photohouse-session'):null;
  if(channel)channel.onmessage=()=>{if(!state.locked&&!state.busy)void restore();};
  $('auth-form').addEventListener('submit',event=>{void signIn(event);});
  $('login-tab').addEventListener('click',()=>setMode('login'));
  $('register-tab').addEventListener('click',()=>setMode('register'));
  $('logout').addEventListener('click',()=>{void signOut();});
  $('refresh').addEventListener('click',()=>{if(!state.locked){state.page=1;void restore();}});
  $('library-select').addEventListener('change',()=>{if(state.locked)return;state.library=$('library-select').value;state.page=1;void restore();});
  $('previous').addEventListener('click',()=>{if(state.page>1){state.page--;void loadGallery();}});
  $('next').addEventListener('click',()=>{if(state.page*24<state.total){state.page++;void loadGallery();}});
  $('close-viewer').addEventListener('click',closeViewer);
  $('viewer').addEventListener('cancel',event=>{event.preventDefault();closeViewer();});
  $('invite-form').addEventListener('submit',event=>{void invite(event);});
  $('cancel-invite').addEventListener('click',()=>{void cancelInvite();});
  $('accept-form').addEventListener('submit',event=>{void accept(event);});
  $('language').addEventListener('click',()=>{state.language=state.language==='en'?'zh':'en';translate();if(state.profile&&!state.locked)void restore();});
  window.addEventListener('pagehide',()=>{invalidate();$('password').value='';$('code').value='';});
  window.addEventListener('pageshow',event=>{if(event.persisted&&!state.locked&&!state.busy)void restore();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)invalidate();else if(!state.busy&&!state.locked)void restore();});
  translate();status('checking');void restore();
})();
