'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {language:'en', mode:'login', generation:0, controllers:new Set(), profile:null,
    csrf:null, library:null, viewerGeneration:0, page:1, busy:false, locked:false, invite:null, memberPage:1, memberGeneration:0, memberTotal:0, total:0, videoRetryTimer:null, videoController:null};
  const words = {
    en: {manageMembers:'Review library members',revokeHelp:'Revoking access stops future requests to this library. Files already downloaded cannot be recalled.',revoke:'Revoke access',confirmRevoke:'Confirm revocation',cancel:'Cancel',confirmFor:'Revoke library access for',revoked:'Access revoked.',conflict:'Membership changed. Review the refreshed list before trying again.',owner:'Owner',viewer:'Viewer',contributor:'Contributor',approved:'Approved',requested:'Requested',rejected:'Rejected',unavailableMember:'Currently unavailable',memberRevoked:'Revoked',tagline:'A place for our memories',eyebrow:'YOUR FAMILY, TOGETHER',welcome:'The moments we keep close.',intro:'A private home for family photos. Sign in, or join with the invitation your library owner sent you.',signIn:'Sign in',join:'Join with an invitation',phone:'Phone number',phoneHelp:'Include the country code. Your phone number is your sign-in name.',password:'Password',passwordHelp:'Choose a passphrase of 8–128 characters.',invitation:'Invitation code',inviteHelp:'Use the code sent for this phone number. An accepted invitation opens that library.',help:'Need an invitation or help signing in? Contact your library owner.',yourLibrary:'YOUR FAMILY LIBRARY',gallery:'Little moments. Lasting memories.',signOut:'Sign out',libraryLabel:'Library',refresh:'Refresh',previous:'Previous',next:'Next',anotherInvite:'Have an invitation to another library?',accept:'Accept invitation',inviteSomeone:'Invite someone to this library',ownerHelp:'Create a code for their phone number, then send it privately. They join as a viewer. Original downloads are not included.',createInvite:'Create invitation',sendCode:'Send this code privately. It expires in 24 hours.',cancelInvite:'Cancel this invitation',close:'Close',download:'Download original',captionNote:'Generated descriptions may be inaccurate. Original downloads require separate permission.',footer:'PhotoHouse · Shared by invitation',checking:'Checking your session…',loading:'Loading your library…',denied:'Access could not be confirmed. Check your details or contact your library owner.',unavailable:'PhotoHouse is unavailable. Please try again later.',limited:'Too many attempts. Please wait before trying again.',changed:'Your access changed. Refresh or contact your library owner.',noLibrary:'No library is currently available. Ask your owner for an invitation.',noPhotos:'No photos are available in this library yet.',signedOut:'You are signed out.',logoutFailed:'Sign out could not be completed. Your photos are hidden; try Sign out again.',accepted:'Invitation accepted.',cancelled:'Invitation cancelled.',noCaptions:'No description is available yet.',edited:'Family description',generated:'Generated description',moreCaptions:'Only the first 20 descriptions are shown.',truncated:'Description shortened.',photo:'Photo',video:'Video',other:'Media',previewMissing:'Preview unavailable',working:'Please wait…',invalidPhone:'Include an explicit country code, for example +86.',invalidPassword:'Choose a passphrase of 8–128 characters.',page:'Page',of:'of',photos:'items'},
    zh: {manageMembers:'查看相册库成员',revokeHelp:'撤销权限后，对方的新请求将无法访问此相册库。已下载的文件无法收回。',revoke:'撤销访问权限',confirmRevoke:'确认撤销',cancel:'取消',confirmFor:'撤销以下成员的相册库访问权限：',revoked:'已撤销访问权限。',conflict:'成员信息已更新，请查看刷新后的列表再操作。',owner:'主人',viewer:'浏览者',contributor:'协作者',approved:'已批准',requested:'待批准',rejected:'已拒绝',unavailableMember:'当前不可访问',memberRevoked:'已撤销',tagline:'珍藏一家人的时光',eyebrow:'属于我们一家人的回忆',welcome:'把美好时光，留在身边。',intro:'一个私密的家庭相册。登录，或使用相册主人发给你的邀请码加入。',signIn:'登录',join:'使用邀请码加入',phone:'手机号码',phoneHelp:'请包含国家区号。手机号码用作登录名。',password:'密码',passwordHelp:'请设置 8–128 个字符的密码或短语。',invitation:'邀请码',inviteHelp:'请使用为此手机号码生成的邀请码。验证成功后即可访问对应相册。',help:'需要邀请码或登录帮助？请联系相册主人。',yourLibrary:'我们的家庭相册',gallery:'小小瞬间，长长回忆。',signOut:'退出登录',libraryLabel:'相册库',refresh:'刷新',previous:'上一页',next:'下一页',anotherInvite:'收到另一个相册库的邀请码？',accept:'接受邀请',inviteSomeone:'邀请家人加入这个相册库',ownerHelp:'为对方的手机号码生成邀请码，再私下发送。对方将以浏览者身份加入，不包含原文件下载权限。',createInvite:'生成邀请码',sendCode:'请私下发送此邀请码，有效期为 24 小时。',cancelInvite:'取消此邀请',close:'关闭',download:'下载原文件',captionNote:'自动生成的描述可能不准确。下载原文件需要单独授权。',footer:'PhotoHouse · 受邀共享的家庭相册',checking:'正在检查登录状态…',loading:'正在加载相册…',denied:'暂时无法确认访问权限。请检查信息或联系相册主人。',unavailable:'PhotoHouse 暂时不可用，请稍后重试。',limited:'尝试次数过多，请稍后再试。',changed:'访问权限已发生变化，请刷新或联系相册主人。',noLibrary:'目前没有可访问的相册库，请向相册主人索取邀请。',noPhotos:'这个相册库暂时没有可浏览的照片。',signedOut:'已退出登录。',logoutFailed:'暂时未能完成退出。照片已隐藏，请再次点击退出登录。',accepted:'已接受邀请。',cancelled:'已取消邀请。',noCaptions:'暂时没有描述。',edited:'家人描述',generated:'自动生成的描述',moreCaptions:'仅显示前 20 条描述。',truncated:'描述已缩短。',photo:'照片',video:'视频',other:'媒体',previewMissing:'预览暂不可用',working:'请稍候…',invalidPhone:'请包含国家区号，例如 +86。',invalidPassword:'请设置 8–128 个字符的密码或短语。',page:'第',of:'/',photos:'项'}
  };
  const t = key => words[state.language][key] || key;
  Object.assign(words.en, {familyStories:'Family stories',storyEyebrow:'THE STORY BEHIND THE MOMENT',storyPrivacy:'Shared with this library, not automatically published to TV.',addStory:'Add your memory',storyTitle:'Title (optional)',storyByline:'Written by (display name)',storyLanguage:'Language of your story',otherLanguage:'Other / unspecified',storyText:'What would you like to remember?',storyLimit:'No word-count limit. Up to 64 KiB of text; longer entries are rejected, never shortened.',saveStory:'Save story',savedStory:'Story saved.',storyEmpty:'Every moment has a story. Add yours when you are ready.',storyLoading:'Loading family stories…',storyError:'Stories could not load. Reopen this moment to try again.',editStory:'Edit',history:'History',familyMember:'Family member',you:'You',revision:'Version',moreStories:'More stories',unsavedStory:'Discard your unsaved story?',storyConflict:'This story changed elsewhere. Your draft is still here. Compare the latest version before saving.',compareLatest:'Compare latest version',keepDraft:'Keep my draft as the next version',confirmDraft:'Save your draft over this latest version? Both versions will remain in history.',storySaveError:'Save not confirmed. Your draft is still here; retry the same save before changing it.',storyInvalid:'Nothing was saved. Check the language, title/byline length and the 64 KiB text limit.',deleteStory:'Remove story',confirmDelete:'Remove this story from the library and search? Owner/author history is retained; this is not permanent erasure.',removedStory:'Story removed.',historyTitle:'Story history',restoreDraft:'Use this version as a draft',searchMemories:'Find a memory',searchIn:'Search in',allDescriptions:'Stories and AI descriptions',aiDescriptions:'AI descriptions',aiAndLegacy:'AI descriptions and earlier caption edits',search:'Search',clearSearch:'Show all',matchedFamily:'Found in a family story',matchedAI:'Found in an AI description',matchedLegacy:'Found in an earlier caption edit',noMatches:'No matching memories. Try another word.',draftRecovered:'Your unsaved draft was restored in this tab.',writtenBy:'Written by',unverifiedByline:'Display name supplied by the author'});
  Object.assign(words.zh, {familyStories:'家人的故事',storyEyebrow:'照片背后的故事',storyPrivacy:'与此相册库的成员共享，不会自动发布到电视。',addStory:'写下这段回忆',storyTitle:'标题（可选）',storyByline:'署名（显示名称）',storyLanguage:'故事的语言',otherLanguage:'其他 / 未指定',storyText:'这一刻，有什么值得记住？',storyLimit:'不限制字数。文本最多 64 KiB，超出时明确提示，不会截断。',saveStory:'保存故事',savedStory:'故事已保存。',storyEmpty:'每个瞬间都有故事，准备好时，写下你的回忆。',storyLoading:'正在加载家人的故事…',storyError:'暂时无法加载故事，请重新打开此照片重试。',editStory:'编辑',history:'历史版本',familyMember:'家人',you:'你',revision:'版本',moreStories:'更多故事',unsavedStory:'放弃尚未保存的故事？',storyConflict:'故事已被其他人修改。你的草稿仍在，请先对比最新版本。',compareLatest:'对比最新版本',keepDraft:'将我的草稿作为下一版本',confirmDraft:'确认用你的草稿更新此最新版本？两个版本都会保存在历史记录中。',storySaveError:'尚未确认保存成功。草稿仍在，请先重试同一次保存，再修改内容。',storyInvalid:'未保存。请检查语言、标题和署名长度，以及 64 KiB 文本限制。',deleteStory:'移除故事',confirmDelete:'从相册和搜索中移除此故事？作者和主人仍可查看历史记录，此操作并非永久删除。',removedStory:'故事已移除。',historyTitle:'故事的历史版本',restoreDraft:'将此版本用作草稿',searchMemories:'寻找一段回忆',searchIn:'搜索范围',allDescriptions:'故事与 AI 描述',aiDescriptions:'AI 描述',aiAndLegacy:'AI 描述与早期编辑的描述',search:'搜索',clearSearch:'显示全部',matchedFamily:'来自家人的故事',matchedAI:'来自 AI 描述',matchedLegacy:'来自早期编辑的描述',noMatches:'没有找到匹配的回忆，请换个词试试。',draftRecovered:'已在此标签页恢复未保存的草稿。',writtenBy:'作者',unverifiedByline:'作者自行填写的显示名称'});
  Object.assign(words.en,{storyDeleteError:'Removal not confirmed. Retry Remove story to confirm the same request.',storyCurrent:'Your earlier save was confirmed. A newer version is now shown.'});
  Object.assign(words.zh,{storyDeleteError:'尚未确认移除成功。请再次点击“移除故事”，确认同一次请求。',storyCurrent:'已确认此前的保存。当前显示的是更新的版本。'});
  const storyState={asset:null,editing:null,dirty:false,busy:false,page:1,load:0,loading:false,history:0,deletes:new Map(),pending:null,search:null,suspended:null};
  const peopleState={page:1,total:0,load:0,query:'',named:'all'};
  const directoryState={page:1,total:0,load:0,query:'',person:null,assetLoad:0,assetPage:1,assetTotal:0};
  const tagState={page:1,total:0,load:0,query:'',tag:null,tagLoad:0,tagPage:1,tagTotal:0,open:null};
  const duplicateState={page:1,total:0,load:0};
  // Date/media narrowing. `binding` is issued by the facets route and must be echoed to
  // the search route; `fingerprint` chains a later page to the exact filter it paginates.
  const discoveryState={binding:null,page:1,total:0,facetLoad:0,searchLoad:0,fingerprint:null,applied:false,appliedFilters:null,placePage:1,placeTotal:0,places:[],selectedPlaces:new Set(),placesAvailable:false};
  const unassignedState={page:1,total:0,load:0};
  const faceState={page:1,total:0,load:0};
  const albumState={page:1,total:0,load:0,draft:null,archivedLoad:0};
  const photoState={image:null,surface:null,mode:'fit',scale:1,drag:null};
  const sequenceState={items:[],index:0,origin:'single',playing:false,timer:null,busy:false};
  Object.assign(words.en,{viewPrevious:'Previous photo',viewNext:'Next photo',viewPlay:'Play slideshow',viewPause:'Pause slideshow',viewInterval:'Each preview',viewPage:'This page',viewAlbum:'This album',viewSequenceHelp:'Slideshow uses these previews only; videos are shown as still previews.'});
  Object.assign(words.zh,{viewPrevious:'上一张',viewNext:'下一张',viewPlay:'播放幻灯片',viewPause:'暂停幻灯片',viewInterval:'每张预览',viewPage:'当前页',viewAlbum:'当前相册',viewSequenceHelp:'幻灯片仅播放此组预览，视频显示为静态预览。'});
  Object.assign(words.en,{viewEditing:'Close the story editor or face review before playing a slideshow.'});
  Object.assign(words.zh,{viewEditing:'请先关闭故事编辑或人脸核对面板，再播放幻灯片。'});
  Object.assign(words.en,{viewFit:'Fit',viewWidth:'Fit width',viewHeight:'Fit height',viewActual:'Actual size',viewOut:'Zoom out',viewIn:'Zoom in',viewFullscreen:'Fullscreen',viewExitFullscreen:'Exit fullscreen',viewFullscreenFailed:'Fullscreen is unavailable in this browser.',viewHelp:'Scroll to zoom; drag to pan. Keyboard: + / − zoom, arrows pan, 0 fits.',viewQuality:'Thumbnail preview. Actual size means preview pixels, not the original photo.',assignmentRestricted:'This saved person cannot be assigned yet: their library ownership needs review. No changes were made.',assignmentChooseHelp:'Select a person, then review the face and press Confirm assignment.'});
  Object.assign(words.zh,{viewFit:'适合窗口',viewWidth:'适合宽度',viewHeight:'适合高度',viewActual:'实际大小',viewOut:'缩小',viewIn:'放大',viewFullscreen:'全屏',viewExitFullscreen:'退出全屏',viewFullscreenFailed:'此浏览器暂不支持全屏。',viewHelp:'滚轮缩放，拖动平移。键盘：+ / − 缩放，方向键平移，0 适合窗口。',viewQuality:'当前为缩略预览。“实际大小”指预览图像素，并非原始照片。',assignmentRestricted:'此人物暂不能分配：需先确认其家庭库归属。未作任何更改。',assignmentChooseHelp:'选择人物后，请核对人脸并点击“确认归属”。'});
  Object.assign(words.en,{preparedPlayback:'Prepared video',videoChecking:'Checking protected video…',videoUnavailable:'This prepared video is unavailable.',videoNotPrepared:'This video is not prepared yet.',videoChanged:'This video changed. Close it and refresh the library.',videoBusy:'The prepared video is busy. Wait before retrying.',videoRetry:'Retry video',videoRetryLater:'Retry later',videoUnauthorized:'Your access changed. The video was closed.',videoInterrupted:'Playback was interrupted. Retry the video.'});
  Object.assign(words.zh,{preparedPlayback:'已准备的视频',videoChecking:'正在检查受保护的视频…',videoUnavailable:'此准备好的视频暂不可用。',videoNotPrepared:'此视频尚未准备好。',videoChanged:'此视频已发生变化。请关闭后刷新相册库。',videoBusy:'准备好的视频当前繁忙，请稍后再试。',videoRetry:'重试视频',videoRetryLater:'稍后重试',videoUnauthorized:'访问权限已变化，视频已关闭。',videoInterrupted:'播放已中断，请重试视频。'});
  Object.assign(words.en,{newPerson:'Create a new person',createAssign:'Create and assign',unassignFace:'Remove this assignment',confirmUnassign:'Remove this face assignment? The saved person and photo will be kept.',albums:'Family albums',albumPrivacy:'Saved in this library, not automatically published to TV.',newAlbum:'Create album',editAlbum:'Edit album',albumTitle:'Album title',albumTitleZh:'Chinese title (optional)',albumDescription:'Description',albumTheme:'Theme',saveAlbum:'Save album',albumSaved:'Album saved.',noAlbums:'No library-owned albums yet. Earlier unowned albums need a reviewed import.',selectPhotos:'Choose photos/videos (up to 60)',selectedPhotos:'Selected order',moveUp:'Move earlier',moveDown:'Move later',remove:'Remove',setCover:'Use as cover',cover:'Cover',albumEmpty:'Empty album',albumChanged:'Album changed. Close this editor and reopen the current version before editing.',albumUncertain:'Save not confirmed. Retry this same save or close and review the saved albums.',discardAlbum:'Discard this unsaved album edit?',albumNeedsReview:'Some earlier selections are no longer available. Saving will remove unavailable entries.',newPersonHelp:'Use an existing saved person when possible. Creating a name does not merge duplicates.'});
  Object.assign(words.zh,{newPerson:'创建新人物',createAssign:'创建并分配',unassignFace:'取消此人脸归属',confirmUnassign:'取消此人脸归属？已保存的人物和照片将保留。',albums:'家庭主题相册',albumPrivacy:'保存在本家庭库，不会自动发布到电视。',newAlbum:'创建相册',editAlbum:'编辑相册',albumTitle:'相册标题',albumTitleZh:'中文标题（可选）',albumDescription:'描述',albumTheme:'主题',saveAlbum:'保存相册',albumSaved:'相册已保存。',noAlbums:'暂无属于本库的相册。旧的未归属相册需经确认后导入。',selectPhotos:'选择照片或视频（最多 60 项）',selectedPhotos:'已选顺序',moveUp:'向前移动',moveDown:'向后移动',remove:'移除',setCover:'设为封面',cover:'封面',albumEmpty:'空相册',albumChanged:'相册已更改，请关闭编辑器并打开最新版本后再编辑。',albumUncertain:'尚未确认保存成功。请重试同一次保存，或关闭并核对已保存相册。',discardAlbum:'放弃尚未保存的相册修改？',albumNeedsReview:'部分原选项已不可访问，保存将移除这些选项。',newPersonHelp:'请优先选择已有的人物。创建姓名不会自动合并重名人物。'});
  Object.assign(words.en,{closeSelection:'Close selection'});
  Object.assign(words.zh,{closeSelection:'关闭选择面板'});
  Object.assign(words.en,{assignFaces:'Review face assignments · Owner',assignHelp:'Choose an existing person for one face. No automatic propagation or new person is created.',unassigned:'Unassigned',choosePerson:'Choose a person',confirmAssignment:'Confirm assignment',assignmentReview:'Assign this face to',assignmentSaved:'Assignment saved. Other faces were not changed.',assignmentConflict:'The face or person changed, or face processing is active. Refresh and review before trying again.',assignmentFailed:'Save not confirmed. Refresh and review this face before trying again.',assignmentUnavailable:'This assignment needs a separate ownership review.',noFaces:'No detected faces on this asset.',selectPerson:'Select this person'});
  Object.assign(words.zh,{assignFaces:'查看人脸归属 · 主人',assignHelp:'为一张人脸选择已保存的人物。不会自动传播标签或创建新人物。',unassigned:'未分配',choosePerson:'选择人物',confirmAssignment:'确认归属',assignmentReview:'将这张人脸分配给',assignmentSaved:'已保存归属，其他人脸未更改。',assignmentConflict:'人脸或人物已更改，或人脸处理正在进行。请刷新并重新确认。',assignmentFailed:'尚未确认保存成功，请刷新并核对此人脸后再试。',assignmentUnavailable:'此归属需要另行确认权限。',noFaces:'此照片暂无已检测的人脸。',selectPerson:'选择此人'});
  Object.assign(words.en,{managePeople:'Manage people · Owner',peopleHelp:'Review saved names and faces in this library. Renaming does not merge people or change face assignments.',findPerson:'Find a saved name',peopleEmpty:'No matching saved names. Unassigned faces and names not linked to this library are not included yet.',personName:'Display name',unnamedPerson:'Unnamed person',reviewFaces:'Review faces',saveName:'Save name',nameSaved:'Name saved.',nameConflict:'This person changed. Review the refreshed record before editing again.',nameUnavailable:'Name editing needs a separate ownership review for this record.',facesCount:'faces in this library',moreFaces:'More faces',nameShortened:'Long existing name: preview shortened.',nameSaveFailed:'Save not confirmed. Refresh the record before trying again.'});
  Object.assign(words.zh,{managePeople:'管理人物 · 主人',peopleHelp:'查看本家庭库中已保存的人名和人脸。修改姓名不会合并人物或更改人脸归属。',findPerson:'查找已保存的人名',peopleEmpty:'没有匹配的人名。暂不包含未分配的人脸或尚未关联到本家庭库的人名。',personName:'显示姓名',unnamedPerson:'未命名人物',reviewFaces:'查看人脸',saveName:'保存姓名',nameSaved:'姓名已保存。',nameConflict:'该人物已更改，请查看刷新后的记录再编辑。',nameUnavailable:'此记录需另行确认归属后才能修改姓名。',facesCount:'张本库人脸',moreFaces:'更多人脸',nameShortened:'原姓名较长，此处缩短显示。',nameSaveFailed:'尚未确认保存成功，请刷新记录后再试。'});
  Object.assign(words.en,{viewFilmstrip:'Photos in this view',viewFilmstripItem:'Photo',goToPage:'Go to page',go:'Go',pageRange:'Enter a page number between 1 and the last page.'});
  Object.assign(words.zh,{viewFilmstrip:'当前视图中的照片',viewFilmstripItem:'照片',goToPage:'跳转到页码',go:'前往',pageRange:'请输入有效范围内的页码。'});
  Object.assign(words.en,{displayName:'Your name',displayNameHelp:'How your family will see you, up to 64 characters.',invalidName:'Enter your name to join.',filterByDate:'Filter by date, places and media',discoveryHelp:'Narrow this library by when a photo was taken, a reviewed place, and whether it is a photo or a video. Read-only: nothing here changes or hides a photo.',places:'Places',placesHelp:'Choose a named place from reviewed library metadata. Places are shown only when this library has them.',placesNone:'No named places are available in this library.',placesUnavailable:'Named places are not available for this library.',placesLoading:'Loading named places…',placesRetry:'Retry places',placesCount:'items',placesLimit:'Choose up to 20 places at a time.',placeSelected:'Selected',mediaKind:'Media',mediaAll:'Photos and videos',mediaImage:'Photos only',mediaVideo:'Videos only',dateFrom:'From',dateTo:'To',applyFilter:'Apply',clearFilter:'Clear',discoveryHint:'Choose a date range, named place or media kind, then apply.',discoveryRange:'Enter a range whose first date is not after the second.',discoveryNone:'No photo in this library matches that filter.',discoveryChanged:'This library changed since the filter was prepared. Reopen the panel and apply again.',discoveryResult:'Filtered photo'});
  Object.assign(words.zh,{displayName:'您的名字',displayNameHelp:'家人将以此称呼您，最多 64 个字符。',invalidName:'请输入您的名字后再加入。',filterByDate:'按日期、地点和媒体筛选',discoveryHelp:'按拍摄时间、已审核的地点和媒体类型缩小本资料库范围。此处为只读：不会更改或隐藏任何照片。',places:'地点',placesHelp:'选择本家庭库已审核元数据中的命名地点。只有本库存在地点信息时才会显示。',placesNone:'本家庭库暂无可用的命名地点。',placesUnavailable:'本家庭库暂不提供命名地点。',placesLoading:'正在加载命名地点…',placesRetry:'重试地点',placesCount:'项',placesLimit:'一次最多选择 20 个地点。',placeSelected:'已选择',mediaKind:'媒体',mediaAll:'照片和视频',mediaImage:'仅照片',mediaVideo:'仅视频',dateFrom:'从',dateTo:'到',applyFilter:'应用',clearFilter:'清除',discoveryHint:'请选择日期范围、命名地点或媒体类型，然后应用。',discoveryRange:'请输入起始日期不晚于结束日期的范围。',discoveryNone:'本资料库中没有符合该筛选的照片。',discoveryChanged:'准备筛选后本资料库已发生变化。请重新打开面板后再应用。',discoveryResult:'筛选出的照片'});
  Object.assign(words.en,{peopleFilter:'Show',peopleAll:'Named and unnamed',peopleNamed:'Named only',peopleUnnamed:'Unnamed only',unassignedFaces:'Unassigned faces · Owner worklist',unassignedHelp:'Faces that no saved person claims yet, across this library. Assigning one keeps the rest of the list.',noUnassignedFaces:'No unassigned faces in this library.',sourcePhoto:'Photo',openPhoto:'Open this photo'});
  Object.assign(words.zh,{peopleFilter:'显示',peopleAll:'已命名与未命名',peopleNamed:'仅已命名',peopleUnnamed:'仅未命名',unassignedFaces:'未分配人脸 · 主人工作清单',unassignedHelp:'本家庭库中尚未归属任何人的人脸。分配其中一张后，清单其余项保持不变。',noUnassignedFaces:'本家庭库中没有未分配的人脸。',sourcePhoto:'照片',openPhoto:'打开这张照片'});
  Object.assign(words.en,{personPhotos:'Photos of this person',noPersonPhotos:'No photo in this library is labelled with this person yet.',clearPerson:'Close',personPhotosHelp:'Read-only. A face label is a guess the library made; it can be wrong.'});
  Object.assign(words.en,{peopleInLibrary:'People in this library',peopleDirectoryHelp:'Names saved in this library, with one face photo each. Only the owner can change a name.',findPersonInLibrary:'Find a person',noPeopleInLibrary:'No saved person names in this library yet.'});
  Object.assign(words.zh,{personPhotos:'此人的照片',noPersonPhotos:'本家庭库中还没有标记为此人的照片。',clearPerson:'关闭',personPhotosHelp:'只读。人脸标记是系统自动判断的结果，可能不准确。'});
  Object.assign(words.zh,{peopleInLibrary:'本家庭库的人物',peopleDirectoryHelp:'本家庭库中已保存的人名，每位配一张人脸照片。只有主人可以修改姓名。',findPersonInLibrary:'查找人物',noPeopleInLibrary:'本家庭库还没有保存的人名。'});
  Object.assign(words.en,{archivedAlbums:'Albums put away',archivedHelp:'Albums this library has put away. Nothing was deleted, so any of them can be brought back.',noArchivedAlbums:'No album has been put away.',archiveAlbum:'Put away',restoreAlbum:'Bring back',confirmArchive:'Put this album away? Nothing is deleted and you can bring it back.'});
  Object.assign(words.en,{describePhoto:'Describe this photo',saveCaption:'Save description',captionSaved:'Saved. Thank you.',captionConflict:'This photo already has a description.'});
  Object.assign(words.en,{duplicatesInLibrary:'Photos saved twice',duplicatesHelp:'Photos this library holds more than once, because the same picture was imported twice. Read-only: nothing here deletes, hides or merges a copy.',savedTimes:'Saved',noDuplicatesInLibrary:'No photo in this library is saved twice.'});
  Object.assign(words.en,{tagsInLibrary:'Tags in this library',tagsHelp:'Tags already attached to photos in this library. Read-only: no tag can be added or removed here.',findTag:'Find a tag',noTagsInLibrary:'No tags in this library yet.',assetsCount:'photos',tagAssets:'Photos with this tag',noTaggedAssets:'No photo in this library carries this tag.',clearTag:'Close'});
  Object.assign(words.zh,{archivedAlbums:'已收起的相册',archivedHelp:'本家庭库收起的相册。照片和相册都没有删除，随时可以恢复。',noArchivedAlbums:'还没有收起任何相册。',archiveAlbum:'收起',restoreAlbum:'恢复',confirmArchive:'确定收起这个相册吗？不会删除任何内容，之后可以恢复。'});
  Object.assign(words.zh,{describePhoto:'为这张照片写一句描述',saveCaption:'保存描述',captionSaved:'已保存，谢谢。',captionConflict:'这张照片已经有描述了。'});
  Object.assign(words.zh,{duplicatesInLibrary:'保存了两次的照片',duplicatesHelp:'本家庭库中保存了不止一次的相同照片，通常是因为同一批照片被导入过两次。只读：这里不会删除、隐藏或合并任何一份。',savedTimes:'保存份数',noDuplicatesInLibrary:'本家庭库中没有重复保存的照片。'});
  Object.assign(words.zh,{tagsInLibrary:'本家庭库的标签',tagsHelp:'本家庭库中照片已附带的标签，仅供查看：此页面不能添加或删除标签。',findTag:'查找标签',noTagsInLibrary:'本家庭库还没有标签。',assetsCount:'张照片',tagAssets:'带此标签的照片',noTaggedAssets:'本家庭库没有照片带此标签。',clearTag:'关闭'});
  Object.assign(words.en,{uploadReview:'Upload review',uploadReviewHelp:'Review private uploads before assigning them to this library. Only the library owner with admin authorization can approve an upload.',uploadLoading:'Loading upload inbox…',uploadEmpty:'No uploads are waiting for review.',uploadRestricted:'Upload review is unavailable for this account.',uploadReviewError:'Uploads could not load. Try again.',approveUpload:'Approve upload',uploadRetryApproval:'Retry approval',approveUploadHelp:'Approving will assign this photo to',approveVisibility:'It will become visible to this library’s members according to their existing access.',uploadReaders:'Current readers',uploadOriginalReaders:'Current original readers',uploadPreviewFailed:'Private preview unavailable. Retry the preview.',uploadApproved:'Upload approved.',uploadConflict:'This upload changed. Review it again before approving.',uploadUncertain:'Approval was not confirmed. The same approval can be retried.',uploadRetry:'Retry review',uploadBytes:'bytes',uploadDimensions:'dimensions',uploadBy:'Uploaded by'});
  Object.assign(words.zh,{uploadReview:'上传审核',uploadReviewHelp:'在将私密上传分配到本家庭库前先进行审核。只有拥有管理员授权的相册库主人可以批准上传。',uploadLoading:'正在加载上传审核…',uploadEmpty:'暂无等待审核的上传。',uploadRestricted:'此账号暂不能进行上传审核。',uploadReviewError:'暂时无法加载上传，请重试。',approveUpload:'批准上传',uploadRetryApproval:'重试批准',approveUploadHelp:'批准后，这张照片将分配到',approveVisibility:'按照现有权限，它将对本家庭库成员可见。',uploadReaders:'当前可读者',uploadOriginalReaders:'当前原文件可读者',uploadPreviewFailed:'私密预览暂不可用，请重试预览。',uploadApproved:'上传已批准。',uploadConflict:'上传内容已变化，请重新审核后再批准。',uploadUncertain:'尚未确认批准结果。可以使用同一确认再次重试。',uploadRetry:'重新审核',uploadBytes:'字节',uploadDimensions:'尺寸',uploadBy:'上传者'});
  const uploadState={page:1,total:0,load:0,items:[],plans:new Map(),dialogItem:null,dialogEpoch:0,previewQueue:{token:0,pending:[],active:false}};
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
  function closeViewer({keepFrame=false}={}) {
    if(state.videoRetryTimer){clearTimeout(state.videoRetryTimer);state.videoRetryTimer=null;}
    if(state.videoController){state.videoController.abort();state.videoController=null;}
    stopSlideshow();sequenceState.items=[];sequenceState.index=0;sequenceState.busy=false;updateSequence();
    resetPhotoView(keepFrame);
    faceState.load++;faceState.page=1;$('face-list').replaceChildren();$('face-panel').hidden=true;$('face-panel').open=false;$('face-status').textContent='';$('face-pages').hidden=true;
    storyState.asset=null;storyState.load++;storyState.history++;storyState.loading=false;storyState.deletes.clear();resetStoryEditor();
    $('story-list').replaceChildren();$('story-history').replaceChildren();$('story-history').hidden=true;$('story-add').hidden=true;$('story-more').hidden=true;storyStatus('');
    state.viewerGeneration++;
    if (!keepFrame&&$('viewer').open) $('viewer').close();
    $('viewer-media').querySelectorAll('video').forEach(video => {video.pause();video.removeAttribute('src');video.load();});
    $('viewer-media').replaceChildren(); $('captions').replaceChildren(); $('viewer-title').textContent='';
    $('viewer-controls').hidden=false;$('viewer-sequence').hidden=true;$('view-help').hidden=false;
    $('original').removeAttribute('href'); $('original').hidden=true;
  }
  function clearPhotos() {
    albumState.load++;$('album-list').replaceChildren();$('album-pages').hidden=true;$('album-status').textContent='';$('album-create').hidden=true;
    if($('album-editor').open)$('album-editor').close();$('album-editor').replaceChildren();
    closeViewer(); $('grid').replaceChildren(); $('pagination').hidden=true; $('empty').hidden=true;
    $('created-code').value=''; $('invitation-result').hidden=true; state.invite=null;
    $('accept-code').value=''; $('invite-phone').value='';
    state.memberGeneration++;$('member-list').replaceChildren();$('member-pages').hidden=true;
    peopleState.load++;$('people-list').replaceChildren();$('people-pages').hidden=true;$('people-status').textContent='';
    clearUploadReview();
  }
  function clearUploadReview(){
    uploadState.load++;uploadState.page=1;uploadState.items=[];uploadState.total=0;uploadState.plans.clear();uploadState.dialogItem=null;uploadState.dialogEpoch=0;uploadState.previewQueue.token++;uploadState.previewQueue.pending=[];uploadState.previewQueue.cancel?.();
    $('uploads-count').textContent='';$('uploads-count').removeAttribute('aria-label');$('uploads-status').textContent='';$('uploads-list').replaceChildren();$('uploads-pages').hidden=true;
    const dialog=$('upload-review-dialog');if(dialog.open)dialog.close();$('upload-review-preview').replaceChildren();$('upload-review-copy').textContent='';$('upload-review-status').textContent='';$('upload-review-approve').textContent=t('approveUpload');
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
    albumState.draft=null;albumState.page=1;$('album-archived-panel').hidden=true;$('album-archived-panel').open=false;$('album-archived-list').replaceChildren();
    storyState.search=null;storyState.suspended=null;$('search-text').value='';$('search-source').value='all';
    state.profile=null;state.csrf=null;state.library=null;state.locked=false;clearUploadReview();$('uploads-panel').hidden=true;$('uploads-open').hidden=true;$('uploads-panel').open=false;
    $('account-label').textContent='';$('library-select').replaceChildren();$('owner-panel').hidden=true;$('members-panel').hidden=true;$('people-panel').hidden=true;
    peopleState.page=1;peopleState.query='';peopleState.named='all';$('people-query').value='';$('people-named').value='all';
    unassignedState.page=1;$('unassigned-list').replaceChildren();
    directoryState.page=1;directoryState.query='';directoryState.total=0;directoryState.person=null;directoryState.assetPage=1;directoryState.assetTotal=0;
    $('directory-query').value='';$('directory-list').replaceChildren();$('directory-status').textContent='';$('directory-pages').hidden=true;
    tagState.page=1;tagState.query='';tagState.total=0;tagState.tag=null;tagState.tagPage=1;tagState.tagTotal=0;tagState.open=null;
    $('tag-query').value='';$('tag-list').replaceChildren();$('tag-status').textContent='';$('tag-pages').hidden=true;$('tag-assets').replaceChildren();
    discoveryState.binding=null;discoveryState.page=1;discoveryState.total=0;discoveryState.facetLoad=0;discoveryState.searchLoad=0;discoveryState.fingerprint=null;discoveryState.applied=false;discoveryState.appliedFilters=null;discoveryState.placePage=1;discoveryState.placeTotal=0;discoveryState.places=[];discoveryState.selectedPlaces.clear();discoveryState.placesAvailable=false;
    $('discovery-panel').hidden=true;$('discovery-panel').open=false;$('discovery-media').value='all';$('discovery-from').value='';$('discovery-to').value='';$('discovery-list').replaceChildren();$('discovery-status').textContent='';$('discovery-pages').hidden=true;$('discovery-place-list').replaceChildren();$('discovery-place-pages').hidden=true;$('discovery-places').hidden=true;$('discovery-places-status').textContent='';
    $('library').hidden=true;$('auth').hidden=false;$('password').value='';$('code').value='';$('name').value='';
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
  function resetPhotoView(keepFrame=false){
    if(!keepFrame&&document.fullscreenElement===$('photo-viewer'))void document.exitFullscreen().catch(()=>{});
    if(photoState.drag&&$('viewer-media').hasPointerCapture(photoState.drag.id))$('viewer-media').releasePointerCapture(photoState.drag.id);
    photoState.image=null;photoState.surface=null;photoState.drag=null;photoState.mode='fit';photoState.scale=1;
    $('viewer-media').classList.remove('dragging');$('photo-viewer').hidden=!keepFrame;
    $('view-scale').textContent='';$('view-quality').textContent='';
    for(const id of ['fit','width','height','actual','in','out'])$('view-'+id).disabled=true;
  }
  function photoButtons(){
    for(const mode of ['fit','width','height','actual'])$('view-'+mode).setAttribute('aria-pressed',String(photoState.mode===mode));
    $('view-scale').textContent=Math.round(photoState.scale*100)+'%';
    $('view-in').disabled=photoState.scale>=16;$('view-out').disabled=photoState.scale<=0.01;
  }
  function drawPhoto(scale,anchor){
    const img=photoState.image,stage=$('viewer-media'),surface=photoState.surface;
    if(!img?.naturalWidth||!stage.clientWidth||!surface)return;
    const oldScale=photoState.scale;
    // Anchor zoom to the image pixel under the pointer (or the viewport centre).
    const x=anchor?.x??stage.clientWidth/2,y=anchor?.y??stage.clientHeight/2;
    const px=(stage.scrollLeft+x-img.offsetLeft)/oldScale,py=(stage.scrollTop+y-img.offsetTop)/oldScale;
    photoState.scale=Math.max(0.01,Math.min(16,scale));
    const width=img.naturalWidth*photoState.scale,height=img.naturalHeight*photoState.scale;
    surface.style.width=Math.max(stage.clientWidth,width)+'px';surface.style.height=Math.max(stage.clientHeight,height)+'px';
    img.style.width=width+'px';img.style.height=height+'px';
    img.style.left=Math.max(0,(stage.clientWidth-width)/2)+'px';img.style.top=Math.max(0,(stage.clientHeight-height)/2)+'px';
    stage.scrollLeft=anchor?px*photoState.scale+img.offsetLeft-x:(surface.offsetWidth-stage.clientWidth)/2;
    stage.scrollTop=anchor?py*photoState.scale+img.offsetTop-y:(surface.offsetHeight-stage.clientHeight)/2;
    photoButtons();
  }
  function fitPhoto(mode=photoState.mode){
    const img=photoState.image,stage=$('viewer-media');
    if(!img?.naturalWidth)return;
    photoState.mode=mode;
    const width=stage.clientWidth/img.naturalWidth,height=stage.clientHeight/img.naturalHeight;
    drawPhoto(mode==='fit'?Math.min(width,height):mode==='width'?width:mode==='height'?height:mode==='actual'?1:photoState.scale);
  }
  function zoomPhoto(factor,anchor={}){if(!photoState.image?.naturalWidth)return;photoState.mode='custom';drawPhoto(photoState.scale*factor,anchor);}
  async function fullscreenPhoto(){
    try{
      if(document.fullscreenElement===$('photo-viewer'))await document.exitFullscreen();
      else if($('photo-viewer').requestFullscreen)await $('photo-viewer').requestFullscreen();
      else throw new Error('Fullscreen unavailable');
    }catch{if(!$('photo-viewer').hidden)$('view-quality').textContent=t('viewQuality')+' '+t('viewFullscreenFailed');}
  }
  async function previewURL(id,epoch){
    // Prefer an already prepared larger thumbnail. Probe metadata only; no
    // original/display fallback or runtime media generation is introduced.
    const url=safeMediaURL(id,'thumbnail',{size:'1024'}),controller=new AbortController();
    state.controllers.add(controller);
    try{
      const response=await fetch(url,{method:'HEAD',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      if(stale(epoch))throw new DOMException('Stale request','AbortError');
      if(response.status===404)return safeMediaURL(id,'thumbnail');
      if(!response.ok){const error=new Error('Preview unavailable');error.status=response.status;throw error;}
      return url;
    }finally{state.controllers.delete(controller);}
  }
  function showPhoto(item,url){
    const image=document.createElement('img'),surface=document.createElement('div');surface.className='viewer-surface';
    image.alt=assetLabel(item);image.draggable=false;photoState.image=image;photoState.surface=surface;
    $('photo-viewer').hidden=false;$('view-quality').textContent=t('viewQuality');
    for(const id of ['fit','width','height','actual','in','out'])$('view-'+id).disabled=true;
    image.addEventListener('load',()=>{if(photoState.image!==image)return;for(const id of ['fit','width','height','actual'])$('view-'+id).disabled=false;fitPhoto('fit');updateSequence();scheduleSlideshow();});
    image.addEventListener('error',()=>{if(photoState.image!==image)return;stopSlideshow();$('view-quality').textContent=t('previewMissing');});
    image.src=url;surface.append(image);$('viewer-media').append(surface);
  }
  async function showPreparedVideo(item,epoch,viewerGeneration){
    const current=()=>!stale(epoch)&&viewerGeneration===state.viewerGeneration&&$('viewer').open;
    if(!current())return;
    const media=$('viewer-media');
    media.replaceChildren();
    $('viewer-controls').hidden=true;$('viewer-sequence').hidden=true;$('view-help').hidden=true;
    $('view-quality').textContent=t('videoChecking');
    function offerRetry(message,retryHeader=null,status=0){
      if(!current())return;
      if(state.videoRetryTimer){clearTimeout(state.videoRetryTimer);state.videoRetryTimer=null;}
      $('view-quality').textContent=t(message);
      const retry=document.createElement('button');retry.type='button';retry.className='quiet';retry.textContent=t('videoRetry');
      let wait=status===429?5000:0;
      if(retryHeader!==null){
        const value=retryHeader.trim();
        if(/^\d+$/.test(value)){
          const seconds=Number(value);wait=Number.isSafeInteger(seconds)&&seconds<=Number.MAX_SAFE_INTEGER/1000?seconds*1000:Infinity;
        }else{
          const date=Date.parse(value);wait=Number.isFinite(date)?Math.max(0,date-Date.now()):Infinity;
        }
      }
      const readyAt=Date.now()+wait;
      retry.disabled=wait>0;
      if(!Number.isFinite(readyAt))retry.textContent=t('videoRetryLater');
      function unlock(){
        state.videoRetryTimer=null;
        if(!current())return;
        const remaining=readyAt-Date.now();
        if(remaining<=0)retry.disabled=false;
        else state.videoRetryTimer=setTimeout(unlock,Math.min(remaining,60000));
      }
      if(wait>0&&Number.isFinite(readyAt))state.videoRetryTimer=setTimeout(unlock,Math.min(wait,60000));
      retry.addEventListener('click',()=>{if(retry.disabled||!current())return;retry.disabled=true;retry.remove();void showPreparedVideo(item,epoch,viewerGeneration);});
      media.replaceChildren(retry);
    }
    const controller=new AbortController();state.controllers.add(controller);state.videoController=controller;
    const path=safeMediaURL(item.id,'playback');
    let response;
    try{
      response=await fetch(path,{method:'HEAD',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
    }catch(error){
      if(error.name!=='AbortError')offerRetry('videoUnavailable');
      return;
    }finally{state.controllers.delete(controller);if(state.videoController===controller)state.videoController=null;}
    if(!current())return;
    const contentType=(response.headers.get('content-type')||'').split(';',1)[0].trim().toLowerCase();
    const lengthText=response.headers.get('content-length')||'';
    const length=Number(lengthText);
    const validHeaders=response.status===200&&contentType==='video/mp4'&&
      response.headers.get('cache-control')==='no-store'&&response.headers.get('accept-ranges')==='bytes'&&
      !response.headers.has('content-range')&&(response.headers.get('content-encoding')||'identity')==='identity'&&
      /^"[a-f0-9]{64}"$/.test(response.headers.get('etag')||'')&&/^\d+$/.test(lengthText)&&
      Number.isSafeInteger(length)&&length>0&&length<=32*1024*1024*1024;
    if(!validHeaders){
      if(response.status===401||response.status===403){
        const error=new Error('Prepared playback denied');error.status=response.status;
        await failure(error,epoch);return;
      }
      offerRetry(response.status===404?'videoNotPrepared':response.status===409?'videoChanged':response.status===429?'videoBusy':'videoUnavailable',response.headers.get('retry-after'),response.status);
      return;
    }
    const video=document.createElement('video');video.controls=true;video.preload='metadata';video.playsInline=true;video.setAttribute('aria-label',assetLabel(item));
    const failedPlayback=()=>{
      if(!current())return;
      video.removeEventListener('error',failedPlayback);video.removeEventListener('abort',failedPlayback);
      video.pause();video.removeAttribute('src');video.load();video.remove();
      offerRetry('videoInterrupted');
    };
    video.addEventListener('error',failedPlayback);video.addEventListener('abort',failedPlayback);
    video.src=path;media.append(video);$('view-quality').textContent=t('preparedPlayback');
  }
  function updateFilmstrip(s){
    const strip=$('viewer-filmstrip');strip.setAttribute('aria-label',t('viewFilmstrip'));
    if(s.items.length<2){strip.replaceChildren();return;}
    // Same bounded window as the legacy strip (at most 11 thumbnails, so a long
    // page never fetches every preview). start is clamped so the window keeps its
    // width at the tail of the list instead of shrinking to as few as 6.
    const start=Math.max(0,Math.min(s.index-5,s.items.length-11));
    const end=Math.min(s.items.length,start+11);
    strip.replaceChildren(...s.items.slice(start,end).map((item,offset)=>{
      const index=start+offset,button=document.createElement('button');
      button.type='button';button.className='quiet';button.dataset.viewerIndex=String(index);button.disabled=s.busy;
      button.setAttribute('aria-label',`${t('viewFilmstripItem')} ${index+1} / ${s.items.length}`);
      button.setAttribute('aria-current',String(index===s.index));
      const image=document.createElement('img');image.alt='';image.loading='lazy';
      // Same URL the gallery grid already requested, so the HTTP cache serves it.
      image.src=safeMediaURL(item.id,'thumbnail');
      button.append(image);return button;
    }));
    if(!s.busy)strip.querySelector('[aria-current="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'});
  }
  function updateSequence(){
    const s=sequenceState;
    $('viewer-sequence').hidden=s.items.length<2;
    $('view-position').textContent=s.items.length?`${t(s.origin==='album'?'viewAlbum':'viewPage')} · ${s.index+1} / ${s.items.length}`:'';
    $('view-previous').disabled=s.busy||s.index<=0;$('view-next').disabled=s.busy||s.index>=s.items.length-1;
    $('view-play').disabled=s.busy||!photoState.image?.naturalWidth||s.items.length<2||(!s.playing&&s.index>=s.items.length-1);
    $('view-play').textContent=t(s.playing?'viewPause':'viewPlay');$('view-play').setAttribute('aria-pressed',String(s.playing));
    $('viewer-sequence').title=t('viewSequenceHelp');
    updateFilmstrip(s);
  }
  function stopSlideshow(){clearTimeout(sequenceState.timer);sequenceState.timer=null;sequenceState.playing=false;updateSequence();}
  function scheduleSlideshow(){
    const s=sequenceState;clearTimeout(s.timer);s.timer=null;
    if(!s.playing||s.busy||!photoState.image?.naturalWidth||!$('viewer').open)return;
    if(s.index>=s.items.length-1){stopSlideshow();return;}
    const epoch=state.generation,viewer=state.viewerGeneration;
    const interval=Number($('view-interval').value);
    s.timer=setTimeout(()=>{if(stale(epoch)||viewer!==state.viewerGeneration)return;void movePhoto(1,true);},[5000,10000,15000].includes(interval)?interval:5000);
  }
  async function movePhoto(delta,automatic=false){
    const s=sequenceState;
    if(s.busy||state.locked||!$('viewer').open)return;
    if(document.hidden||state.busy||storyState.busy||storyState.dirty||!$('story-form').hidden||$('face-panel').open){stopSlideshow();if(automatic||state.busy||storyState.busy)return;}
    if(!automatic&&!abandonStory())return;
    const next=s.index+delta;
    if(next<0||next>=s.items.length){stopSlideshow();return;}
    const {items,origin}=s;
    await openAsset(items[next],{sequence:items,origin,advance:true,play:automatic&&s.playing});
  }
  async function openAsset(item,{sequence=[item],origin='single',advance=false,play=false}={}) {
    if(state.locked)return;
    const epoch=state.generation;
    closeViewer({keepFrame:advance});storyState.asset=item;storyState.page=1;
    sequenceState.items=sequence.slice();sequenceState.index=Math.max(0,sequence.findIndex(asset=>asset.id===item.id));sequenceState.origin=origin;sequenceState.busy=true;sequenceState.playing=play;updateSequence();
    const viewerGeneration=state.viewerGeneration;if(!$('viewer').open)$('viewer').showModal();$('viewer-title').textContent=assetLabel(item);
    $('photo-viewer').hidden=false;$('view-quality').textContent=t('loading');
    void loadStories();
    $('face-panel').hidden=state.profile?.memberships.find(member=>member.library_id===state.library&&member.available)?.role!=='owner';
    try {
      const detail=await request(libraryPath(`/assets/detail/${item.id}`),{epoch});
      const captions=await request(libraryPath(`/assets/${item.id}/captions`),{epoch});
      if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
      storyState.asset=detail.asset;$('viewer-title').textContent=assetLabel(detail.asset);
      if(detail.asset.kind==='video') {
        await showPreparedVideo(detail.asset,epoch,viewerGeneration);
        if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
      }
      else {
        const url=await previewURL(item.id,epoch);
        if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
        showPhoto(detail.asset,url);
      }
      if(detail.originals_allowed) { $('original').href=safeMediaURL(item.id,'media',{download:'true'});$('original').hidden=false; }
      if(!captions.items.length) {
        const p=document.createElement('p');p.textContent=t('noCaptions');$('captions').append(p);
        // A member may describe a photo that has none. The route refuses an asset that already
        // has a caption, so the control is offered only where it can actually succeed.
        const form=document.createElement('form');form.className='caption-form';
        const label=document.createElement('label');label.htmlFor='caption-text';label.textContent=t('describePhoto');
        const input=document.createElement('input');input.id='caption-text';input.maxLength=1024;input.autocomplete='off';
        const button=document.createElement('button');button.type='submit';button.className='primary';button.textContent=t('saveCaption');
        form.append(label,input,button);
        const status=document.createElement('p');status.className='fine';status.setAttribute('role','status');
        form.addEventListener('submit',async event=>{
          event.preventDefault();
          const text=input.value.trim();
          if(!text||state.busy||state.locked)return;
          state.busy=true;button.disabled=true;
          try{
            const saved=await request(libraryPath(`/assets/${item.id}/captions`),{method:'POST',epoch,body:{text}});
            if(stale(epoch)||viewerGeneration!==state.viewerGeneration)return;
            // Show what was saved without reopening the viewer: the route allows one write per
            // photo, so there is nothing left to submit and the form is replaced in place.
            const written=document.createElement('small');written.textContent=t('edited');
            const written_text=document.createElement('p');written_text.textContent=saved.caption.text;
            p.remove();
            form.replaceWith(written,written_text);
            status.textContent=t('captionSaved');
          }catch(error){status.textContent=t(errorStatus(error));}
          finally{state.busy=false;button.disabled=false;}
        });
        $('captions').append(form,status);
      }
      for(const caption of captions.items) {
        const label=document.createElement('small');label.textContent=t(caption.user_edited?'edited':'generated');
        const p=document.createElement('p');p.textContent=caption.text;
        $('captions').append(label,p);
        if(caption.truncated) {const small=document.createElement('small');small.textContent=t('truncated');$('captions').append(small);}
      }
      if(captions.has_more) {const p=document.createElement('p');p.textContent=t('moreCaptions');$('captions').append(p);}
      return true;
    } catch(error) {
      if(viewerGeneration===state.viewerGeneration&&!stale(epoch)){
        stopSlideshow();$('view-quality').textContent=t(errorStatus(error));
      }
      await failure(error,epoch);return false;
    }
    finally{if(!stale(epoch)&&viewerGeneration===state.viewerGeneration){sequenceState.busy=false;updateSequence();scheduleSlideshow();}}
  }
  function storyButton(label, action){const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t(label);button.addEventListener('click',action);return button;}
  function storyText(container, title, text){
    if(title){const heading=document.createElement('h4');heading.textContent=title;container.append(heading);}
    const paragraph=document.createElement('p');paragraph.className='story-text';paragraph.textContent=text;container.append(paragraph);
  }
  function editStory(story=null, content=null){
    stopSlideshow();
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
        const card=document.createElement('button');card.type='button';card.className='asset';card.dataset.assetId=item.id;
        const image=document.createElement('img');image.loading='lazy';image.alt=assetLabel(item);
        image.src=safeMediaURL(item.id,'thumbnail');
        image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
        const label=document.createElement('span');label.textContent=assetLabel(item);card.append(image,label);
        if(item.match){const excerpt=document.createElement('span');excerpt.className='search-excerpt';excerpt.textContent=t(item.match.source==='family'?'matchedFamily':item.match.source==='ai'?'matchedAI':'matchedLegacy')+' · '+item.match.excerpt;card.append(excerpt);}
        card.addEventListener('click',()=>{void openAsset(item,{sequence:result.items,origin:'page'});});$('grid').append(card);
      }
      $('empty').hidden=result.items.length>0;$('empty').textContent=t(storyState.search?'noMatches':'noPhotos');
      const pages=Math.max(1,Math.ceil(result.total/24));
      $('pagination').hidden=result.total===0;$('previous').disabled=state.page===1;$('next').disabled=state.page>=pages;
      $('page-input').max=String(pages);$('page-input').value=String(state.page);
      $('page-label').textContent=`${t('page')} ${state.page} ${t('of')} ${pages} · ${result.total} ${t('photos')}`;
      status('');
      if(!$('members-panel').hidden&&$('members-panel').open)void loadMembers();
      if(!$('uploads-panel').hidden&&$('uploads-panel').open)void loadUploads();
      if($('directory-panel').open)void loadDirectory();
      if($('tags-panel').open)void loadTags();if($('duplicates-panel').open)void loadDuplicates();
      // Probe once per library (the reset clears the binding): the filter appears only
      // where the deployment has opted in, and reappears on a later load if it does.
      if(!discoveryState.binding)void openDiscovery();
      if(!$('people-panel').hidden&&$('people-panel').open)void loadPeople();
      $('album-create').hidden=state.profile?.memberships.find(m=>m.library_id===state.library&&m.available)?.role!=='owner';
      if($('albums-panel').open)void loadAlbums();
      if(albumState.draft){if(albumState.draft.library===state.library&&albumState.draft.account===state.profile?.account_id&&!$('album-create').hidden)editAlbum(null,albumState.draft);else albumState.draft=null;}
      return true;
    } catch(error) {await failure(error,epoch);return false;}
  }
  async function restore(load=true) {
    const epoch=invalidate();
    try {
      const profile=await request('/auth/session',{epoch});
      if(stale(epoch))return;
      if(state.profile?.account_id!==profile.account_id){peopleState.page=1;peopleState.query='';$('people-query').value='';directoryState.page=1;directoryState.query='';$('directory-query').value='';tagState.page=1;tagState.query='';tagState.tag=null;tagState.open=null;$('tag-query').value='';$('tag-assets').replaceChildren();uploadState.page=1;}
      state.profile=profile;state.csrf=profile.csrf_token;state.locked=false;
      $('auth').hidden=true;$('library').hidden=false;$('account-label').textContent=profile.phone_login;
      const available=profile.memberships.filter(m=>m.available===true);
      if(!available.some(m=>m.library_id===state.library)){state.library=available[0]?.library_id||null;state.page=1;state.memberPage=1;}
      $('library-select').replaceChildren();
      for(const member of available) {const option=document.createElement('option');option.value=member.library_id;option.textContent=member.library_id;$('library-select').append(option);}
      $('library-select').value=state.library||'';
      const isOwner=available.some(m=>m.library_id===state.library&&m.role==='owner');
      $('owner-panel').hidden=!isOwner;$('uploads-panel').hidden=!isOwner;$('uploads-open').hidden=!isOwner;
      $('members-panel').hidden=$('owner-panel').hidden;
      $('people-panel').hidden=$('owner-panel').hidden;
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
    $('registration-fields').hidden=mode!=='register';$('code').required=mode==='register';$('name').required=mode==='register';
    $('password').autocomplete=mode==='register'?'new-password':'current-password';
    $('password').minLength=mode==='register'?8:1;$('password').value='';$('code').value='';translate();
  }
  // UI convenience only: transport and stored identities remain explicit E.164.
  function phoneForRequest(value) {
    const compact=value.replace(/[ ()-]/g,'');
    if(/^\+[1-9][0-9]{7,14}$/.test(compact))return compact;
    if(/^[0-9]{11}$/.test(compact))return '+86'+compact;
    return null;
  }
  Object.assign(words.en, {phoneHelp:'China (+86) is the default. For another country, enter + and its country code.',invalidPhone:'Enter an 11-digit number, or a full international number starting with +.'});
  Object.assign(words.zh, {phoneHelp:'默认中国区号 +86，无需输入。其他国家请填写以 + 和国家区号开头的完整号码。',invalidPhone:'请输入 11 位号码，或以 + 和国家区号开头的完整号码。'});
  async function signIn(event) {
    event.preventDefault();if(state.busy)return;
    const phone=phoneForRequest($('phone').value),password=$('password').value;
    if(!phone) {status('invalidPhone');return;}
    if(state.mode==='register'&&(Array.from(password).length<8||Array.from(password).length>128)){status('invalidPassword');return;}
    // The name is required at registration: it is how the family recognises a member, and it
    // is the source of that member's incoming upload folder label.
    if(state.mode==='register'&&!$('name').value.trim()){status('invalidName');return;}
    state.busy=true;$('auth-submit').disabled=true;translate();const epoch=invalidate();
    const body={phone,password,transport:'web'};
    if(state.mode==='register'){body.code=$('code').value;body.name=$('name').value.trim();}
    try {
      await request('/auth/'+state.mode,{method:'POST',body,epoch});
      if(!stale(epoch)) {$('password').value='';$('code').value='';$('name').value='';await restore();}
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
    event.preventDefault();if(state.busy||state.locked)return;
    const phone=phoneForRequest($('invite-phone').value);
    if(!phone){status('invalidPhone');return;}
    state.busy=true;const epoch=state.generation;
    const library=state.library;
    try {
      const result=await request(`/libraries/${encodeURIComponent(library)}/invitations`,{method:'POST',body:{phone},epoch});
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
  function currentLibraryName(){
    const membership=state.profile?.memberships?.find(item=>item.library_id===state.library);
    return String(membership?.name||membership?.title||membership?.library_name||$('library-select').selectedOptions[0]?.textContent||state.library||'this library');
  }
  function uploadErrorKey(error){
    if(error?.status===503)return 'uploadRestricted';
    if(error?.status===401||error?.status===403)return 'denied';
    return 'uploadReviewError';
  }
  function safeUploadPreviewURL(value,itemId){
    if(typeof value!=='string'||!value)return null;
    try{const url=new URL(value,window.location.origin);const expected=`/admin/uploads/${encodeURIComponent(String(itemId))}/preview`;return url.origin===window.location.origin&&url.pathname===expected&&url.searchParams.get('library')===state.library?url.href:null;}catch{return null;}
  }
  function enqueueUploadPreview(container,image,url){
    const queue=uploadState.previewQueue,token=queue.token;
    // A page contains at most ten cards; keep one small confirmation slot and
    // refuse anything beyond that bounded surface rather than accumulating work.
    if(queue.pending.length>=11){image.dispatchEvent(new Event('error'));return;}
    queue.pending.push({container,image,url,token});
    queueMicrotask(()=>void drainUploadPreviewQueue());
  }
  async function drainUploadPreviewQueue(){
    const queue=uploadState.previewQueue;if(queue.active)return;queue.active=true;
    try{while(queue.pending.length){
      const job=queue.pending.shift();
      if(job.token!==queue.token||!job.container.isConnected||!job.image.isConnected)continue;
      await new Promise(resolve=>{
        let done=false;const finish=()=>{if(done)return;done=true;clearTimeout(timer);job.image.onload=null;job.image.onerror=null;queue.cancel=null;resolve();};
        const timer=setTimeout(()=>{job.image.dispatchEvent(new Event('error'));finish();},30000);
        queue.cancel=()=>{finish();job.image.removeAttribute('src');};
        job.image.onload=finish;job.image.onerror=finish;job.image.src=job.url;
      });
    }}finally{queue.active=false;if(queue.pending.length)void drainUploadPreviewQueue();}
  }
  function renderUploadPreview(container,item){
    container.replaceChildren();
    const url=safeUploadPreviewURL(item.preview_url,item.id);
    const failed=()=>{container.replaceChildren();const note=document.createElement('p');note.className='upload-preview-error';note.textContent=t('uploadPreviewFailed');const retry=document.createElement('button');retry.type='button';retry.className='quiet';retry.textContent=t('uploadRetry');retry.addEventListener('click',()=>renderUploadPreview(container,item));container.append(note,retry);};
    if(!url){failed();return;}
    const image=document.createElement('img');image.className='upload-preview';image.alt=`${t('photo')} ${item.id}`;image.loading='eager';
    image.addEventListener('error',failed,{once:true});
    container.append(image);enqueueUploadPreview(container,image,url);
  }
  function openUploadDialog(item,review){
    if(state.locked||stale(uploadState.dialogEpoch))return;
    uploadState.dialogItem=item;uploadState.plans.set(item.id,String(review.plan));
    $('upload-review-copy').replaceChildren();
    const copy=document.createDocumentFragment(),line=document.createElement('span');line.textContent=`${t('approveUploadHelp')} ${currentLibraryName()}. `;copy.append(line);
    const warning=document.createElement('strong');warning.textContent=t('approveVisibility');copy.append(warning);
    const readers=document.createElement('span');readers.className='upload-reader-counts';readers.textContent=`${t('uploadReaders')}: ${Number(review.current_readers)||0} · ${t('uploadOriginalReaders')}: ${Number(review.current_original_readers)||0}`;copy.append(document.createElement('br'),readers);$('upload-review-copy').append(copy);
    $('upload-review-status').textContent='';$('upload-review-approve').textContent=t('approveUpload');
    renderUploadPreview($('upload-review-preview'),item);
    $('upload-review-dialog').showModal();$('upload-review-approve').focus();
  }
  async function reviewUpload(item){
    if(state.busy||state.locked||!item||!state.library)return;
    const epoch=state.generation;state.busy=true;$('uploads-status').textContent=t('working');
    try{
      const result=await request(libraryPath(`/admin/uploads/${encodeURIComponent(item.id)}/review`),{method:'POST',body:{},epoch});
      if(stale(epoch))return;uploadState.dialogEpoch=epoch;openUploadDialog(item,result);$('uploads-status').textContent='';
    }catch(error){if(!stale(epoch)){if(error.status===401||error.status===403)await failure(error,epoch);else $('uploads-status').textContent=t(uploadErrorKey(error));}}
    finally{state.busy=false;}
  }
  async function approveUpload(){
    const item=uploadState.dialogItem,epoch=uploadState.dialogEpoch,library=state.library,plan=item&&uploadState.plans.get(item.id);
    if(state.busy||state.locked||!item||!plan||stale(epoch))return;
    state.busy=true;$('upload-review-approve').disabled=true;$('upload-review-cancel').disabled=true;$('upload-review-close').disabled=true;
    try{
      await request(libraryPath(`/admin/uploads/${encodeURIComponent(item.id)}/approve`),{method:'POST',body:{plan},epoch});
      if(stale(epoch))return;closeUploadDialog();
      // The inbox disappearing alone leaves a stale gallery and makes approval
      // look like data loss. Return to an unfiltered first page immediately.
      storyState.search=null;$('search-text').value='';state.page=1;
      if(await loadGallery()&&library===state.library&&!state.locked){
        await loadUploads('uploadApproved');
        const card=[...$('grid').children].find(node=>node.dataset.assetId===String(item.id));
        if(card){card.scrollIntoView({block:'center'});card.focus({preventScroll:true});}
      }
    }catch(error){
      if(stale(epoch))return;
      if(error.status===409){closeUploadDialog();await loadUploads('uploadConflict');}
      else if(error.status===503||!error.status){$('upload-review-status').textContent=t('uploadUncertain');$('upload-review-approve').textContent=t('uploadRetryApproval');}
      else if(error.status===401||error.status===403)await failure(error,epoch);
      else {$('upload-review-status').textContent=t(uploadErrorKey(error));$('upload-review-approve').textContent=t('uploadRetryApproval');}
    }finally{state.busy=false;$('upload-review-approve').disabled=false;$('upload-review-cancel').disabled=false;$('upload-review-close').disabled=false;}
  }
  function closeUploadDialog(){
    const dialog=$('upload-review-dialog');if(dialog.open)dialog.close();uploadState.dialogItem=null;uploadState.dialogEpoch=0;$('upload-review-preview').replaceChildren();$('upload-review-copy').textContent='';$('upload-review-status').textContent='';$('upload-review-approve').textContent=t('approveUpload');
  }
  async function loadUploads(notice=null){
    if(state.locked||$('uploads-panel').hidden||!$('uploads-panel').open||!state.library)return;
    const epoch=state.generation,library=state.library,load=++uploadState.load;
    uploadState.dialogEpoch=epoch;$('uploads-list').replaceChildren();$('uploads-pages').hidden=true;$('uploads-status').textContent=t('uploadLoading');$('uploads-count').textContent='';
    try{
      const result=await request(libraryPath('/admin/uploads',{page:String(uploadState.page)}),{epoch});
      if(stale(epoch)||load!==uploadState.load||library!==state.library)return;
      uploadState.total=Number.isInteger(result.total)?result.total:0;uploadState.items=Array.isArray(result.items)?result.items:[];
      const pages=Math.max(1,Math.ceil(uploadState.total/10));
      if(uploadState.page>pages){uploadState.page=pages;return await loadUploads(notice);}
      $('uploads-count').textContent=result.can_review?`(${uploadState.total})`:'';if(result.can_review)$('uploads-count').setAttribute('aria-label',String(uploadState.total));
      if(!result.can_review){$('uploads-status').textContent=t('uploadRestricted');return;}
      $('uploads-status').textContent=notice?t(notice):(uploadState.total?'':t('uploadEmpty'));
      for(const item of uploadState.items){
        const card=document.createElement('article');card.className='upload-card';card.dataset.uploadId=item.id;
        const preview=document.createElement('div');preview.className='upload-card-preview';renderUploadPreview(preview,item);
        const details=document.createElement('div');details.className='upload-card-details';
        const title=document.createElement('h3');title.textContent=`${t('uploadBy')}: ${item.uploader}`;
        const meta=document.createElement('p');meta.className='fine';meta.textContent=`${String(item.created_at||'')} · ${item.width}×${item.height} · ${item.bytes} ${t('uploadBytes')}`;
        const button=document.createElement('button');button.type='button';button.className='primary';button.textContent=t('uploadReview');button.addEventListener('click',()=>void reviewUpload(item));
        details.append(title,meta,button);card.append(preview,details);$('uploads-list').append(card);
      }
      $('uploads-pages').hidden=uploadState.total===0;$('uploads-previous').disabled=uploadState.page===1;$('uploads-next').disabled=uploadState.page>=pages;$('uploads-page-label').textContent=`${t('page')} ${uploadState.page} ${t('of')} ${pages}`;
    }catch(error){if(!stale(epoch)&&load===uploadState.load){if(error.status===401||error.status===403)await failure(error,epoch);else {$('uploads-status').textContent=t(uploadErrorKey(error));$('uploads-count').textContent='';}}}
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
  // Albums this library has put away. Owner-only, and the only surface that shows them: an
  // archived album is excluded from every member-facing read, which is the point of archiving.
  // Restoring takes no revision, so there is nothing here to read back first.
  async function loadArchivedAlbums(){
    if(state.locked||$('album-archived-panel').hidden||!$('album-archived-panel').open)return;
    const epoch=state.generation,library=state.library,load=++albumState.archivedLoad;
    $('album-archived-list').replaceChildren();$('album-archived-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===albumState.archivedLoad&&library===state.library;
    try{
      const result=await request(libraryPath('/admin/albums/archived',{page:'1'}),{epoch});
      if(!current())return;
      $('album-archived-status').textContent=result.total?'':t('noArchivedAlbums');
      for(const album of result.items){
        const row=document.createElement('article');row.className='album-archived-card';row.dataset.albumId=album.id;
        const title=document.createElement('h3');title.textContent=album.title;
        row.append(title);
        row.append(storyButton('restoreAlbum',async()=>{
          if(state.busy||state.locked)return;
          try{
            await request(libraryPath(`/admin/albums/${album.id}/restore`),{method:'POST',epoch,body:{}});
            if(!current())return;
            await loadArchivedAlbums();await loadAlbums();
          }catch(error){if(current())await failure(error,epoch);}
        }));
        $('album-archived-list').append(row);
      }
    }catch(error){if(current()){$('album-archived-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  async function loadAlbums(){
    if(state.locked||!state.library)return;
    const epoch=state.generation,load=++albumState.load;
    $('album-list').replaceChildren();$('album-status').textContent=t('loading');
    try{
      const result=await request(libraryPath('/library-albums',{page:String(albumState.page)}),{epoch});
      if(stale(epoch)||load!==albumState.load)return;albumState.total=result.total;
      $('album-status').textContent=result.total?'':t('noAlbums');$('album-create').hidden=!result.can_manage;
      $('album-archived-panel').hidden=!result.can_manage;
      for(const album of result.items){
        const card=document.createElement('article');card.className='album-card';card.dataset.albumId=album.id;
        const title=document.createElement('h3');title.textContent=state.language==='zh'&&album.title_zh?album.title_zh:album.title;
        const description=document.createElement('p');description.textContent=album.description;card.append(title,description);
        if(album.needs_review){const note=document.createElement('p');note.textContent=t('albumNeedsReview');card.append(note);}
        const photos=document.createElement('div');photos.className='album-strip';
        for(const id of album.asset_ids){const button=document.createElement('button');button.type='button';button.className='quiet';const img=document.createElement('img');img.src=safeMediaURL(id,'thumbnail');img.alt=`${t('photo')} ${id}`;img.loading='lazy';button.append(img);button.addEventListener('click',async()=>{try{const detail=await request(libraryPath(`/assets/detail/${id}`),{epoch});if(!stale(epoch)&&card.isConnected)await openAsset(detail.asset,{sequence:album.asset_ids.map(id=>({id})),origin:'album'});}catch(error){await failure(error,epoch);}});photos.append(button);}
        card.append(photos);
        if(result.can_manage){
          card.append(storyButton('editAlbum',()=>editAlbum(album)));
          // Archive puts the album away without deleting anything, so a mistake is recoverable.
          card.append(storyButton('archiveAlbum',async()=>{
            if(state.busy||state.locked||!window.confirm(t('confirmArchive')))return;
            try{
              await request(libraryPath(`/admin/albums/${album.id}/archive`),{method:'POST',epoch,body:{revision:album.revision}});
              await loadAlbums();await loadArchivedAlbums();
            }catch(error){await failure(error,epoch);}
          }));
        }
        $('album-list').append(card);
      }
      $('album-pages').hidden=!result.total;$('album-previous').disabled=albumState.page===1;$('album-next').disabled=albumState.page*10>=result.total;
      $('album-page-label').textContent=`${t('page')} ${albumState.page} ${t('of')} ${Math.max(1,Math.ceil(result.total/10))}`;
    }catch(error){if(!stale(epoch)&&load===albumState.load){$('album-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  function editAlbum(album=null,restored=null){
    if(state.locked||state.busy||$('album-create').hidden)return;
    const epoch=state.generation,dialog=$('album-editor');
    const draft=restored||{account:state.profile.account_id,library:state.library,id:album?.id,revision:album?.revision,mutation_id:crypto.randomUUID(),title:album?.title||'',title_zh:album?.title_zh||'',description:album?.description||'',theme:album?.theme||'custom',ids:[...(album?.asset_ids||[])],cover_asset_id:album?.cover_asset_id||'',dirty:false,locked:false};
    albumState.draft=draft;dialog.replaceChildren();
    const current=()=>!stale(epoch)&&albumState.draft===draft&&dialog.open;
    const heading=document.createElement('h2');heading.textContent=t(draft.id?'editAlbum':'newAlbum');
    const form=document.createElement('form'),notice=document.createElement('p');notice.setAttribute('role','status');notice.id='album-editor-status';
    for(const [key,label,max] of [['title','albumTitle',160],['title_zh','albumTitleZh',160],['description','albumDescription',1000]]){
      const text=document.createElement('label');text.htmlFor='album-'+key;text.textContent=t(label);
      const input=document.createElement(key==='description'?'textarea':'input');input.id=text.htmlFor;input.value=draft[key];input.maxLength=max;input.required=key==='title';input.addEventListener('input',()=>{draft[key]=input.value;draft.dirty=true;});form.append(text,input);
    }
    const label=document.createElement('label');label.htmlFor='album-theme';label.textContent=t('albumTheme');const theme=document.createElement('select');theme.id='album-theme';
    for(const [value,en,zh] of [['custom','Our story','我们的故事'],['birthday','Birthday','生日'],['trip','Trip','旅行'],['growing_up','Growing up','成长'],['grandparents','Grandparents','祖辈时光'],['year_in_review','Year in review','年度回忆'],['seasonal','Seasonal','四季']]){const option=document.createElement('option');option.value=value;option.textContent=state.language==='zh'?zh:en;theme.append(option);}
    theme.value=draft.theme;theme.addEventListener('change',()=>{draft.theme=theme.value;draft.dirty=true;});form.append(label,theme);
    const selected=document.createElement('div');selected.id='album-selected';
    function selection(){selected.replaceChildren();for(const [index,id] of draft.ids.entries()){
      const row=document.createElement('div');row.className='album-selection';row.dataset.assetId=id;const image=document.createElement('img');image.src=safeMediaURL(id,'thumbnail');image.alt=`${t('photo')} ${id}`;row.append(image);
      const marker=document.createElement('span');marker.textContent=`${index+1} · ${id}${draft.cover_asset_id===id?' · '+t('cover'):''}`;row.append(marker);
      for(const [key,action,disabled] of [['moveUp',()=>{[draft.ids[index-1],draft.ids[index]]=[draft.ids[index],draft.ids[index-1]];},index===0],['moveDown',()=>{[draft.ids[index+1],draft.ids[index]]=[draft.ids[index],draft.ids[index+1]];},index===draft.ids.length-1],['setCover',()=>{draft.cover_asset_id=id;},draft.cover_asset_id===id],['remove',()=>{draft.ids=draft.ids.filter(value=>value!==id);if(draft.cover_asset_id===id)draft.cover_asset_id=draft.ids[0]||'';},false]]){const button=storyButton(key,()=>{if(!draft.locked&&current()){action();draft.dirty=true;selection();}});button.disabled=disabled||draft.locked;row.append(button);}selected.append(row);
    }}
    const selectedTitle=document.createElement('h3');selectedTitle.textContent=t('selectedPhotos');const pickTitle=document.createElement('h3');pickTitle.textContent=t('selectPhotos');
    const choices=document.createElement('div');choices.className='album-strip';choices.id='album-choices';const nav=document.createElement('nav');nav.className='pagination';let page=1,serial=0;
    async function pick(){const attempt=++serial;choices.replaceChildren();nav.replaceChildren();try{const result=await request(libraryPath('/assets',{page:String(page),page_size:'20'}),{epoch});if(!current()||attempt!==serial)return;
      for(const item of result.items){const button=document.createElement('button');button.type='button';button.className='quiet';button.dataset.assetId=item.id;button.setAttribute('aria-label',assetLabel(item));const img=document.createElement('img');img.src=safeMediaURL(item.id,'thumbnail');img.alt=assetLabel(item);img.loading='lazy';button.append(img);button.disabled=draft.locked;button.addEventListener('click',()=>{if(draft.locked||!current())return;if(!draft.ids.includes(item.id)&&draft.ids.length<60){draft.ids.push(item.id);draft.cover_asset_id=draft.cover_asset_id||item.id;draft.dirty=true;selection();}});choices.append(button);}
      const prev=storyButton('previous',()=>{page--;void pick();}),next=storyButton('next',()=>{page++;void pick();});prev.disabled=page===1||draft.locked;next.disabled=page*20>=result.total||draft.locked;nav.append(prev,next);
    }catch(error){if(current()){notice.textContent=t(errorStatus(error));await failure(error,epoch);}}}
    const save=document.createElement('button');save.id='album-save';save.type='submit';save.className='primary';save.textContent=t('saveAlbum');
    const close=storyButton('cancel',()=>{if(!state.busy&&(!draft.dirty||window.confirm(t('discardAlbum')))){albumState.draft=null;dialog.close();dialog.replaceChildren();}});
    form.append(selectedTitle,selected,pickTitle,choices,nav,notice,save,close);dialog.append(heading,form);if(!dialog.open)dialog.showModal();selection();void pick();
    function lock(){for(const input of form.querySelectorAll('input,textarea,select,button'))input.disabled=draft.locked;save.disabled=false;close.disabled=false;selection();}
    if(draft.locked){notice.textContent=t('albumUncertain');lock();}
    form.addEventListener('submit',async event=>{event.preventDefault();if(!current()||state.busy)return;state.busy=true;save.disabled=true;
      const body={title:draft.title,title_zh:draft.title_zh,description:draft.description,theme:draft.theme,asset_ids:draft.ids.join(','),cover_asset_id:draft.cover_asset_id,...(draft.id?{revision:draft.revision}:{mutation_id:draft.mutation_id})};
      draft.locked=true;lock();save.disabled=true;
      try{await request(libraryPath(draft.id?`/admin/albums/${draft.id}`:'/admin/albums'),{method:draft.id?'PUT':'POST',body,epoch});if(current()){albumState.draft=null;dialog.close();dialog.replaceChildren();await loadAlbums();$('album-status').textContent=t('albumSaved');}}
      catch(error){if(current()){draft.locked=![400,413,422].includes(error.status);lock();if(error.status===409){notice.textContent=t('albumChanged');save.disabled=true;}else notice.textContent=t(draft.locked?'albumUncertain':errorStatus(error));if(error.status===401||error.status===403)await failure(error,epoch);}}
      finally{state.busy=false;}
    });
  }
  $('album-editor').addEventListener('cancel',event=>{event.preventDefault();if(!state.busy&&(!albumState.draft?.dirty||window.confirm(t('discardAlbum')))){albumState.draft=null;$('album-editor').close();$('album-editor').replaceChildren();}});
  $('albums-panel').addEventListener('toggle',()=>{if($('albums-panel').open)void loadAlbums();});
  $('album-archived-panel').addEventListener('toggle',()=>{if($('album-archived-panel').open)void loadArchivedAlbums();});
  $('album-create').addEventListener('click',()=>editAlbum());
  $('album-previous').addEventListener('click',()=>{if(albumState.page>1){albumState.page--;void loadAlbums();}});
  $('album-next').addEventListener('click',()=>{if(albumState.page*10<albumState.total){albumState.page++;void loadAlbums();}});
  function personPicker({face,image,current,epoch,onSaved,status,container}){
    if(!current()||state.busy)return;
    // One picker per viewer; no previous person's selection survives opening another.
    container.querySelectorAll('.face-picker').forEach(node=>node.remove());
    const picker=document.createElement('section');picker.className='face-picker';
    const form=document.createElement('form');form.className='people-search';
    const label=document.createElement('label');label.htmlFor=`face-query-${face.id}`;label.textContent=t('findPerson');
    const input=document.createElement('input');input.id=label.htmlFor;input.type='search';input.maxLength=128;input.autocomplete='off';
    const search=document.createElement('button');search.type='submit';search.className='quiet';search.textContent=t('search');
    const results=document.createElement('div'),review=document.createElement('div'),notice=document.createElement('p');notice.setAttribute('role','status');review.className='assignment-review';
    const nav=document.createElement('nav');nav.className='pagination';
    let page=1,query='',serial=0;
    const active=()=>current()&&picker.isConnected;
    async function find(){
      const attempt=++serial;results.replaceChildren();review.replaceChildren();nav.replaceChildren();notice.textContent=t('loading');
      try{
        const found=await request(libraryPath('/admin/people',{q:query,page:String(page)}),{epoch});
        if(!active()||attempt!==serial)return;notice.textContent=found.total?t('assignmentChooseHelp'):t('peopleEmpty');
        for(const person of found.items){
          const choice=document.createElement('button');choice.type='button';choice.className='quiet person-choice';
          choice.textContent=`${person.display_name||t('unnamedPerson')} · ${person.id}`;choice.disabled=!person.can_rename;
          const option=document.createElement('div');option.className='person-choice-row';option.append(choice);
          if(!person.can_rename){const reason=document.createElement('p');reason.className='fine';reason.id=`assignment-restricted-${face.id}-${person.id}`;reason.textContent=t('assignmentRestricted');choice.setAttribute('aria-describedby',reason.id);option.append(reason);}
          choice.addEventListener('click',()=>{
            if(!active()||state.busy||attempt!==serial)return;
            const text=document.createElement('p');text.textContent=`${t('assignmentReview')}: ${person.display_name||t('unnamedPerson')} · ${person.id}?`;
            const confirm=storyButton('confirmAssignment',async()=>{
              if(!active()||state.busy||attempt!==serial)return;
              state.busy=true;confirm.disabled=true;
              try{
                await request(libraryPath(`/admin/faces/${face.id}/assignment`),{method:'POST',epoch,body:{person_id:person.id,revision:face.revision,person_revision:person.revision}});
                if(active()){await onSaved();if(!stale(epoch))status.textContent=t('assignmentSaved');}
              }catch(error){
                if(active()){
                  // Ambiguous writes require fresh server readback; never retry automatically.
                  serial++;review.replaceChildren();results.replaceChildren();nav.replaceChildren();
                  notice.textContent=t(error.status===409?'assignmentConflict':'assignmentFailed');
                  if(error.status===401||error.status===403)await failure(error,epoch);
                }
              }finally{state.busy=false;}
            });
            const preview=image.cloneNode();preview.loading='eager';
            const actions=document.createElement('div');actions.className='face-confirm';actions.append(confirm,storyButton('cancel',()=>review.replaceChildren()));
            review.replaceChildren(preview,text,actions);review.scrollIntoView({block:'nearest'});confirm.focus();
          });results.append(option);
        }
        const previous=storyButton('previous',()=>{if(!state.busy){page--;void find();}}),next=storyButton('next',()=>{if(!state.busy){page++;void find();}});
        previous.disabled=page===1;next.disabled=page*25>=found.total;
        const position=document.createElement('span');position.textContent=`${t('page')} ${page} ${t('of')} ${Math.max(1,Math.ceil(found.total/25))}`;
        nav.append(previous,position,next);
      }catch(error){if(active()&&attempt===serial){notice.textContent=t(errorStatus(error));await failure(error,epoch);}}
    }
    form.append(label,input,search);picker.append(form,notice,results,nav,review,storyButton('closeSelection',()=>picker.remove()));
    form.addEventListener('submit',event=>{event.preventDefault();if(!state.busy&&active()){query=input.value.trim();page=1;void find();}});
    void find();input.focus();
    return picker;
  }

  async function loadAssetFaces(){
    if(state.locked||$('face-panel').hidden||!storyState.asset)return;
    const epoch=state.generation,viewer=state.viewerGeneration,load=++faceState.load,asset=storyState.asset.id;
    const current=()=>!stale(epoch)&&viewer===state.viewerGeneration&&load===faceState.load&&$('viewer').open;
    $('face-list').replaceChildren();$('face-pages').hidden=true;$('face-status').textContent=t('loading');
    try{
      const result=await request(libraryPath(`/admin/assets/${asset}/faces`,{page:String(faceState.page)}),{epoch});
      if(!current())return;faceState.total=result.total;$('face-status').textContent=result.total?'':t('noFaces');
      for(const face of result.items){
        const row=document.createElement('article');row.className='face-label-card';row.dataset.faceId=face.id;
        const image=document.createElement('img');image.className='assignment-crop';image.alt=`${t('reviewFaces')} ${face.id}`;image.src=libraryPath(`/faces/${face.id}/crop`);image.loading='lazy';
        image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
        const name=document.createElement('h4');name.textContent=face.display_name||(face.person_id?`${t('unnamedPerson')} ${face.person_id}`:t('unassigned'));
        row.append(image,name);
        if(!face.can_assign){const note=document.createElement('p');note.textContent=t('assignmentUnavailable');row.append(note);}
        else row.append(storyButton('choosePerson',()=>{
          if(!current()||state.busy)return;
          // One picker per viewer; a previous selection never survives opening another.
          row.append(personPicker({face,image,current,epoch,onSaved:loadAssetFaces,status:$('face-status'),container:$('face-list')}));
        }));
        if(face.can_assign){
          async function changeFace(action,body){if(!current()||state.busy)return;state.busy=true;try{await request(libraryPath(`/admin/faces/${face.id}/${action}`),{method:'POST',body:{revision:face.revision,...body},epoch});if(current()){await loadAssetFaces();if(!stale(epoch))$('face-status').textContent=t('assignmentSaved');}}catch(error){if(current()){$('face-status').textContent=t(error.status===409?'assignmentConflict':'assignmentFailed');if(error.status===401||error.status===403)await failure(error,epoch);}}finally{state.busy=false;}}
          row.append(storyButton('newPerson',()=>{if(!current()||state.busy)return;row.querySelector('.new-person-form')?.remove();const form=document.createElement('form');form.className='new-person-form';const label=document.createElement('label');label.htmlFor=`new-person-${face.id}`;label.textContent=t('personName');const input=document.createElement('input');input.id=label.htmlFor;input.required=true;input.maxLength=128;const help=document.createElement('p');help.textContent=t('newPersonHelp');const save=document.createElement('button');save.type='submit';save.textContent=t('createAssign');form.append(label,input,help,save);form.addEventListener('submit',event=>{event.preventDefault();if(input.value.trim()&&window.confirm(`${t('createAssign')}: ${input.value.trim()}?`))void changeFace('new-person',{display_name:input.value.trim()});});row.append(form);input.focus();}));
          if(face.person_id)row.append(storyButton('unassignFace',()=>{if(window.confirm(t('confirmUnassign')))void changeFace('unassign',{});}));
        }
        $('face-list').append(row);
      }
      $('face-pages').hidden=result.total===0;$('face-previous').disabled=faceState.page===1;$('face-next').disabled=faceState.page*25>=result.total;
      $('face-page-label').textContent=`${t('page')} ${faceState.page} ${t('of')} ${Math.max(1,Math.ceil(result.total/25))}`;
    }catch(error){if(current()){$('face-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  $('face-panel').addEventListener('toggle',()=>{if($('face-panel').open){stopSlideshow();void loadAssetFaces();}});
  $('face-refresh').addEventListener('click',()=>{if(!state.busy)void loadAssetFaces();});
  $('face-previous').addEventListener('click',()=>{if(!state.busy&&faceState.page>1){faceState.page--;void loadAssetFaces();}});
  $('face-next').addEventListener('click',()=>{if(!state.busy&&faceState.page*25<faceState.total){faceState.page++;void loadAssetFaces();}});
  async function loadPeople(){
    if(state.locked||$('people-panel').hidden)return;
    const epoch=state.generation,library=state.library,load=++peopleState.load;
    $('people-list').replaceChildren();$('people-pages').hidden=true;$('people-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===peopleState.load&&library===state.library;
    try{
      const result=await request(libraryPath('/admin/people',{page:String(peopleState.page),q:peopleState.query,named:peopleState.named}),{epoch});
      if(!current())return;
      peopleState.total=result.total;$('people-status').textContent=result.total?'':t('peopleEmpty');
      for(const person of result.items){
        const row=document.createElement('article');row.className='person-card';row.dataset.personId=person.id;
        const title=document.createElement('h3');title.textContent=person.display_name||`${t('unnamedPerson')} ${person.id}`;
        const count=document.createElement('small');count.textContent=`${person.face_count} ${t('facesCount')}`;row.append(title,count);
        if(person.name_truncated){const note=document.createElement('p');note.className='fine';note.textContent=t('nameShortened');row.append(note);}
        if(person.can_rename){
          const form=document.createElement('form');form.className='person-name-form';
          const label=document.createElement('label');label.htmlFor=`person-name-${person.id}`;label.textContent=t('personName');
          const input=document.createElement('input');input.id=label.htmlFor;input.value=person.name_truncated?'':person.display_name;input.maxLength=128;input.required=true;input.autocomplete='off';
          const save=document.createElement('button');save.type='submit';save.className='quiet';save.textContent=t('saveName');
          form.append(label,input,save);row.append(form);
          form.addEventListener('submit',async event=>{
            event.preventDefault();if(!current()||state.locked||state.busy||!row.isConnected)return;
            const name=input.value.trim();if(!name)return;
            state.busy=true;save.disabled=true;input.disabled=true;
            try{
              await request(libraryPath(`/admin/people/${person.id}`),{method:'PUT',body:{display_name:name,revision:person.revision},epoch});
              if(current()){await loadPeople();if(!stale(epoch))$('people-status').textContent=t('nameSaved');}
            }catch(error){
              if(!current())return;
              if(error.status===409){await loadPeople();if(!stale(epoch))$('people-status').textContent=t('nameConflict');}
              else if(error.status===401||error.status===403)await failure(error,epoch);
              else $('people-status').textContent=t('nameSaveFailed');
            }finally{state.busy=false;save.disabled=false;input.disabled=false;}
          });
        }else{const note=document.createElement('p');note.className='fine';note.textContent=t('nameUnavailable');row.append(note);}
        const faces=document.createElement('div');faces.className='person-faces';
        const review=document.createElement('button');review.type='button';review.className='quiet';review.textContent=t('reviewFaces');
        let facePage=0;
        review.addEventListener('click',async()=>{
          if(!current()||state.locked||!row.isConnected)return;review.disabled=true;
          try{
            const result=await request(libraryPath(`/admin/people/${person.id}/faces`,{page:String(facePage+1)}),{epoch});
            if(!current()||!row.isConnected)return;facePage=result.page;
            for(const face of result.items){
              const button=document.createElement('button');button.type='button';button.className='face-review';
              const image=document.createElement('img');image.alt=`${person.display_name||t('unnamedPerson')} · ${face.id}`;
              image.src=libraryPath(`/faces/${face.id}/crop`);image.loading='lazy';
              image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
              button.append(image);faces.append(button);
              button.addEventListener('click',async()=>{
                if(!current()||state.locked||!abandonStory())return;
                try{const detail=await request(libraryPath(`/assets/detail/${face.asset_id}`),{epoch});if(current())await openAsset(detail.asset);}
                catch(error){await failure(error,epoch);}
              });
            }
            review.hidden=facePage*25>=result.total;review.textContent=t('moreFaces');
          }catch(error){await failure(error,epoch);}finally{review.disabled=false;}
        });
        row.append(faces,review);$('people-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('people-pages').hidden=result.total===0;
      $('people-previous').disabled=peopleState.page===1;$('people-next').disabled=peopleState.page>=pages;
      $('people-page-label').textContent=`${t('page')} ${peopleState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('people-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  // Member-facing people directory. Read-only by construction: the route returns a
  // name, a count and one thumbnail, so there is nothing here to submit. The owner
  // panel below is where names are actually managed.
  async function loadDirectory(){
    if(state.locked||!$('directory-panel').open)return;
    const epoch=state.generation,library=state.library,load=++directoryState.load;
    $('directory-list').replaceChildren();$('directory-pages').hidden=true;$('directory-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===directoryState.load&&library===state.library&&$('directory-panel').open;
    try{
      const result=await request(libraryPath('/people',{page:String(directoryState.page),q:directoryState.query}),{epoch});
      if(!current())return;
      directoryState.total=result.total;$('directory-status').textContent=result.total?'':t('noPeopleInLibrary');
      for(const person of result.items){
        const row=document.createElement('article');row.className='directory-card';row.dataset.personId=person.id;
        if(directoryState.person===person.id)row.classList.add('tag-selected');
        // The name is the control that opens this person's photos. The route behind it is
        // member-scoped and read-only, so there is nothing on the card to submit.
        const button=document.createElement('button');button.type='button';button.className='quiet person-name';
        button.textContent=person.display_name;
        const count=document.createElement('small');count.textContent=`${person.face_count} ${t('facesCount')}`;
        row.append(button,count);
        button.addEventListener('click',()=>{
          if(state.busy||state.locked)return;
          directoryState.person=person.id;directoryState.assetPage=1;
          for(const other of $('directory-list').children)other.classList.remove('tag-selected');
          row.classList.add('tag-selected');
          void loadPersonAssets();
        });
        // The server supplies the crop URL so the client never reconstructs one; only
        // a same-origin path is accepted, so no unexpected origin can be loaded.
        if(typeof person.thumbnail_url==='string'&&person.thumbnail_url.startsWith('/faces/')){
          const image=document.createElement('img');image.className='directory-crop';image.loading='lazy';
          image.alt=`${person.display_name} · ${t('facesCount')}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
          image.src=person.thumbnail_url;row.prepend(image);
        }
        $('directory-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('directory-pages').hidden=result.total===0;
      $('directory-previous').disabled=directoryState.page===1;$('directory-next').disabled=directoryState.page>=pages;
      $('directory-page-label').textContent=`${t('page')} ${directoryState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('directory-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  // Photos of one person, from the member-scoped route. Read-only by construction: the
  // route returns photos this library already maps and nothing about faces, so there is no
  // control here beyond opening one. An empty page keeps the total visible.
  async function loadPersonAssets(){
    if(state.locked||directoryState.person===null||!$('directory-panel').open)return;
    const epoch=state.generation,library=state.library,person=directoryState.person,load=++directoryState.assetLoad;
    $('person-assets').replaceChildren();$('person-pages').hidden=true;
    const current=()=>!stale(epoch)&&load===directoryState.assetLoad&&person===directoryState.person&&library===state.library;
    try{
      const result=await request(libraryPath(`/people/${person}/assets`,{page:String(directoryState.assetPage)}),{epoch});
      if(!current())return;
      directoryState.assetTotal=result.total;
      const heading=document.createElement('h4');heading.textContent=t('personPhotos');
      heading.append(' ',storyButton('clearPerson',()=>{
        directoryState.person=null;directoryState.assetTotal=0;$('person-assets').replaceChildren();
        $('person-pages').hidden=true;void loadDirectory();
      }));
      $('person-assets').append(heading);
      if(!result.total){const empty=document.createElement('p');empty.className='fine';empty.textContent=t('noPersonPhotos');$('person-assets').append(empty);}
      for(const asset of result.items){
        const row=document.createElement('article');row.className='person-asset-card';row.dataset.assetId=asset.id;
        // Only a same-origin thumbnail path is accepted, so no unexpected origin is loaded.
        if(typeof asset.thumbnail_url==='string'&&asset.thumbnail_url.startsWith('/assets/')){
          const image=document.createElement('img');image.className='person-asset-crop';image.loading='lazy';
          image.alt=`${t('personPhotos')} · ${asset.id}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
          image.src=asset.thumbnail_url;row.append(image);
        }
        row.append(storyButton('openPhoto',async()=>{
          if(!current()||state.locked||state.busy||!abandonStory())return;
          try{const detail=await request(libraryPath(`/assets/detail/${asset.id}`),{epoch});if(current())await openAsset(detail.asset);}
          catch(error){await failure(error,epoch);}
        }));
        $('person-assets').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('person-pages').hidden=result.total===0;
      $('person-previous').disabled=directoryState.assetPage===1;
      $('person-next').disabled=directoryState.assetPage>=pages;
      $('person-page-label').textContent=`${t('page')} ${directoryState.assetPage} ${t('of')} ${pages}`;
    }catch(error){if(current())await failure(error,epoch);}
  }
  // Exact duplicate groups in this library. Read-only by construction: the route is GET-only
  // and returns no path, filename or content hash, so there is nothing here to submit and
  // nothing to act on. It explains a duplication the member can already see in the gallery.
  async function loadDuplicates(){
    if(state.locked||!$('duplicates-panel').open)return;
    const epoch=state.generation,library=state.library,load=++duplicateState.load;
    $('duplicate-list').replaceChildren();$('duplicate-pages').hidden=true;$('duplicate-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===duplicateState.load&&library===state.library&&$('duplicates-panel').open;
    try{
      const result=await request(libraryPath('/duplicates',{page:String(duplicateState.page)}),{epoch});
      if(!current())return;
      duplicateState.total=result.total;
      $('duplicate-status').textContent=result.total?'':t('noDuplicatesInLibrary');
      for(const group of result.items){
        const row=document.createElement('article');row.className='duplicate-group';row.dataset.groupId=group.group_id;
        const title=document.createElement('h4');title.textContent=`${t('savedTimes')} ${group.copy_count}`;
        const copies=document.createElement('div');copies.className='duplicate-copies';
        for(const copy of group.copies){
          const card=document.createElement('article');card.className='duplicate-copy';card.dataset.assetId=copy.id;
          // Only a same-origin thumbnail path is accepted, so no unexpected origin is loaded.
          if(typeof copy.thumbnail_url==='string'&&copy.thumbnail_url.startsWith('/assets/')){
            const image=document.createElement('img');image.className='duplicate-crop';image.loading='lazy';
            image.alt=`${t('duplicatesInLibrary')} · ${copy.id}`;
            image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
            image.src=copy.thumbnail_url;card.append(image);
          }
          card.append(storyButton('openPhoto',async()=>{
            if(!current()||state.locked||state.busy||!abandonStory())return;
            try{const detail=await request(libraryPath(`/assets/detail/${copy.id}`),{epoch});if(current())await openAsset(detail.asset);}
            catch(error){await failure(error,epoch);}
          }));
          copies.append(card);
        }
        row.append(title,copies);$('duplicate-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('duplicate-pages').hidden=result.total===0;
      $('duplicate-previous').disabled=duplicateState.page===1;$('duplicate-next').disabled=duplicateState.page>=pages;
      $('duplicate-page-label').textContent=`${t('page')} ${duplicateState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('duplicate-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  // Member-facing tag catalog. Read-only by construction: both routes are GET-only and
  // the server returns a name plus a count of this library's own photos, so there is no
  // add, rename or remove control here and nothing to submit.
  async function loadTags(){
    if(state.locked||!$('tags-panel').open)return;
    const epoch=state.generation,library=state.library,load=++tagState.load;
    $('tag-list').replaceChildren();$('tag-pages').hidden=true;$('tag-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===tagState.load&&library===state.library&&$('tags-panel').open;
    try{
      const result=await request(libraryPath('/tags',{page:String(tagState.page),q:tagState.query}),{epoch});
      if(!current())return;
      tagState.total=result.total;$('tag-status').textContent=result.total?'':t('noTagsInLibrary');
      for(const tag of result.items){
        const row=document.createElement('article');row.className='tag-card';row.dataset.tagId=tag.id;
        if(tagState.open===tag.id)row.classList.add('tag-selected');
        const button=document.createElement('button');button.type='button';button.className='quiet tag-name';
        button.textContent=tag.name;
        const count=document.createElement('small');count.textContent=`${tag.asset_count} ${t('assetsCount')}`;
        row.append(button,count);
        button.addEventListener('click',()=>{
          if(state.busy||state.locked)return;
          tagState.tag=tag.id;tagState.tagPage=1;
          for(const other of $('tag-list').children)other.classList.remove('tag-selected');
          row.classList.add('tag-selected');
          void loadTagAssets();
        });
        $('tag-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('tag-pages').hidden=result.total===0;
      $('tag-previous').disabled=tagState.page===1;$('tag-next').disabled=tagState.page>=pages;
      $('tag-page-label').textContent=`${t('page')} ${tagState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('tag-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  async function loadTagAssets(){
    if(state.locked||tagState.tag===null||!$('tags-panel').open)return;
    const epoch=state.generation,library=state.library,tag=tagState.tag,load=++tagState.tagLoad;
    $('tag-assets').replaceChildren();
    const current=()=>!stale(epoch)&&load===tagState.tagLoad&&tag===tagState.tag&&library===state.library;
    try{
      const result=await request(libraryPath(`/tags/${tag}/assets`,{page:String(tagState.tagPage)}),{epoch});
      if(!current())return;
      tagState.tagTotal=result.total;
      const heading=document.createElement('h4');heading.textContent=t('tagAssets');
      heading.append(' ',storyButton('clearTag',()=>{
        tagState.tag=null;tagState.tagTotal=0;tagState.open=null;$('tag-assets').replaceChildren();void loadTags();
      }));
      $('tag-assets').append(heading);
      if(!result.total){const empty=document.createElement('p');empty.className='fine';empty.textContent=t('noTaggedAssets');$('tag-assets').append(empty);}
      for(const asset of result.items){
        const row=document.createElement('article');row.className='tag-asset-card';row.dataset.assetId=asset.id;
        // Only a same-origin thumbnail path is accepted, so no unexpected origin is loaded.
        if(typeof asset.thumbnail_url==='string'&&asset.thumbnail_url.startsWith('/assets/')){
          const image=document.createElement('img');image.className='tag-asset-crop';image.loading='lazy';
          image.alt=`${t('tagAssets')} · ${asset.id}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
          image.src=asset.thumbnail_url;row.append(image);
        }
        row.append(storyButton('openPhoto',async()=>{
          if(!current()||state.locked||state.busy||!abandonStory())return;
          try{const detail=await request(libraryPath(`/assets/detail/${asset.id}`),{epoch});if(current())await openAsset(detail.asset);}
          catch(error){await failure(error,epoch);}
        }));
        $('tag-assets').append(row);
      }
    }catch(error){if(current())await failure(error,epoch);}
  }
  // Date/media narrowing over the reviewed discovery index. The panel is offered only
  // when the deployment has opted in with an index artifact: with no runtime the routes
  // answer 503, and the filter simply stays hidden rather than appearing broken. Absence
  // of the filter is a deployment state, not an error the member can act on.
  async function openDiscovery(){
    if(state.locked||!state.library)return;
    const epoch=state.generation,library=state.library,load=++discoveryState.facetLoad;
    const current=()=>!stale(epoch)&&load===discoveryState.facetLoad&&library===state.library;
    try{
      const result=await request(`/libraries/${encodeURIComponent(library)}/discovery/v1/facets?`+
      new URLSearchParams({facet:'locations',page:'1',page_size:'24'}),{epoch});
      if(!current())return;
      if(!Array.isArray(result.enabled)||!result.enabled.includes('media')){$('discovery-panel').hidden=true;return;}
      discoveryState.binding=result.binding;
      discoveryState.page=1;discoveryState.fingerprint=null;
      discoveryState.searchLoad++;
      const bounds=result.captured_date_bounds||{};
      // Both inputs carry the same captured range as native bounds; the server
      // independently refuses an inverted or malformed range, so neither side is
      // load-bearing on its own.
      const low=typeof bounds.from==='string'?bounds.from:'',high=typeof bounds.to==='string'?bounds.to:'';
      for(const id of ['discovery-from','discovery-to']){$(id).min=low;$(id).max=high;}
      $('discovery-panel').hidden=false;
      discoveryState.placesAvailable=Array.isArray(result.enabled)&&result.enabled.includes('locations');
      if(discoveryState.placesAvailable){
        discoveryState.placeTotal=Number(result.total)||0;
        discoveryState.places=Array.isArray(result.items)?result.items:[];
        discoveryState.placePage=1;
        renderDiscoveryPlaces();
      }else{$('discovery-places').hidden=true;$('discovery-places-status').textContent=t('placesUnavailable');}
      if(!discoveryState.applied)$('discovery-status').textContent=t('discoveryHint');
    }catch(error){if(current()){$('discovery-panel').hidden=false;$('discovery-places').hidden=false;discoveryState.binding=null;discoveryState.applied=false;discoveryState.appliedFilters=null;discoveryState.fingerprint=null;$('discovery-list').replaceChildren();$('discovery-pages').hidden=true;$('discovery-status').textContent=error&&error.status===409?t('discoveryChanged'):'';$('discovery-places-status').textContent=t('placesUnavailable');const retry=document.createElement('button');retry.type='button';retry.className='quiet';retry.textContent=t('placesRetry');retry.addEventListener('click',()=>void openDiscovery());$('discovery-places-status').append(' ',retry);}}
  }
  function renderDiscoveryPlaces(){
    if(!discoveryState.placesAvailable)return;
    const list=$('discovery-place-list');list.replaceChildren();
    if(!discoveryState.placeTotal){$('discovery-places').hidden=false;$('discovery-places-status').textContent=t('placesNone');$('discovery-place-pages').hidden=true;return;}
    $('discovery-places').hidden=false;$('discovery-places-status').textContent='';
    for(const place of discoveryState.places){
      const button=document.createElement('button');button.type='button';button.className='place-choice';button.dataset.placeId=String(place.id);button.setAttribute('aria-pressed',String(discoveryState.selectedPlaces.has(String(place.id))));
      const label=document.createElement('span');label.textContent=String(place.label||place.id);const count=document.createElement('small');count.textContent=`${Number(place.asset_count)||0} ${t('placesCount')}`;button.append(label,count);
      button.addEventListener('click',()=>{if(state.busy||state.locked)return;const id=String(place.id);if(discoveryState.selectedPlaces.has(id))discoveryState.selectedPlaces.delete(id);else if(discoveryState.selectedPlaces.size<20)discoveryState.selectedPlaces.add(id);else{$('discovery-status').textContent=t('placesLimit');return;}button.setAttribute('aria-pressed',String(discoveryState.selectedPlaces.has(id)));});list.append(button);
    }
    const pages=Math.max(1,Math.ceil(discoveryState.placeTotal/24));$('discovery-place-pages').hidden=pages<=1;$('discovery-place-previous').disabled=discoveryState.placePage===1;$('discovery-place-next').disabled=discoveryState.placePage>=pages;$('discovery-place-page-label').textContent=`${t('page')} ${discoveryState.placePage} ${t('of')} ${pages}`;
  }
  async function loadDiscoveryPlaces(){
    if(state.locked||!state.library||!discoveryState.placesAvailable)return;
    const epoch=state.generation,library=state.library,load=++discoveryState.facetLoad;const current=()=>!stale(epoch)&&load===discoveryState.facetLoad&&library===state.library;
    $('discovery-place-list').replaceChildren();$('discovery-place-pages').hidden=true;$('discovery-places-status').textContent=t('placesLoading');
    try{const result=await request(`/libraries/${encodeURIComponent(library)}/discovery/v1/facets?`+new URLSearchParams({facet:'locations',page:String(discoveryState.placePage),page_size:'24',binding:discoveryState.binding}),{epoch});if(!current())return;discoveryState.placeTotal=Number(result.total)||0;discoveryState.places=Array.isArray(result.items)?result.items:[];renderDiscoveryPlaces();}
    catch(error){if(current()){if(error&&error.status===409){discoveryState.binding=null;discoveryState.placePage=1;void openDiscovery();return;}$('discovery-places-status').textContent=t('placesUnavailable');const retry=document.createElement('button');retry.type='button';retry.className='quiet';retry.textContent=t('placesRetry');retry.addEventListener('click',()=>void loadDiscoveryPlaces());$('discovery-places-status').append(' ',retry);}}
  }
  async function loadDiscovery(applyDraft=false){
    if(state.locked||!discoveryState.binding)return;
    if(applyDraft){
      const from=$('discovery-from').value,to=$('discovery-to').value;
      if(from&&to&&from>to){$('discovery-status').textContent=t('discoveryRange');return;}
      const filters={};
      if($('discovery-media').value!=='all')filters.media=[$('discovery-media').value];
      if(discoveryState.selectedPlaces.size>20){$('discovery-status').textContent=t('placesLimit');return;}
      if(discoveryState.selectedPlaces.size)filters.locations=[...discoveryState.selectedPlaces];
      if(from||to)filters.date={from:from||null,to:to||null};
      if(!Object.keys(filters).length){
        discoveryState.applied=false;discoveryState.appliedFilters=null;discoveryState.fingerprint=null;
        $('discovery-list').replaceChildren();$('discovery-pages').hidden=true;
        $('discovery-status').textContent=t('discoveryHint');return;
      }
      discoveryState.appliedFilters=JSON.parse(JSON.stringify(filters));
      discoveryState.applied=true;discoveryState.page=1;discoveryState.fingerprint=null;
    }
    if(!discoveryState.appliedFilters)return;
    const epoch=state.generation,library=state.library,load=++discoveryState.searchLoad;
    const current=()=>!stale(epoch)&&load===discoveryState.searchLoad&&library===state.library;
    $('discovery-list').replaceChildren();$('discovery-pages').hidden=true;$('discovery-status').textContent=t('loading');
    const body={binding:discoveryState.binding,filters:discoveryState.appliedFilters,page:discoveryState.page,page_size:24,
      fingerprint:discoveryState.page>1?discoveryState.fingerprint:null};
    try{
      const result=await request(`/libraries/${encodeURIComponent(library)}/discovery/v1/search`,{method:'POST',body,epoch});
      if(!current())return;
      discoveryState.fingerprint=result.fingerprint;discoveryState.total=result.total;
      $('discovery-status').textContent=result.total?'':t('discoveryNone');
      for(const asset of result.items){
        const row=document.createElement('article');row.className='tag-asset-card';row.dataset.assetId=asset.id;
        if(typeof asset.thumbnail_url==='string'&&asset.thumbnail_url.startsWith('/assets/')){
          const image=document.createElement('img');image.className='tag-asset-crop';image.loading='lazy';
          image.alt=`${t('discoveryResult')} · ${asset.id}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
          image.src=asset.thumbnail_url;row.append(image);
        }
        row.append(storyButton('openPhoto',async()=>{
          if(!current()||state.locked||state.busy||!abandonStory())return;
          try{const detail=await request(libraryPath(`/assets/detail/${asset.id}`),{epoch});if(current())await openAsset(detail.asset);}
          catch(error){await failure(error,epoch);}
        }));
        $('discovery-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/24));$('discovery-pages').hidden=result.total===0;
      $('discovery-previous').disabled=discoveryState.page===1;$('discovery-next').disabled=discoveryState.page>=pages;
      $('discovery-page-label').textContent=`${discoveryState.page} / ${pages}`;
    }catch(error){
      if(!current())return;
      if(error&&error.status===409){
        // A stale snapshot is refused, never answered from older data. Stop offering
        // results rather than showing a list the service no longer stands behind.
        discoveryState.applied=false;discoveryState.appliedFilters=null;discoveryState.binding=null;discoveryState.fingerprint=null;
        $('discovery-list').replaceChildren();$('discovery-pages').hidden=true;
        $('discovery-status').textContent=t('discoveryChanged');return;
      }
      await failure(error,epoch);
    }
  }
  async function loadUnassignedFaces(){
    if(state.locked||$('people-panel').hidden||!$('unassigned-section').open)return;
    const epoch=state.generation,library=state.library,load=++unassignedState.load;
    const current=()=>!stale(epoch)&&load===unassignedState.load&&library===state.library&&$('people-panel').open;
    $('unassigned-list').replaceChildren();$('unassigned-pages').hidden=true;$('unassigned-status').textContent=t('loading');
    try{
      const result=await request(libraryPath('/admin/faces',{page:String(unassignedState.page)}),{epoch});
      if(!current())return;
      unassignedState.total=result.total;$('unassigned-status').textContent=result.total?'':t('noUnassignedFaces');
      for(const face of result.items){
        const row=document.createElement('article');row.className='unassigned-card';row.dataset.faceId=face.id;
        const image=document.createElement('img');image.className='assignment-crop';image.alt=`${t('unassigned')} ${face.id}`;image.src=libraryPath(`/faces/${face.id}/crop`);image.loading='lazy';
        image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
        const source=document.createElement('h4');source.textContent=`${t('unassigned')} · ${t('sourcePhoto')} ${face.asset_id}`;
        row.append(image,source);
        // Assigning here keeps one assignment path: the same picker, revision and
        // conflict rules as the per-photo review. The row leaves on the next load.
        row.append(storyButton('openPhoto',async()=>{
          if(!current()||state.locked||state.busy||!abandonStory())return;
          try{const detail=await request(libraryPath(`/assets/detail/${face.asset_id}`),{epoch});if(current())await openAsset(detail.asset);}
          catch(error){await failure(error,epoch);}
        }));
        row.append(storyButton('choosePerson',()=>{
          if(!current()||state.busy)return;
          row.append(personPicker({face,image,current,epoch,onSaved:loadUnassignedFaces,status:$('unassigned-status'),container:$('unassigned-list')}));
        }));
        $('unassigned-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('unassigned-pages').hidden=result.total===0;
      $('unassigned-previous').disabled=unassignedState.page===1;$('unassigned-next').disabled=unassignedState.page>=pages;
      $('unassigned-page-label').textContent=`${t('page')} ${unassignedState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('unassigned-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  $('directory-panel').addEventListener('toggle',()=>{if($('directory-panel').open)void loadDirectory();});
  $('directory-search').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;directoryState.query=$('directory-query').value.trim();directoryState.page=1;void loadDirectory();});
  $('directory-previous').addEventListener('click',()=>{if(!state.busy&&directoryState.page>1){directoryState.page--;void loadDirectory();}});
  $('directory-next').addEventListener('click',()=>{if(!state.busy&&directoryState.page*25<directoryState.total){directoryState.page++;void loadDirectory();}});
  $('person-previous').addEventListener('click',()=>{if(!state.busy&&directoryState.assetPage>1){directoryState.assetPage--;void loadPersonAssets();}});
  $('person-next').addEventListener('click',()=>{if(!state.busy&&directoryState.assetPage*25<directoryState.assetTotal){directoryState.assetPage++;void loadPersonAssets();}});
  $('tags-panel').addEventListener('toggle',()=>{if($('tags-panel').open)void loadTags();});
  $('duplicates-panel').addEventListener('toggle',()=>{if($('duplicates-panel').open)void loadDuplicates();});
  $('duplicate-previous').addEventListener('click',()=>{if(!state.busy&&duplicateState.page>1){duplicateState.page--;void loadDuplicates();}});
  $('duplicate-next').addEventListener('click',()=>{if(!state.busy&&duplicateState.page*25<duplicateState.total){duplicateState.page++;void loadDuplicates();}});
  $('tag-search').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;tagState.query=$('tag-query').value.trim();tagState.page=1;void loadTags();});
  $('tag-previous').addEventListener('click',()=>{if(!state.busy&&tagState.page>1){tagState.page--;void loadTags();}});
  $('tag-next').addEventListener('click',()=>{if(!state.busy&&tagState.page*25<tagState.total){tagState.page++;void loadTags();}});
  $('discovery-panel').addEventListener('toggle',async()=>{
    if(!$('discovery-panel').open)return;
    await openDiscovery();
    if(discoveryState.applied)void loadDiscovery();
  });
  $('discovery-form').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;void loadDiscovery(true);});
  $('discovery-clear').addEventListener('click',()=>{if(state.busy||state.locked)return;$('discovery-media').value='all';$('discovery-from').value='';$('discovery-to').value='';discoveryState.selectedPlaces.clear();document.querySelectorAll('.place-choice').forEach(button=>button.setAttribute('aria-pressed','false'));void loadDiscovery(true);});
  $('discovery-place-previous').addEventListener('click',()=>{if(!state.busy&&discoveryState.placePage>1){discoveryState.placePage--;void loadDiscoveryPlaces();}});
  $('discovery-place-next').addEventListener('click',()=>{if(!state.busy&&discoveryState.placePage*24<discoveryState.placeTotal){discoveryState.placePage++;void loadDiscoveryPlaces();}});
  $('discovery-previous').addEventListener('click',()=>{if(!state.busy&&discoveryState.page>1){discoveryState.page--;void loadDiscovery();}});
  $('discovery-next').addEventListener('click',()=>{if(!state.busy&&discoveryState.page*24<discoveryState.total){discoveryState.page++;void loadDiscovery();}});
  $('people-panel').addEventListener('toggle',()=>{if($('people-panel').open){void loadPeople();if($('unassigned-section').open)void loadUnassignedFaces();}});
  $('people-search').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;peopleState.query=$('people-query').value.trim();peopleState.page=1;void loadPeople();});
  $('people-named').addEventListener('change',()=>{if(state.busy||state.locked)return;peopleState.named=$('people-named').value;peopleState.page=1;void loadPeople();});
  $('people-previous').addEventListener('click',()=>{if(!state.busy&&peopleState.page>1){peopleState.page--;void loadPeople();}});
  $('people-next').addEventListener('click',()=>{if(!state.busy&&peopleState.page*25<peopleState.total){peopleState.page++;void loadPeople();}});
  $('unassigned-section').addEventListener('toggle',()=>{if($('unassigned-section').open)void loadUnassignedFaces();});
  $('unassigned-previous').addEventListener('click',()=>{if(!state.busy&&unassignedState.page>1){unassignedState.page--;void loadUnassignedFaces();}});
  $('unassigned-next').addEventListener('click',()=>{if(!state.busy&&unassignedState.page*25<unassignedState.total){unassignedState.page++;void loadUnassignedFaces();}});
  const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('photohouse-session'):null;
  if(channel)channel.onmessage=()=>{if(!state.locked&&!state.busy){suspendDraft();if(document.hidden)invalidate();else void restoreWithDraft();}};
  $('auth-form').addEventListener('submit',event=>{void signIn(event);});
  $('login-tab').addEventListener('click',()=>setMode('login'));
  $('register-tab').addEventListener('click',()=>setMode('register'));
  $('logout').addEventListener('click',()=>{void signOut();});
  $('refresh').addEventListener('click',()=>{if(!state.locked&&abandonStory()){state.page=1;void restore();}});
  $('library-select').addEventListener('change',()=>{if(state.locked||!abandonStory()){$('library-select').value=state.library||'';return;}storyState.search=null;storyState.suspended=null;$('search-text').value='';peopleState.page=1;peopleState.query='';$('people-query').value='';state.library=$('library-select').value;state.page=1;state.memberPage=1;uploadState.page=1;void restore();});
  $('previous').addEventListener('click',()=>{if(state.page>1){state.page--;void loadGallery();}});
  $('next').addEventListener('click',()=>{if(state.page*24<state.total){state.page++;void loadGallery();}});
  $('page-jump').addEventListener('submit',event=>{
    event.preventDefault();
    if(state.locked||!abandonStory())return;
    const pages=Math.max(1,Math.ceil(state.total/24)),value=Number($('page-input').value);
    if(!Number.isInteger(value)||value<1||value>pages){status('pageRange');return;}
    if(value===state.page){status('');return;}
    state.page=value;void loadGallery();
  });
  $('members-panel').addEventListener('toggle',()=>{if($('members-panel').open)void loadMembers();});
  $('member-previous').addEventListener('click',()=>{if(state.memberPage>1){state.memberPage--;void loadMembers();}});
  $('member-next').addEventListener('click',()=>{if(state.memberPage*25<state.memberTotal){state.memberPage++;void loadMembers();}});
  $('uploads-open').addEventListener('click',()=>{if(state.locked||state.busy)return;$('uploads-panel').open=true;$('uploads-panel').scrollIntoView({block:'start'});$('uploads-panel').querySelector('summary').focus();});
  $('uploads-panel').addEventListener('toggle',()=>{if($('uploads-panel').open)void loadUploads();});
  $('uploads-refresh').addEventListener('click',()=>{if(!state.busy&&!state.locked){uploadState.page=1;void loadUploads();}});
  $('uploads-previous').addEventListener('click',()=>{if(!state.busy&&uploadState.page>1){uploadState.page--;void loadUploads();}});
  $('uploads-next').addEventListener('click',()=>{if(!state.busy&&uploadState.page*10<uploadState.total){uploadState.page++;void loadUploads();}});
  $('upload-review-close').addEventListener('click',closeUploadDialog);
  $('upload-review-cancel').addEventListener('click',closeUploadDialog);
  $('upload-review-approve').addEventListener('click',()=>void approveUpload());
  $('upload-review-dialog').addEventListener('cancel',event=>{event.preventDefault();if(!state.busy)closeUploadDialog();});
  $('close-viewer').addEventListener('click',()=>{if(abandonStory())closeViewer();});
  $('view-previous').addEventListener('click',()=>void movePhoto(-1));$('view-next').addEventListener('click',()=>void movePhoto(1));
  $('view-play').addEventListener('click',()=>{if(sequenceState.playing){stopSlideshow();return;}if(state.busy||storyState.busy||storyState.dirty||!$('story-form').hidden||$('face-panel').open){$('view-quality').textContent=t('viewQuality')+' '+t('viewEditing');return;}sequenceState.playing=true;updateSequence();scheduleSlideshow();});
  $('view-interval').addEventListener('change',scheduleSlideshow);
  $('viewer-filmstrip').addEventListener('click',event=>{
    const button=event.target.closest('[data-viewer-index]');
    if(!button||state.locked||sequenceState.busy)return;
    const index=Number(button.dataset.viewerIndex);
    if(!Number.isInteger(index)||index===sequenceState.index)return;
    if(!abandonStory())return;
    stopSlideshow();
    const {items,origin}=sequenceState;
    if(index<0||index>=items.length)return;
    void openAsset(items[index],{sequence:items,origin,advance:true});
  });
  for(const mode of ['fit','width','height','actual'])$('view-'+mode).addEventListener('click',()=>fitPhoto(mode));
  $('view-in').addEventListener('click',()=>zoomPhoto(1.25));$('view-out').addEventListener('click',()=>zoomPhoto(0.8));
  $('view-fullscreen').addEventListener('click',()=>void fullscreenPhoto());
  document.addEventListener('fullscreenchange',()=>{
    const full=document.fullscreenElement===$('photo-viewer');
    $('view-fullscreen').textContent=t(full?'viewExitFullscreen':'viewFullscreen');
    if(full&&$('photo-viewer').hidden){void document.exitFullscreen().catch(()=>{});return;}
    if(photoState.image)fitPhoto();
  });
  const photoStage=$('viewer-media');
  new ResizeObserver(()=>{if(photoState.image)fitPhoto();}).observe(photoStage);
  photoStage.addEventListener('wheel',event=>{if(!photoState.image?.naturalWidth)return;event.preventDefault();const box=photoStage.getBoundingClientRect();const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?photoStage.clientHeight:1);zoomPhoto(Math.exp(-Math.max(-200,Math.min(200,delta))*0.003),{x:event.clientX-box.left,y:event.clientY-box.top});},{passive:false});
  photoStage.addEventListener('pointerdown',event=>{if(event.button!==0||!photoState.image?.naturalWidth||photoState.drag)return;event.preventDefault();photoStage.focus({preventScroll:true});photoStage.setPointerCapture(event.pointerId);photoState.drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:photoStage.scrollLeft,top:photoStage.scrollTop};photoStage.classList.add('dragging');});
  photoStage.addEventListener('pointermove',event=>{const drag=photoState.drag;if(drag?.id!==event.pointerId)return;photoStage.scrollLeft=drag.left+drag.x-event.clientX;photoStage.scrollTop=drag.top+drag.y-event.clientY;});
  function endPhotoDrag(event){if(photoState.drag?.id!==event.pointerId)return;photoState.drag=null;photoStage.classList.remove('dragging');if(photoStage.hasPointerCapture(event.pointerId))photoStage.releasePointerCapture(event.pointerId);}
  for(const event of ['pointerup','pointercancel','lostpointercapture'])photoStage.addEventListener(event,endPhotoDrag);
  photoStage.addEventListener('keydown',event=>{if(event.ctrlKey||event.metaKey||event.altKey)return;const actions={'+':()=>zoomPhoto(1.25),'=':()=>zoomPhoto(1.25),'-':()=>zoomPhoto(0.8),'0':()=>fitPhoto('fit'),'1':()=>fitPhoto('actual'),ArrowLeft:()=>{photoStage.scrollLeft-=60;},ArrowRight:()=>{photoStage.scrollLeft+=60;},ArrowUp:()=>{photoStage.scrollTop-=60;},ArrowDown:()=>{photoStage.scrollTop+=60;}};if(actions[event.key]){event.preventDefault();actions[event.key]();}});
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
  window.addEventListener('beforeunload',event=>{if(storyState.dirty||albumState.draft?.dirty){event.preventDefault();event.returnValue='';}});
  window.addEventListener('pagehide',()=>{invalidate();$('password').value='';$('code').value='';});
  window.addEventListener('pageshow',event=>{if(event.persisted&&!state.locked&&!state.busy)void restoreWithDraft();});
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){
      suspendDraft();
      invalidate();
    }else if(!state.busy&&!state.locked)void restoreWithDraft();
  });
  setMode('login');status('checking');void restore();
})();
