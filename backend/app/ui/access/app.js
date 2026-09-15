'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {language:'en', mode:'login', generation:0, controllers:new Set(), profile:null,
    csrf:null, library:null, viewerGeneration:0, page:1, busy:false, locked:false, invite:null, memberPage:1, memberGeneration:0, memberTotal:0, total:0};
  const words = {
    en: {manageMembers:'Review library members',revokeHelp:'Revoking access stops future requests to this library. Files already downloaded cannot be recalled.',revoke:'Revoke access',confirmRevoke:'Confirm revocation',cancel:'Cancel',confirmFor:'Revoke library access for',revoked:'Access revoked.',conflict:'Membership changed. Review the refreshed list before trying again.',owner:'Owner',viewer:'Viewer',contributor:'Contributor',approved:'Approved',requested:'Requested',rejected:'Rejected',unavailableMember:'Currently unavailable',memberRevoked:'Revoked',tagline:'A place for our memories',eyebrow:'YOUR FAMILY, TOGETHER',welcome:'The moments we keep close.',intro:'A private home for family photos. Sign in, or join with the invitation your library owner sent you.',signIn:'Sign in',join:'Join with an invitation',phone:'Phone number',phoneHelp:'Include the country code. Your phone number is your sign-in name.',password:'Password',passwordHelp:'Choose a passphrase of 15–128 characters.',invitation:'Invitation code',inviteHelp:'Use the code sent for this phone number. An accepted invitation opens that library.',help:'Need an invitation or help signing in? Contact your library owner.',yourLibrary:'YOUR FAMILY LIBRARY',gallery:'Little moments. Lasting memories.',signOut:'Sign out',libraryLabel:'Library',refresh:'Refresh',previous:'Previous',next:'Next',anotherInvite:'Have an invitation to another library?',accept:'Accept invitation',inviteSomeone:'Invite someone to this library',ownerHelp:'Create a code for their phone number, then send it privately. They join as a viewer. Original downloads are not included.',createInvite:'Create invitation',sendCode:'Send this code privately. It expires in 24 hours.',cancelInvite:'Cancel this invitation',close:'Close',download:'Download original',captionNote:'Generated descriptions may be inaccurate. Original downloads require separate permission.',footer:'PhotoHouse · Shared by invitation',checking:'Checking your session…',loading:'Loading your library…',denied:'Access could not be confirmed. Check your details or contact your library owner.',unavailable:'PhotoHouse is unavailable. Please try again later.',limited:'Too many attempts. Please wait before trying again.',changed:'Your access changed. Refresh or contact your library owner.',noLibrary:'No library is currently available. Ask your owner for an invitation.',noPhotos:'No photos are available in this library yet.',signedOut:'You are signed out.',logoutFailed:'Sign out could not be completed. Your photos are hidden; try Sign out again.',accepted:'Invitation accepted.',cancelled:'Invitation cancelled.',noCaptions:'No description is available yet.',edited:'Family description',generated:'Generated description',moreCaptions:'Only the first 20 descriptions are shown.',truncated:'Description shortened.',photo:'Photo',video:'Video',other:'Media',previewMissing:'Preview unavailable',working:'Please wait…',invalidPhone:'Include an explicit country code, for example +86.',invalidPassword:'Choose a passphrase of 15–128 characters.',page:'Page',of:'of',photos:'items'},
    zh: {manageMembers:'查看相册库成员',revokeHelp:'撤销权限后，对方的新请求将无法访问此相册库。已下载的文件无法收回。',revoke:'撤销访问权限',confirmRevoke:'确认撤销',cancel:'取消',confirmFor:'撤销以下成员的相册库访问权限：',revoked:'已撤销访问权限。',conflict:'成员信息已更新，请查看刷新后的列表再操作。',owner:'主人',viewer:'浏览者',contributor:'协作者',approved:'已批准',requested:'待批准',rejected:'已拒绝',unavailableMember:'当前不可访问',memberRevoked:'已撤销',tagline:'珍藏一家人的时光',eyebrow:'属于我们一家人的回忆',welcome:'把美好时光，留在身边。',intro:'一个私密的家庭相册。登录，或使用相册主人发给你的邀请码加入。',signIn:'登录',join:'使用邀请码加入',phone:'手机号码',phoneHelp:'请包含国家区号。手机号码用作登录名。',password:'密码',passwordHelp:'请设置 15–128 个字符的密码或短语。',invitation:'邀请码',inviteHelp:'请使用为此手机号码生成的邀请码。验证成功后即可访问对应相册。',help:'需要邀请码或登录帮助？请联系相册主人。',yourLibrary:'我们的家庭相册',gallery:'小小瞬间，长长回忆。',signOut:'退出登录',libraryLabel:'相册库',refresh:'刷新',previous:'上一页',next:'下一页',anotherInvite:'收到另一个相册库的邀请码？',accept:'接受邀请',inviteSomeone:'邀请家人加入这个相册库',ownerHelp:'为对方的手机号码生成邀请码，再私下发送。对方将以浏览者身份加入，不包含原文件下载权限。',createInvite:'生成邀请码',sendCode:'请私下发送此邀请码，有效期为 24 小时。',cancelInvite:'取消此邀请',close:'关闭',download:'下载原文件',captionNote:'自动生成的描述可能不准确。下载原文件需要单独授权。',footer:'PhotoHouse · 受邀共享的家庭相册',checking:'正在检查登录状态…',loading:'正在加载相册…',denied:'暂时无法确认访问权限。请检查信息或联系相册主人。',unavailable:'PhotoHouse 暂时不可用，请稍后重试。',limited:'尝试次数过多，请稍后再试。',changed:'访问权限已发生变化，请刷新或联系相册主人。',noLibrary:'目前没有可访问的相册库，请向相册主人索取邀请。',noPhotos:'这个相册库暂时没有可浏览的照片。',signedOut:'已退出登录。',logoutFailed:'暂时未能完成退出。照片已隐藏，请再次点击退出登录。',accepted:'已接受邀请。',cancelled:'已取消邀请。',noCaptions:'暂时没有描述。',edited:'家人描述',generated:'自动生成的描述',moreCaptions:'仅显示前 20 条描述。',truncated:'描述已缩短。',photo:'照片',video:'视频',other:'媒体',previewMissing:'预览暂不可用',working:'请稍候…',invalidPhone:'请包含国家区号，例如 +86。',invalidPassword:'请设置 15–128 个字符的密码或短语。',page:'第',of:'/',photos:'项'}
  };
  const t = key => words[state.language][key] || key;
  Object.assign(words.en, {familyStories:'Family stories',storyEyebrow:'THE STORY BEHIND THE MOMENT',storyPrivacy:'Shared with this library, not automatically published to TV.',addStory:'Add your memory',storyTitle:'Title (optional)',storyByline:'Written by (display name)',storyLanguage:'Language of your story',otherLanguage:'Other / unspecified',storyText:'What would you like to remember?',storyLimit:'No word-count limit. Up to 64 KiB of text; longer entries are rejected, never shortened.',saveStory:'Save story',savedStory:'Story saved.',storyEmpty:'Every moment has a story. Add yours when you are ready.',storyLoading:'Loading family stories…',storyError:'Stories could not load. Reopen this moment to try again.',editStory:'Edit',history:'History',familyMember:'Family member',you:'You',revision:'Version',moreStories:'More stories',unsavedStory:'Discard your unsaved story?',storyConflict:'This story changed elsewhere. Your draft is still here. Compare the latest version before saving.',compareLatest:'Compare latest version',keepDraft:'Keep my draft as the next version',confirmDraft:'Save your draft over this latest version? Both versions will remain in history.',storySaveError:'Save not confirmed. Your draft is still here; retry the same save before changing it.',storyInvalid:'Nothing was saved. Check the language, title/byline length and the 64 KiB text limit.',deleteStory:'Remove story',confirmDelete:'Remove this story from the library and search? Owner/author history is retained; this is not permanent erasure.',removedStory:'Story removed.',historyTitle:'Story history',restoreDraft:'Use this version as a draft',searchMemories:'Find a memory',searchIn:'Search in',allDescriptions:'Stories and AI descriptions',aiDescriptions:'AI descriptions',aiAndLegacy:'AI descriptions and earlier caption edits',search:'Search',clearSearch:'Show all',matchedFamily:'Found in a family story',matchedAI:'Found in an AI description',matchedLegacy:'Found in an earlier caption edit',noMatches:'No matching memories. Try another word.',draftRecovered:'Your unsaved draft was restored in this tab.',writtenBy:'Written by',unverifiedByline:'Display name supplied by the author'});
  Object.assign(words.zh, {familyStories:'家人的故事',storyEyebrow:'照片背后的故事',storyPrivacy:'与此相册库的成员共享，不会自动发布到电视。',addStory:'写下这段回忆',storyTitle:'标题（可选）',storyByline:'署名（显示名称）',storyLanguage:'故事的语言',otherLanguage:'其他 / 未指定',storyText:'这一刻，有什么值得记住？',storyLimit:'不限制字数。文本最多 64 KiB，超出时明确提示，不会截断。',saveStory:'保存故事',savedStory:'故事已保存。',storyEmpty:'每个瞬间都有故事，准备好时，写下你的回忆。',storyLoading:'正在加载家人的故事…',storyError:'暂时无法加载故事，请重新打开此照片重试。',editStory:'编辑',history:'历史版本',familyMember:'家人',you:'你',revision:'版本',moreStories:'更多故事',unsavedStory:'放弃尚未保存的故事？',storyConflict:'故事已被其他人修改。你的草稿仍在，请先对比最新版本。',compareLatest:'对比最新版本',keepDraft:'将我的草稿作为下一版本',confirmDraft:'确认用你的草稿更新此最新版本？两个版本都会保存在历史记录中。',storySaveError:'尚未确认保存成功。草稿仍在，请先重试同一次保存，再修改内容。',storyInvalid:'未保存。请检查语言、标题和署名长度，以及 64 KiB 文本限制。',deleteStory:'移除故事',confirmDelete:'从相册和搜索中移除此故事？作者和主人仍可查看历史记录，此操作并非永久删除。',removedStory:'故事已移除。',historyTitle:'故事的历史版本',restoreDraft:'将此版本用作草稿',searchMemories:'寻找一段回忆',searchIn:'搜索范围',allDescriptions:'故事与 AI 描述',aiDescriptions:'AI 描述',aiAndLegacy:'AI 描述与早期编辑的描述',search:'搜索',clearSearch:'显示全部',matchedFamily:'来自家人的故事',matchedAI:'来自 AI 描述',matchedLegacy:'来自早期编辑的描述',noMatches:'没有找到匹配的回忆，请换个词试试。',draftRecovered:'已在此标签页恢复未保存的草稿。',writtenBy:'作者',unverifiedByline:'作者自行填写的显示名称'});
  Object.assign(words.en,{storyDeleteError:'Removal not confirmed. Retry Remove story to confirm the same request.',storyCurrent:'Your earlier save was confirmed. A newer version is now shown.'});
  Object.assign(words.zh,{storyDeleteError:'尚未确认移除成功。请再次点击“移除故事”，确认同一次请求。',storyCurrent:'已确认此前的保存。当前显示的是更新的版本。'});
  const storyState={asset:null,editing:null,dirty:false,busy:false,page:1,load:0,loading:false,history:0,deletes:new Map(),pending:null,search:null,suspended:null};
  function storyStatus(key){$('story-status').textContent=key?t(key):'';}
  function abandonStory(){return !storyState.busy&&(!storyState.dirty||window.confirm(t('unsavedStory')));}
  function resetStoryEditor(){
    storyState.editing=null;storyState.dirty=false;storyState.pending=null;
    $('story-form').reset();$('story-form').hidden=true;$('story-compare').hidden=true;$('story-conflict').replaceChildren();
    lockStoryInputs(false);
  }
  function lockStoryInputs(locked){for(const id of ['story-title','story-byline','story-language','story-text'])$(id).disabled=locked;}
  function suspendDraft(){
    if(storyState.dirty&&state.profile&&storyState.asset)storyState.suspended={account:state.profile.account_id,library:state.library,asset:storyState.asset,editing:storyState.editing,pending:storyState.pending,locked:$('story-text').disabled,content:Object.fromEntries(['title','byline','text','language'].map(key=>[key,$('story-'+key).value]))};
  }
  async function restoreWithDraft(){
    const restored=await restore();
    if(!restored||document.hidden)return;
    const draft=storyState.suspended;storyState.suspended=null;
    if(draft&&draft.account===state.profile?.account_id&&draft.library===state.library){
      const role=state.profile.memberships.find(member=>member.library_id===draft.library&&member.available)?.role;
      if(role!=='owner'&&(role!=='contributor'||(draft.editing&&draft.editing.author_id!==draft.account)))return;
      const authorized=await openAsset(draft.asset);
      if(authorized&&!document.hidden&&storyState.asset?.id===draft.asset.id&&state.profile?.account_id===draft.account&&state.library===draft.library){editStory(draft.editing,draft.content);storyState.pending=draft.pending;lockStoryInputs(draft.locked);storyStatus(draft.locked?'storySaveError':'draftRecovered');}
    }
  }
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
    storyState.asset=null;storyState.load++;storyState.history++;storyState.loading=false;storyState.deletes.clear();resetStoryEditor();
    $('story-list').replaceChildren();$('story-history').replaceChildren();$('story-history').hidden=true;$('story-add').hidden=true;$('story-more').hidden=true;storyStatus('');
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
    state.memberGeneration++;$('member-list').replaceChildren();$('member-pages').hidden=true;
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
    storyState.search=null;storyState.suspended=null;$('search-text').value='';$('search-source').value='all';
    state.profile=null;state.csrf=null;state.library=null;state.locked=false;
    $('account-label').textContent='';$('library-select').replaceChildren();$('owner-panel').hidden=true;$('members-panel').hidden=true;
    $('library').hidden=true;$('auth').hidden=false;$('password').value='';$('code').value='';
  }
  function errorStatus(error) {return error.status===409?'conflict':error.status===429?'limited':error.status===401||error.status===403?'denied':'unavailable';}
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
    closeViewer(); storyState.asset=item;storyState.page=1; const viewerGeneration=state.viewerGeneration; $('viewer').showModal(); $('viewer-title').textContent=assetLabel(item);
    void loadStories();
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
      return true;
    } catch(error) {await failure(error,epoch);return false;}
  }
  function storyButton(label, action){const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t(label);button.addEventListener('click',action);return button;}
  function storyText(container, title, text){
    if(title){const heading=document.createElement('h4');heading.textContent=title;container.append(heading);}
    const paragraph=document.createElement('p');paragraph.className='story-text';paragraph.textContent=text;container.append(paragraph);
  }
  function editStory(story=null, content=null){
    if(!abandonStory())return;
    resetStoryEditor();storyState.editing=story;
    const value=content||story||{title:'',byline:'',text:'',language:state.language};
    for(const key of ['title','byline','text','language'])$('story-'+key).value=value[key];
    $('story-form').hidden=false;storyState.dirty=Boolean(content);storyStatus('');$('story-text').focus();
  }
  async function loadStories(append=false){
    const asset=storyState.asset;if(!asset||(append&&storyState.loading))return;
    const page=append?storyState.page+1:storyState.page;
    const epoch=state.generation, viewer=state.viewerGeneration, load=++storyState.load;
    storyState.loading=true;$('story-more').disabled=true;storyStatus('storyLoading');
    try{
      const result=await request(libraryPath(`/assets/${asset.id}/stories`,{page:String(page)}),{epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration||load!==storyState.load)return;
      storyState.page=page;
      if(!append)$('story-list').replaceChildren();
      if(!result.items.length&&!append){const p=document.createElement('p');p.className='story-empty';p.textContent=t('storyEmpty');$('story-list').append(p);}
      for(const story of result.items){
        const article=document.createElement('article');article.className='story-card';
        storyText(article,story.title,story.text);
        const byline=document.createElement('small');byline.title=t('unverifiedByline');
        byline.textContent=`${story.byline||t('familyMember')} · ${story.author_id===state.profile.account_id?t('you'):story.author_id.slice(0,8)} · ${new Date(story.updated_at*1000).toLocaleString(state.language==='zh'?'zh-CN':'en')} · ${t('revision')} ${story.revision}`;article.append(byline);
        const actions=document.createElement('div');actions.className='story-actions';
        if(story.can_edit){actions.append(storyButton('editStory',()=>editStory(story)),storyButton('deleteStory',()=>{void removeStory(story);}));}
        if(story.can_view_history)actions.append(storyButton('history',()=>{void showStoryHistory(story);}));
        article.append(actions);$('story-list').append(article);
      }
      $('story-add').hidden=!result.can_create;$('story-more').hidden=!result.has_more;storyStatus('');
    }catch(error){if(stale(epoch)||viewer!==state.viewerGeneration||load!==storyState.load)return;storyStatus('storyError');if(error.status===401||error.status===403)await failure(error,epoch);}
    finally{if(!stale(epoch)&&viewer===state.viewerGeneration&&load===storyState.load){storyState.loading=false;$('story-more').disabled=false;}}
  }
  async function saveStory(event){
    event.preventDefault();if(storyState.busy||!storyState.asset)return;
    const epoch=state.generation,viewer=state.viewerGeneration;
    const body=Object.fromEntries(['title','byline','text','language'].map(key=>[key,$('story-'+key).value]));
    if(new TextEncoder().encode(body.text).length>65536||new TextEncoder().encode(body.title).length>512||new TextEncoder().encode(body.byline).length>256||!body.text.trim()){storyStatus('storyInvalid');return;}
    if(storyState.editing)body.revision=String(storyState.editing.revision);
    const fingerprint=JSON.stringify(body);
    if(!storyState.pending||storyState.pending.fingerprint!==fingerprint)storyState.pending={fingerprint,id:crypto.randomUUID()};
    body.mutation_id=storyState.pending.id;
    const path=storyState.editing?`/stories/${storyState.editing.id}`:`/assets/${storyState.asset.id}/stories`;
    storyState.busy=true;lockStoryInputs(true);$('story-save').disabled=true;$('story-cancel').disabled=true;storyStatus('working');
    try{
      const result=await request(libraryPath(path),{method:storyState.editing?'PUT':'POST',body,epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration)return;
      const newer=result.revision>(body.revision?Number(body.revision)+1:1);
      resetStoryEditor();storyState.page=1;await loadStories();storyStatus(newer?'storyCurrent':'savedStory');
    }catch(error){
      if(stale(epoch)||viewer!==state.viewerGeneration)return;
      if(error.status===401||error.status===403){await failure(error,epoch);return;}
      const conflict=error.status===409,invalid=error.status===400||error.status===413||error.status===422;
      storyStatus(conflict?'storyConflict':invalid?'storyInvalid':'storySaveError');
      $('story-compare').hidden=!conflict||!storyState.editing;
      // Ambiguous delivery: retain the mutation ID and freeze content for an exact retry.
      lockStoryInputs(!conflict&&!invalid);
    }finally{storyState.busy=false;$('story-save').disabled=false;$('story-cancel').disabled=false;}
  }
  async function showStoryHistory(story,page=1,append=false){
    const epoch=state.generation,viewer=state.viewerGeneration,history=++storyState.history;
    try{
      const result=await request(libraryPath(`/stories/${story.id}/history`,{page:String(page)}),{epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration||history!==storyState.history)return;
      const root=$('story-history');if(!append)root.replaceChildren();root.hidden=false;
      if(!append){const h=document.createElement('h4');h.textContent=t('historyTitle');root.append(h);}
      for(const version of result.items){const article=document.createElement('article');article.className='story-card';const label=document.createElement('small');label.textContent=`${t('revision')} ${version.revision} · ${new Date(version.occurred_at*1000).toLocaleString()}${version.deleted?' · '+t('removedStory'):''}`;article.append(label);storyText(article,version.title,version.text);
        if(!result.story.deleted)article.append(storyButton('restoreDraft',()=>editStory(result.story,version)));root.append(article);}
      if(result.has_more){const more=storyButton('moreStories',()=>{more.remove();void showStoryHistory(story,page+1,true);});root.append(more);}
    }catch(error){if(!stale(epoch)&&viewer===state.viewerGeneration&&history===storyState.history){storyStatus('storyError');await failure(error,epoch);}}
  }
  async function compareStory(){
    if(!storyState.editing||storyState.busy)return;
    const epoch=state.generation,viewer=state.viewerGeneration,id=storyState.editing.id;
    try{
      const result=await request(libraryPath(`/stories/${id}/history`),{epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration||storyState.editing?.id!==id)return;
      const root=$('story-conflict');root.replaceChildren();storyText(root,result.story.title,result.story.text);
      if(!result.story.deleted)root.append(storyButton('keepDraft',()=>{
        if(storyState.busy||storyState.editing?.id!==id||!window.confirm(t('confirmDraft')))return;
        storyState.editing=result.story;storyState.pending=null;root.replaceChildren();$('story-compare').hidden=true;lockStoryInputs(false);storyStatus('');
      }));
    }catch(error){await failure(error,epoch);}
  }
  async function removeStory(story){
    if(storyState.busy||!abandonStory()||!window.confirm(t('confirmDelete')))return;
    const epoch=state.generation,viewer=state.viewerGeneration;
    const key=`${story.id}:${story.revision}`;
    if(!storyState.deletes.has(key))storyState.deletes.set(key,{revision:String(story.revision),mutation_id:crypto.randomUUID()});
    storyState.busy=true;
    try{
      await request(libraryPath(`/stories/${story.id}`),{method:'DELETE',body:storyState.deletes.get(key),epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration)return;
      storyState.deletes.delete(key);resetStoryEditor();storyState.page=1;await loadStories();storyStatus('removedStory');
      // Retain an explicit route to the restricted history until this viewer closes.
      $('story-history').replaceChildren(storyButton('history',()=>{void showStoryHistory(story);}));$('story-history').hidden=false;
    }catch(error){if(!stale(epoch)&&viewer===state.viewerGeneration){if(error.status===409)storyState.deletes.delete(key);storyStatus(error.status===409?'storyConflict':'storyDeleteError');await failure(error,epoch);}}
    finally{storyState.busy=false;}
  }
  async function loadGallery() {
    if(!state.library||state.locked)return;
    const epoch=invalidate();status('loading');
    try {
      const result=storyState.search ? await request(libraryPath('/library/search'),{method:'POST',body:{...storyState.search,page:String(state.page),media:'all'},epoch}) : await request(libraryPath('/assets',{page:String(state.page),page_size:'24'}),{epoch});
      if(stale(epoch))return;
      state.total=result.total;
      for(const item of result.items) {
        const card=document.createElement('button');card.type='button';card.className='asset';
        const image=document.createElement('img');image.loading='lazy';image.alt=assetLabel(item);
        image.src=safeMediaURL(item.id,'thumbnail');
        image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
        const label=document.createElement('span');label.textContent=assetLabel(item);card.append(image,label);
        if(item.match){const excerpt=document.createElement('span');excerpt.className='search-excerpt';excerpt.textContent=t(item.match.source==='family'?'matchedFamily':item.match.source==='ai'?'matchedAI':'matchedLegacy')+' · '+item.match.excerpt;card.append(excerpt);}
        card.addEventListener('click',()=>{void openAsset(item);});$('grid').append(card);
      }
      $('empty').hidden=result.items.length>0;$('empty').textContent=t(storyState.search?'noMatches':'noPhotos');
      const pages=Math.max(1,Math.ceil(result.total/24));
      $('pagination').hidden=result.total===0;$('previous').disabled=state.page===1;$('next').disabled=state.page>=pages;
      $('page-label').textContent=`${t('page')} ${state.page} ${t('of')} ${pages} · ${result.total} ${t('photos')}`;
      status('');
      if(!$('members-panel').hidden&&$('members-panel').open)void loadMembers();
      return true;
    } catch(error) {await failure(error,epoch);return false;}
  }
  async function restore(load=true) {
    const epoch=invalidate();
    try {
      const profile=await request('/auth/session',{epoch});
      if(stale(epoch))return;
      state.profile=profile;state.csrf=profile.csrf_token;state.locked=false;
      $('auth').hidden=true;$('library').hidden=false;$('account-label').textContent=profile.phone_login;
      const available=profile.memberships.filter(m=>m.available===true);
      if(!available.some(m=>m.library_id===state.library)){state.library=available[0]?.library_id||null;state.page=1;state.memberPage=1;}
      $('library-select').replaceChildren();
      for(const member of available) {const option=document.createElement('option');option.value=member.library_id;option.textContent=member.library_id;$('library-select').append(option);}
      $('library-select').value=state.library||'';
      $('owner-panel').hidden=!available.some(m=>m.library_id===state.library&&m.role==='owner');
      $('members-panel').hidden=$('owner-panel').hidden;
      if(!state.library) {$('empty').hidden=false;$('empty').textContent=t('noLibrary');status('');}
      else if(load) return await loadGallery();
      return true;
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
    if(!abandonStory())return;storyState.suspended=null;storyState.search=null;
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
  async function loadMembers() {
    if(state.locked||$('members-panel').hidden)return;
    const epoch=state.generation,library=state.library,memberGeneration=++state.memberGeneration;
    $('member-list').replaceChildren();$('member-pages').hidden=true;
    try {
      const result=await request(`/libraries/${encodeURIComponent(library)}/members?`+new URLSearchParams({page:String(state.memberPage),page_size:'25'}),{epoch});
      if(stale(epoch)||memberGeneration!==state.memberGeneration)return;
      state.memberTotal=result.total;
      for(const member of result.items) {
        const row=document.createElement('div');row.className='member-row';
        const info=document.createElement('div'),phone=document.createElement('span'),label=document.createElement('small');
        phone.textContent=member.phone_login;
        label.textContent=`${t(member.role)} · ${t(member.status==='revoked'?'memberRevoked':member.status)}${member.available?'':' · '+t('unavailableMember')}`;
        info.append(phone,label);row.append(info);
        if(member.role!=='owner'&&member.status!=='revoked') {
          const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t('revoke');
          button.addEventListener('click',()=>{
            if(state.locked||stale(epoch)||state.busy)return;
            row.querySelector('.member-confirm')?.remove();
            const review=document.createElement('div');review.className='member-confirm';
            const text=document.createElement('p');text.textContent=`${t('confirmFor')} ${member.phone_login} · ${library}`;
            const confirm=document.createElement('button');confirm.type='button';confirm.className='primary';confirm.textContent=t('confirmRevoke');
            const cancel=document.createElement('button');cancel.type='button';cancel.className='quiet';cancel.textContent=t('cancel');
            cancel.addEventListener('click',()=>review.remove());
            confirm.addEventListener('click',async()=>{
              if(state.locked||state.busy||stale(epoch))return;
              state.busy=true;confirm.disabled=true;
              try {
                await request(`/libraries/${encodeURIComponent(library)}/members/${encodeURIComponent(member.account_id)}/revoke`,{method:'POST',body:{revision:member.revision},epoch});
                await loadMembers();status('revoked');
              } catch(error) {
                if(error.status===409&&!stale(epoch)){await loadMembers();status('conflict');}
                else await failure(error,epoch);
              } finally {state.busy=false;}
            });
            review.append(text,confirm,cancel);row.append(review);confirm.focus();
          });
          row.append(button);
        }
        $('member-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));
      $('member-pages').hidden=result.total===0;$('member-previous').disabled=state.memberPage===1;$('member-next').disabled=state.memberPage>=pages;
      $('member-page-label').textContent=`${t('page')} ${state.memberPage} ${t('of')} ${pages}`;
    } catch(error) {await failure(error,epoch);}
  }
  const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('photohouse-session'):null;
  if(channel)channel.onmessage=()=>{if(!state.locked&&!state.busy){suspendDraft();if(document.hidden)invalidate();else void restoreWithDraft();}};
  $('auth-form').addEventListener('submit',event=>{void signIn(event);});
  $('login-tab').addEventListener('click',()=>setMode('login'));
  $('register-tab').addEventListener('click',()=>setMode('register'));
  $('logout').addEventListener('click',()=>{void signOut();});
  $('refresh').addEventListener('click',()=>{if(!state.locked&&abandonStory()){state.page=1;void restore();}});
  $('library-select').addEventListener('change',()=>{if(state.locked||!abandonStory()){$('library-select').value=state.library||'';return;}storyState.search=null;storyState.suspended=null;$('search-text').value='';state.library=$('library-select').value;state.page=1;state.memberPage=1;void restore();});
  $('previous').addEventListener('click',()=>{if(state.page>1){state.page--;void loadGallery();}});
  $('next').addEventListener('click',()=>{if(state.page*24<state.total){state.page++;void loadGallery();}});
  $('members-panel').addEventListener('toggle',()=>{if($('members-panel').open)void loadMembers();});
  $('member-previous').addEventListener('click',()=>{if(state.memberPage>1){state.memberPage--;void loadMembers();}});
  $('member-next').addEventListener('click',()=>{if(state.memberPage*25<state.memberTotal){state.memberPage++;void loadMembers();}});
  $('close-viewer').addEventListener('click',()=>{if(abandonStory())closeViewer();});
  $('viewer').addEventListener('cancel',event=>{event.preventDefault();if(abandonStory())closeViewer();});
  $('story-add').addEventListener('click',()=>editStory());
  $('story-form').addEventListener('input',()=>{storyState.dirty=true;});
  $('story-form').addEventListener('submit',event=>{void saveStory(event);});
  $('story-cancel').addEventListener('click',()=>{if(abandonStory()){resetStoryEditor();storyStatus('');}});
  $('story-more').addEventListener('click',()=>{void loadStories(true);});
  $('story-compare').addEventListener('click',()=>{void compareStory();});
  $('story-search').addEventListener('submit',event=>{event.preventDefault();if(state.locked||!abandonStory())return;const text=$('search-text').value.trim();storyState.search=text?{text,source:$('search-source').value}:null;state.page=1;void loadGallery();});
  $('clear-search').addEventListener('click',()=>{if(state.locked||!abandonStory())return;storyState.search=null;$('search-text').value='';state.page=1;void loadGallery();});
  $('invite-form').addEventListener('submit',event=>{void invite(event);});
  $('cancel-invite').addEventListener('click',()=>{void cancelInvite();});
  $('accept-form').addEventListener('submit',event=>{void accept(event);});
  $('language').addEventListener('click',()=>{if(!abandonStory())return;state.language=state.language==='en'?'zh':'en';translate();if(state.profile&&!state.locked)void restore();});
  window.addEventListener('beforeunload',event=>{if(storyState.dirty){event.preventDefault();event.returnValue='';}});
  window.addEventListener('pagehide',()=>{invalidate();$('password').value='';$('code').value='';});
  window.addEventListener('pageshow',event=>{if(event.persisted&&!state.locked&&!state.busy)void restoreWithDraft();});
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){
      suspendDraft();
      invalidate();
    }else if(!state.busy&&!state.locked)void restoreWithDraft();
  });
  translate();status('checking');void restore();
})();
