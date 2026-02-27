const state = {
  activeTab: "library",
  selectedAsset: null,
  persons: [],
  namedPersons: [],
  showUnnamedPeople: false,
  geoMap: null,
  geoLayer: null,
  mapLoaded: false,
  libraryViewItems: [],
  assetMap: new Map(),
  inspectorOriginTab: "library",
  lang: "en",
  libraryPager: {
    kind: "latest",
    mode: "path",
    q: "",
    media: "all",
    tags: [],
    page: 1,
    pageSize: 120,
    total: 0,
    shown: 0,
  },
  personAssetsPager: {
    personId: null,
    page: 1,
    pageSize: 120,
    total: 0,
    shown: 0,
  },
  unassignedFacesPager: {
    page: 1,
    pageSize: 120,
    total: 0,
    shown: 0,
  },
  tagsPager: {
    q: "",
    source: "all",
    page: 1,
    pageSize: 200,
    total: 0,
    shown: 0,
  },
  tagsAssetsPager: {
    tagId: null,
    tagName: "",
    page: 1,
    pageSize: 120,
    total: 0,
    shown: 0,
    media: "all",
    source: "all",
  },
  voiceBusy: false,
};

const qs = (id) => document.getElementById(id);

const I18N = {
  en: {
    app_title: "VLM Photo House",
    subtitle: "Faces, captions, videos, and search in one control surface.",
    voice_command: "Voice Command",
    voice_recording: "Listening...",
    voice_processing: "Processing...",
    voice_not_supported: "Voice capture is not supported in this browser",
    voice_denied: "Microphone permission denied",
    voice_transcribe_failed: "Voice transcription failed: {error}",
    voice_command_failed: "Voice command failed: {error}",
    voice_no_transcript: "Could not hear speech clearly",
    voice_heard: "Heard: {text}",
    voice_person_opened: "Opened {name} photos ({total})",
    voice_person_not_found: "No person matched {name}",
    refresh: "Refresh",
    api_docs: "API Docs",
    assets: "Assets",
    captions: "Captions",
    faces: "Faces",
    people: "People",
    tags_total: "Tag Links",
    tagged_assets: "Tagged Assets",
    tasks_pending: "Tasks Pending",
    health: "Health",
    tab_library: "Library",
    tab_people: "People",
    tab_tags: "Tags",
    tab_map: "Map",
    tab_tasks: "Tasks",
    tab_admin: "Admin",
    search: "Search",
    mode: "Mode",
    mode_path: "Path",
    mode_caption: "Caption",
    mode_smart: "Smart",
    mode_person: "Person Name",
    query: "Query",
    query_ph: "Type query text...",
    tags_for_smart: "Tags (for smart mode)",
    tags_for_smart_ph: "family, beach, sunset",
    media: "Media",
    media_all: "All",
    media_image: "Image",
    media_video: "Video",
    run_search: "Run Search",
    browse_latest: "Browse Latest",
    results: "Results",
    inspector: "Inspector",
    asset_empty: "Select any result card to inspect captions, tags, and faces.",
    regenerate: "Regenerate",
    tags: "Tags",
    tags_input_ph: "comma separated tags",
    add_tags: "Add Tags",
    person_assets: "Person Assets",
    person_assets_meta_default: "Select a person to view related assets.",
    unassigned_faces: "Unassigned Faces",
    show_unnamed_clusters: "Show unnamed clusters",
    geo_map: "Geo Map",
    points: "Points",
    refresh_map: "Refresh Map",
    map_loading: "Loading map data...",
    task_queue: "Task Queue",
    id: "ID",
    type: "Type",
    state: "State",
    progress: "Progress",
    retry: "Retry",
    error: "Error",
    action: "Action",
    metrics: "Metrics",
    actions: "Actions",
    rebuild_vector_index: "Rebuild Vector Index",
    trigger_reclustering: "Trigger Reclustering",
    ingest_root_ph: "E:\\01_INCOMING",
    ingest_scan: "Ingest Scan",
    admin_maintenance_hint: "Use this for controlled maintenance operations from browser.",
    caption_lvface: "Caption/LVFace",
    back_to_results: "Back",
    fullscreen: "Full Screen",
    close_preview: "Close",
    status_ok: "OK",
    status_degraded: "DEGRADED",
    no_thumbnail: "No thumbnail",
    dashboard_refresh_failed: "Dashboard refresh failed: {error}",
    latest_assets_meta: "Latest assets: {shown} shown of {total}",
    library_load_failed: "Library load failed: {error}",
    caption_mode_needs_text: "Caption mode needs text",
    person_mode_needs_name: "Person mode needs a name",
    search_results_meta: "Mode: {mode} | Results: {count}",
    search_results_meta_paged: "Mode: {mode} | Results: {shown}/{total}",
    search_failed: "Search failed: {error}",
    asset_not_found: "Asset #{id} not found",
    asset_prefix: "Asset #{id}",
    unknown_path: "(unknown path)",
    inspector_load_failed: "Inspector load failed: {error}",
    map_lib_failed: "Map library failed to load.",
    map_showing_meta: "Showing {shown} of {total} geo-tagged assets ({media}).",
    map_no_points: "No GPS points found for this filter.",
    map_load_failed: "Map load failed: {error}",
    popup_open_asset: "Open Asset",
    popup_image: "image",
    popup_video: "video",
    no_captions: "No captions yet.",
    caption_unknown_model: "unknown",
    edited_flag: "edited={value}",
    caption_save: "Save",
    caption_delete: "Delete",
    no_tags: "No tags.",
    new_person_name_ph: "New person name",
    create_person: "Create Person",
    create_and_assign: "Create + Assign",
    assign_to_person: "Assign to person...",
    current_person: "Current: Person {id}",
    person_fallback: "Person {id}",
    new_person: "+ New Person",
    not_face_delete: "Not Face (Delete detection)",
    no_face_detections: "No face detections for this asset.",
    label_none: "label=(none)",
    label_line: "label={source}{score}",
    label_score: " score={score}",
    assign: "Assign",
    not_face: "Not Face",
    face_prefix: "Face #{id}",
    face_asset_prefix: "Face #{face}, asset #{asset}",
    person_stats: "id={id} | faces={count}",
    no_persons: "No persons yet.",
    people_hint_all: "Showing named people and unnamed clusters.",
    people_hint_named: "Showing named people only. Enable \"Show unnamed clusters\" if needed.",
    display_name_ph: "Display name",
    save_name: "Save Name",
    view_assets: "View Assets",
    person_assets_meta: "Person {id}: {count} assets",
    person_assets_meta_paged: "Person {id}: showing {shown}/{total}",
    no_unassigned_faces: "No unassigned faces.",
    people_load_failed: "People load failed: {error}",
    person_assets_load_failed: "Person assets load failed: {error}",
    unassigned_faces_load_failed: "Unassigned faces load failed: {error}",
    task_meta: "Total={total} | pending={pending} | running={running} | failed={failed} | dead={dead}",
    task_meta_with_page:
      "Total={total} | pending={pending} | running={running} | failed={failed} | dead={dead} | showing={shown}",
    usage_cpu: "CPU",
    usage_memory: "Memory",
    usage_gpu: "GPU {index}",
    usage_no_gpu: "No GPU metrics",
    usage_unavailable: "Unavailable",
    usage_util_mem: "util {util}% | mem {used}/{total} GiB",
    usage_temp: "temp {temp} C",
    cancel: "Cancel",
    task_load_failed: "Task load failed: {error}",
    admin_refresh_failed: "Admin refresh failed: {error}",
    caption_saved: "Caption {id} saved",
    caption_deleted: "Caption {id} deleted",
    caption_action_failed: "Caption action failed: {error}",
    person_name_required: "Please enter a person name",
    person_created: "Person {name} is ready",
    person_exists_reused: "Using existing person {name}",
    select_target_first: "Select a target person first",
    invalid_person_selection: "Invalid person selection",
    confirm_delete_face: "Delete face #{id} as non-face detection?",
    refreshed: "Refreshed",
    caption_regen_enqueued: "Caption regeneration task enqueued",
    regenerate_failed: "Regenerate failed: {error}",
    no_tag_entered: "No tag entered",
    tags_updated: "Tags updated",
    tag_catalog: "Tag Catalog",
    tag_filter_name_ph: "Filter tags...",
    tag_source: "Source",
    tag_source_all: "All",
    tag_source_cap: "Caption",
    tag_source_img: "Image",
    tag_source_capimg: "Caption+Image",
    tag_source_manual: "Manual",
    tag_source_rule: "Rule",
    tag_source_null: "Unknown",
    tag_assets: "Assets",
    tag_links: "Links",
    tag_sources: "Sources",
    tag_assets_panel: "Tag Assets",
    tag_assets_meta_default: "Select a tag to view related assets.",
    tag_assets_meta: "Tag {name}: {count} assets",
    tag_assets_meta_paged: "Tag {name}: showing {shown}/{total}",
    tag_assets_load_failed: "Tag assets load failed: {error}",
    tag_open_search: "Open in Search",
    tags_meta: "Tags: {shown} shown of {total}",
    tags_meta_paged: "Tags: {shown}/{total}",
    tag_catalog_load_failed: "Tag catalog load failed: {error}",
    remove_tag: "Remove tag",
    tag_removed: "Tag removed",
    tag_update_failed: "Tag update failed: {error}",
    face_updated: "Face {id} updated",
    face_assignment_failed: "Face assignment failed: {error}",
    person_renamed: "Person {id} renamed",
    person_action_failed: "Person action failed: {error}",
    unassigned_face_action_failed: "Unassigned face action failed: {error}",
    task_cancel_requested: "Task {id} cancel requested",
    cancel_failed: "Cancel failed: {error}",
    vector_rebuild_triggered: "Vector index rebuild triggered",
    rebuild_failed: "Rebuild failed: {error}",
    recluster_queued: "Recluster task queued",
    recluster_failed: "Recluster failed: {error}",
    provide_ingest_root: "Provide ingest root path",
    ingest_started: "Ingest scan started for {root}",
    ingest_failed: "Ingest failed: {error}",
    no_asset_selected: "Select an asset first",
    prev_page: "Prev",
    next_page: "Next",
    jump_page: "Go",
    page_input_ph: "Page",
    pager_status: "Page {page}/{pages} | showing {shown}/{total}",
  },
  zh: {
    app_title: "VLM 照片屋",
    subtitle: "在人脸、字幕、视频和搜索之间统一管理。",
    voice_command: "语音命令",
    voice_recording: "正在聆听...",
    voice_processing: "处理中...",
    voice_not_supported: "当前浏览器不支持语音采集",
    voice_denied: "麦克风权限被拒绝",
    voice_transcribe_failed: "语音转写失败: {error}",
    voice_command_failed: "语音命令失败: {error}",
    voice_no_transcript: "未清晰识别到语音",
    voice_heard: "识别到: {text}",
    voice_person_opened: "已打开 {name} 的照片（{total}）",
    voice_person_not_found: "未找到人物 {name}",
    refresh: "刷新",
    api_docs: "API 文档",
    assets: "资源",
    captions: "描述",
    faces: "人脸",
    people: "人物",
    tags_total: "标签关联",
    tagged_assets: "已标注资源",
    tasks_pending: "待处理任务",
    health: "健康状态",
    tab_library: "资源库",
    tab_people: "人物",
    tab_tags: "标签",
    tab_map: "地图",
    tab_tasks: "任务",
    tab_admin: "管理",
    search: "搜索",
    mode: "模式",
    mode_path: "路径",
    mode_caption: "描述",
    mode_smart: "智能",
    mode_person: "人物名",
    query: "查询",
    query_ph: "输入查询文本...",
    tags_for_smart: "标签（智能模式）",
    tags_for_smart_ph: "family, beach, sunset",
    media: "媒体",
    media_all: "全部",
    media_image: "图片",
    media_video: "视频",
    run_search: "执行搜索",
    browse_latest: "浏览最新",
    results: "结果",
    inspector: "详情",
    asset_empty: "选择任意结果卡片以查看描述、标签和人脸。",
    regenerate: "重新生成",
    tags: "标签",
    tags_input_ph: "逗号分隔标签",
    add_tags: "添加标签",
    person_assets: "人物资源",
    person_assets_meta_default: "选择一个人物查看相关资源。",
    unassigned_faces: "未分配人脸",
    show_unnamed_clusters: "显示未命名聚类",
    geo_map: "地理地图",
    points: "点位",
    refresh_map: "刷新地图",
    map_loading: "正在加载地图数据...",
    task_queue: "任务队列",
    id: "编号",
    type: "类型",
    state: "状态",
    progress: "进度",
    retry: "重试",
    error: "错误",
    action: "操作",
    metrics: "指标",
    actions: "操作",
    rebuild_vector_index: "重建向量索引",
    trigger_reclustering: "触发重聚类",
    ingest_root_ph: "E:\\01_INCOMING",
    ingest_scan: "扫描导入",
    admin_maintenance_hint: "在浏览器中执行受控维护操作。",
    caption_lvface: "描述/LVFace",
    back_to_results: "返回",
    fullscreen: "全屏预览",
    close_preview: "关闭",
    status_ok: "正常",
    status_degraded: "降级",
    no_thumbnail: "无缩略图",
    dashboard_refresh_failed: "看板刷新失败: {error}",
    latest_assets_meta: "最新资源: 显示 {shown} / {total}",
    library_load_failed: "资源库加载失败: {error}",
    caption_mode_needs_text: "描述模式需要输入文本",
    person_mode_needs_name: "人物模式需要人物名",
    search_results_meta: "模式: {mode} | 结果: {count}",
    search_results_meta_paged: "模式: {mode} | 结果: {shown}/{total}",
    search_failed: "搜索失败: {error}",
    asset_not_found: "资源 #{id} 未找到",
    asset_prefix: "资源 #{id}",
    unknown_path: "(未知路径)",
    inspector_load_failed: "详情加载失败: {error}",
    map_lib_failed: "地图库加载失败。",
    map_showing_meta: "显示 {shown} / {total} 个地理标记资源（{media}）。",
    map_no_points: "该筛选条件下没有 GPS 点。",
    map_load_failed: "地图加载失败: {error}",
    popup_open_asset: "打开资源",
    popup_image: "图片",
    popup_video: "视频",
    no_captions: "暂无描述。",
    caption_unknown_model: "未知",
    edited_flag: "已编辑={value}",
    caption_save: "保存",
    caption_delete: "删除",
    no_tags: "暂无标签。",
    new_person_name_ph: "新人物姓名",
    create_person: "新建人物",
    create_and_assign: "新建并分配",
    assign_to_person: "分配到人物...",
    current_person: "当前: 人物 {id}",
    person_fallback: "人物 {id}",
    new_person: "+ 新建人物",
    not_face_delete: "非人脸（删除检测）",
    no_face_detections: "该资源暂无人脸检测结果。",
    label_none: "标签=(无)",
    label_line: "标签={source}{score}",
    label_score: " 分数={score}",
    assign: "分配",
    not_face: "非人脸",
    face_prefix: "人脸 #{id}",
    face_asset_prefix: "人脸 #{face}, 资源 #{asset}",
    person_stats: "编号={id} | 人脸={count}",
    no_persons: "暂无人物。",
    people_hint_all: "显示已命名人物和未命名聚类。",
    people_hint_named: "仅显示已命名人物。需要时可开启“显示未命名聚类”。",
    display_name_ph: "显示名称",
    save_name: "保存名称",
    view_assets: "查看资源",
    person_assets_meta: "人物 {id}: {count} 个资源",
    person_assets_meta_paged: "人物 {id}: 当前显示 {shown}/{total}",
    no_unassigned_faces: "没有未分配人脸。",
    people_load_failed: "人物加载失败: {error}",
    person_assets_load_failed: "人物资源加载失败: {error}",
    unassigned_faces_load_failed: "未分配人脸加载失败: {error}",
    task_meta: "总计={total} | 待处理={pending} | 运行中={running} | 失败={failed} | 失效={dead}",
    task_meta_with_page:
      "总计={total} | 待处理={pending} | 运行中={running} | 失败={failed} | 失效={dead} | 当前显示={shown}",
    usage_cpu: "CPU",
    usage_memory: "内存",
    usage_gpu: "GPU {index}",
    usage_no_gpu: "无 GPU 指标",
    usage_unavailable: "不可用",
    usage_util_mem: "利用率 {util}% | 显存 {used}/{total} GiB",
    usage_temp: "温度 {temp} C",
    cancel: "取消",
    task_load_failed: "任务加载失败: {error}",
    admin_refresh_failed: "管理面板刷新失败: {error}",
    caption_saved: "描述 {id} 已保存",
    caption_deleted: "描述 {id} 已删除",
    caption_action_failed: "描述操作失败: {error}",
    person_name_required: "请输入人物姓名",
    person_created: "人物 {name} 已可用",
    person_exists_reused: "已使用现有人物 {name}",
    select_target_first: "请先选择目标人物",
    invalid_person_selection: "人物选择无效",
    confirm_delete_face: "将人脸 #{id} 标记为非人脸并删除检测？",
    refreshed: "已刷新",
    caption_regen_enqueued: "已加入描述重生成任务",
    regenerate_failed: "重生成失败: {error}",
    no_tag_entered: "未输入标签",
    tags_updated: "标签已更新",
    tag_catalog: "标签总览",
    tag_filter_name_ph: "筛选标签...",
    tag_source: "来源",
    tag_source_all: "全部",
    tag_source_cap: "描述",
    tag_source_img: "图像",
    tag_source_capimg: "描述+图像",
    tag_source_manual: "手动",
    tag_source_rule: "规则",
    tag_source_null: "未知",
    tag_assets: "资源数",
    tag_links: "关联数",
    tag_sources: "来源明细",
    tag_assets_panel: "标签资源",
    tag_assets_meta_default: "选择一个标签查看相关资源。",
    tag_assets_meta: "标签 {name}: {count} 个资源",
    tag_assets_meta_paged: "标签 {name}: 当前显示 {shown}/{total}",
    tag_assets_load_failed: "标签资源加载失败: {error}",
    tag_open_search: "在搜索中打开",
    tags_meta: "标签: 显示 {shown} / {total}",
    tags_meta_paged: "标签: {shown}/{total}",
    tag_catalog_load_failed: "标签总览加载失败: {error}",
    remove_tag: "移除标签",
    tag_removed: "标签已移除",
    tag_update_failed: "标签更新失败: {error}",
    face_updated: "人脸 {id} 已更新",
    face_assignment_failed: "人脸分配失败: {error}",
    person_renamed: "人物 {id} 已重命名",
    person_action_failed: "人物操作失败: {error}",
    unassigned_face_action_failed: "未分配人脸操作失败: {error}",
    task_cancel_requested: "任务 {id} 已请求取消",
    cancel_failed: "取消失败: {error}",
    vector_rebuild_triggered: "已触发向量索引重建",
    rebuild_failed: "重建失败: {error}",
    recluster_queued: "已加入重聚类任务",
    recluster_failed: "重聚类失败: {error}",
    provide_ingest_root: "请提供导入根路径",
    ingest_started: "已开始导入扫描: {root}",
    ingest_failed: "导入失败: {error}",
    no_asset_selected: "请先选择一个资源",
    prev_page: "上一页",
    next_page: "下一页",
    jump_page: "跳转",
    page_input_ph: "页码",
    pager_status: "第 {page}/{pages} 页 | 当前显示 {shown}/{total}",
  },
};

function t(key, vars = {}) {
  const dict = I18N[state.lang] || I18N.en;
  let s = dict[key] || I18N.en[key] || key;
  for (const [k, v] of Object.entries(vars)) {
    s = s.replaceAll(`{${k}}`, String(v));
  }
  return s;
}

function mediaLabel(value) {
  if (value === "image") return t("media_image");
  if (value === "video") return t("media_video");
  return t("media_all");
}

function modeLabel(value) {
  if (value === "path") return t("mode_path");
  if (value === "caption") return t("mode_caption");
  if (value === "smart") return t("mode_smart");
  if (value === "person") return t("mode_person");
  return value;
}

function tagSourceLabel(value) {
  if (value === "cap") return t("tag_source_cap");
  if (value === "img") return t("tag_source_img");
  if (value === "cap+img") return t("tag_source_capimg");
  if (value === "manual") return t("tag_source_manual");
  if (value === "rule") return t("tag_source_rule");
  if (value === "(null)") return t("tag_source_null");
  return value || t("tag_source_null");
}

function pageCount(total, pageSize) {
  const totalNum = Number(total) || 0;
  const sizeNum = Math.max(1, Number(pageSize) || 1);
  return Math.max(1, Math.ceil(totalNum / sizeNum));
}

function isLibraryPaged() {
  return ["latest", "path", "person"].includes(String(state.libraryPager.kind || ""));
}

function parsePageInputValue(rawValue, pages) {
  const n = Number(rawValue);
  if (!Number.isFinite(n)) return null;
  const p = Math.floor(n);
  if (p < 1) return 1;
  if (p > pages) return pages;
  return p;
}

function updateLibraryPagerUi() {
  const prev = qs("btn-library-prev");
  const next = qs("btn-library-next");
  const jumpBtn = qs("btn-library-jump");
  const jumpInput = qs("library-page-input");
  const meta = qs("library-page-meta");
  if (!prev || !next || !meta || !jumpBtn || !jumpInput) return;

  const pager = state.libraryPager || {};
  const page = Math.max(1, Number(pager.page) || 1);
  const pages = pageCount(pager.total, pager.pageSize);
  const shown = Number(pager.shown) || 0;
  const total = Number(pager.total);
  const displayTotal = Number.isFinite(total) && total >= 0 ? total : shown;

  if (!isLibraryPaged()) {
    prev.disabled = true;
    next.disabled = true;
    jumpBtn.disabled = true;
    jumpInput.disabled = true;
  } else {
    prev.disabled = page <= 1;
    next.disabled = page >= pages || shown <= 0;
    jumpBtn.disabled = shown <= 0 || pages <= 1;
    jumpInput.disabled = shown <= 0 || pages <= 1;
  }
  jumpInput.min = "1";
  jumpInput.max = String(pages);
  jumpInput.value = String(page);
  meta.textContent = t("pager_status", {
    page,
    pages,
    shown,
    total: displayTotal,
  });
}

function updatePersonAssetsPagerUi() {
  const prev = qs("btn-person-assets-prev");
  const next = qs("btn-person-assets-next");
  const jumpBtn = qs("btn-person-assets-jump");
  const jumpInput = qs("person-assets-page-input");
  const meta = qs("person-assets-page-meta");
  if (!prev || !next || !meta || !jumpBtn || !jumpInput) return;

  const pager = state.personAssetsPager || {};
  const page = Math.max(1, Number(pager.page) || 1);
  const pages = pageCount(pager.total, pager.pageSize);
  const shown = Number(pager.shown) || 0;
  const total = Number(pager.total) || 0;
  const active = Boolean(pager.personId);

  prev.disabled = page <= 1 || !active;
  next.disabled = page >= pages || shown <= 0 || !active;
  jumpBtn.disabled = !active || shown <= 0 || pages <= 1;
  jumpInput.disabled = !active || shown <= 0 || pages <= 1;
  jumpInput.min = "1";
  jumpInput.max = String(pages);
  jumpInput.value = String(page);
  meta.textContent = t("pager_status", { page, pages, shown, total });
}

function updateUnassignedFacesPagerUi() {
  const prev = qs("btn-unassigned-prev");
  const next = qs("btn-unassigned-next");
  const jumpBtn = qs("btn-unassigned-jump");
  const jumpInput = qs("unassigned-page-input");
  const meta = qs("unassigned-page-meta");
  if (!prev || !next || !meta || !jumpBtn || !jumpInput) return;

  const pager = state.unassignedFacesPager || {};
  const page = Math.max(1, Number(pager.page) || 1);
  const pages = pageCount(pager.total, pager.pageSize);
  const shown = Number(pager.shown) || 0;
  const total = Number(pager.total) || 0;

  prev.disabled = page <= 1;
  next.disabled = page >= pages || shown <= 0;
  jumpBtn.disabled = shown <= 0 || pages <= 1;
  jumpInput.disabled = shown <= 0 || pages <= 1;
  jumpInput.min = "1";
  jumpInput.max = String(pages);
  jumpInput.value = String(page);
  meta.textContent = t("pager_status", { page, pages, shown, total });
}

function updateTagsPagerUi() {
  const prev = qs("btn-tags-prev");
  const next = qs("btn-tags-next");
  const jumpBtn = qs("btn-tags-jump");
  const jumpInput = qs("tags-page-input");
  const meta = qs("tags-page-meta");
  if (!prev || !next || !meta || !jumpBtn || !jumpInput) return;

  const pager = state.tagsPager || {};
  const page = Math.max(1, Number(pager.page) || 1);
  const pages = pageCount(pager.total, pager.pageSize);
  const shown = Number(pager.shown) || 0;
  const total = Number(pager.total) || 0;

  prev.disabled = page <= 1;
  next.disabled = page >= pages || shown <= 0;
  jumpBtn.disabled = shown <= 0 || pages <= 1;
  jumpInput.disabled = shown <= 0 || pages <= 1;
  jumpInput.min = "1";
  jumpInput.max = String(pages);
  jumpInput.value = String(page);
  meta.textContent = t("pager_status", { page, pages, shown, total });
}

function updateTagAssetsPagerUi() {
  const prev = qs("btn-tag-assets-prev");
  const next = qs("btn-tag-assets-next");
  const jumpBtn = qs("btn-tag-assets-jump");
  const jumpInput = qs("tag-assets-page-input");
  const meta = qs("tag-assets-page-meta");
  if (!prev || !next || !meta || !jumpBtn || !jumpInput) return;

  const pager = state.tagsAssetsPager || {};
  const page = Math.max(1, Number(pager.page) || 1);
  const pages = pageCount(pager.total, pager.pageSize);
  const shown = Number(pager.shown) || 0;
  const total = Number(pager.total) || 0;
  const active = Boolean(pager.tagId);

  prev.disabled = page <= 1 || !active;
  next.disabled = page >= pages || shown <= 0 || !active;
  jumpBtn.disabled = !active || shown <= 0 || pages <= 1;
  jumpInput.disabled = !active || shown <= 0 || pages <= 1;
  jumpInput.min = "1";
  jumpInput.max = String(pages);
  jumpInput.value = String(page);
  meta.textContent = t("pager_status", { page, pages, shown, total });
}

function mbToGiB(mb) {
  const n = Number(mb);
  if (!Number.isFinite(n)) return "-";
  return (n / 1024).toFixed(1);
}

function bytesToGiB(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "-";
  return (n / (1024 ** 3)).toFixed(1);
}

function renderSystemUsage(usage) {
  const root = qs("task-system-usage");
  if (!root) return;
  if (!usage) {
    root.innerHTML = "";
    return;
  }

  const cpuText = Number.isFinite(Number(usage.cpu_percent))
    ? `${Number(usage.cpu_percent).toFixed(1)}%`
    : t("usage_unavailable");

  let memValue = t("usage_unavailable");
  let memSub = "";
  if (usage.memory) {
    const total = bytesToGiB(usage.memory.total);
    const used = bytesToGiB(usage.memory.used);
    const pct = Number.isFinite(Number(usage.memory.percent)) ? Number(usage.memory.percent).toFixed(1) : "-";
    memValue = `${pct}%`;
    memSub = `${used}/${total} GiB`;
  }

  const cards = [
    `<article class="usage-card"><p class="usage-title">${esc(t("usage_cpu"))}</p><p class="usage-value">${esc(cpuText)}</p></article>`,
    `<article class="usage-card"><p class="usage-title">${esc(t("usage_memory"))}</p><p class="usage-value">${esc(memValue)}</p><p class="usage-sub">${esc(memSub)}</p></article>`,
  ];

  const gpus = Array.isArray(usage.gpus) ? usage.gpus : [];
  if (!gpus.length) {
    cards.push(
      `<article class="usage-card"><p class="usage-title">GPU</p><p class="usage-value">${esc(
        t("usage_no_gpu")
      )}</p></article>`
    );
  } else {
    for (const g of gpus) {
      const util = Number.isFinite(Number(g.utilization_gpu_percent))
        ? Number(g.utilization_gpu_percent).toFixed(0)
        : "-";
      const used = mbToGiB(g.memory_used_mb);
      const total = mbToGiB(g.memory_total_mb);
      const temp = Number.isFinite(Number(g.temperature_c)) ? Number(g.temperature_c).toFixed(0) : "-";
      cards.push(`
        <article class="usage-card">
          <p class="usage-title">${esc(t("usage_gpu", { index: g.index }))}</p>
          <p class="usage-value">${esc(g.name || "NVIDIA GPU")}</p>
          <p class="usage-sub">${esc(t("usage_util_mem", { util, used, total }))}</p>
          <p class="usage-sub">${esc(t("usage_temp", { temp }))}</p>
        </article>
      `);
    }
  }

  root.innerHTML = cards.join("");
}

function applyI18n() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  document.title = t("app_title");
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (key) el.setAttribute("placeholder", t(key));
  });
  document.querySelectorAll(".lang-btn").forEach((el) => {
    el.classList.toggle("active", el.dataset.lang === state.lang);
  });
}

function setLanguage(lang, persist = true) {
  const next = lang === "zh" ? "zh" : "en";
  state.lang = next;
  if (persist) {
    window.localStorage.setItem("vlm_ui_lang", next);
  }
  applyI18n();
  renderCurrentViewText();
}

function renderCurrentViewText() {
  if (state.libraryViewItems.length) {
    renderAssetGrid(state.libraryViewItems, "library-grid");
  }
  updateLibraryPagerUi();
  updatePersonAssetsPagerUi();
  updateUnassignedFacesPagerUi();
  if (state.selectedAsset) {
    qs("asset-id").textContent = t("asset_prefix", { id: state.selectedAsset.id });
    if (!qs("asset-path").textContent.trim()) {
      qs("asset-path").textContent = t("unknown_path");
    }
  }
  if (state.activeTab === "people") {
    renderPeopleList();
    loadUnassignedFaces(state.unassignedFacesPager.page || 1);
  }
  if (state.activeTab === "tags") {
    loadTagsCatalog(state.tagsPager.page || 1);
    if (state.tagsAssetsPager.tagId) {
      loadTagAssets(state.tagsAssetsPager.tagId, state.tagsAssetsPager.page || 1);
    } else {
      updateTagAssetsPagerUi();
    }
  }
  if (state.activeTab === "tasks") {
    loadTasks();
  }
  if (state.activeTab === "map") {
    loadGeoMap();
  }
}

function esc(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function basename(path) {
  const raw = String(path || "");
  const p = raw.replaceAll("\\", "/");
  return p.split("/").pop() || raw;
}

function isVideoAsset(asset) {
  const mime = String(asset?.mime || "").toLowerCase();
  if (mime.startsWith("video/")) {
    return true;
  }
  const p = String(asset?.path || "").toLowerCase();
  return [".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"].some((ext) => p.endsWith(ext));
}

function showToast(message) {
  const toast = qs("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function tabToUrl(tab) {
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  window.history.replaceState(null, "", url.toString());
}

async function api(url, opts = {}) {
  const options = { ...opts };
  options.headers = options.headers || {};
  if (options.body && !(options.body instanceof FormData)) {
    options.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, options);
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = data?.detail || data?.error?.message || data || `HTTP ${res.status}`;
    throw new Error(String(detail));
  }
  return data;
}

function setVoiceStatus(message = "") {
  const el = qs("voice-status");
  if (el) el.textContent = message;
}

function extractVoicePersonAssetsQuery(textRaw) {
  const normalized = String(textRaw || "")
    .trim()
    .toLowerCase()
    .replace(/[,.!?;:，。！？；：]/g, " ")
    .replace(/\s+/g, " ");
  if (!normalized) return "";
  const patterns = [
    /^(?:please\s+)?(?:show me|show|find|open)\s+(?:(?:the|a|an|some)\s+)?(?:photos|photo|pictures|picture|images|image)\s+(?:of\s+)?(.+)$/,
    /^(?:photos|photo|pictures|picture|images|image)\s+(?:of\s+)?(.+)$/,
    /^(?:show me|show)\s+(.+?)\s+(?:photos|photo|pictures|picture|images|image)$/,
    /^(?:show me|show)\s+(.+?)'s\s+(?:photos|photo|pictures|picture|images|image)$/,
    /^(?:请)?(?:给我看|给我看看|帮我找|找找|找一下|显示|打开|看看)\s*(?:一下)?\s*(.+?)\s*(?:的)?\s*(?:照片|图片|相片|影像|相册)$/,
    /^(?:请)?(?:帮我)?(?:找|找下|找一下)\s*(.+?)\s*(?:的)?\s*(?:照片|图片|相片|影像|相册)$/,
  ];
  for (const p of patterns) {
    const m = normalized.match(p);
    if (!m || !m[1]) continue;
    const q = String(m[1]).trim().replace(/^[\s'"`.,!?;:。！？；：]+|[\s'"`.,!?;:。！？；：]+$/g, "");
    const q2 = q.replace(/^(?:the|a|an)\s+/i, "").trim();
    if (q2) return q2;
    if (q) return q;
  }
  return "";
}

function normalizeVoicePersonName(raw) {
  let q = String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/[,.!?;:，。！？；：]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  q = q.replace(/^(?:the|a|an)\s+/i, "").trim();
  q = q.replace(/\s+[a-z]$/i, "").trim(); // trims noisy suffix like "jane r"
  return q;
}

async function lookupPersonByNameQuery(rawQuery) {
  const base = normalizeVoicePersonName(rawQuery);
  if (!base) return null;
  const candidates = [];
  const push = (v) => {
    const n = normalizeVoicePersonName(v);
    if (n && !candidates.includes(n)) candidates.push(n);
  };
  push(base);
  const tokens = base.split(" ").filter((x) => x);
  if (tokens.length > 1) {
    push(tokens[0]);
    push(tokens[tokens.length - 1]);
  }
  for (const q of candidates) {
    let data;
    try {
      data = await api(
        `/persons?page=1&page_size=120&include_faces=false&named_only=true&sort_by=face_count&order=desc&name_query=${encodeURIComponent(q)}`
      );
    } catch (_) {
      continue;
    }
    const persons = Array.isArray(data?.persons) ? data.persons : [];
    if (!persons.length) continue;
    const qLower = String(q).toLowerCase();
    let person = persons.find((p) => String(p?.display_name || "").trim().toLowerCase() === qLower);
    if (!person) {
      person = persons.find((p) => String(p?.display_name || "").trim().toLowerCase().startsWith(qLower));
    }
    if (!person) person = persons[0];
    const personId = Number(person?.id || 0);
    if (personId <= 0) continue;
    let total = 0;
    try {
      const assets = await api(`/search/person/${personId}?page=1&page_size=1`);
      total = Number(assets?.total || 0);
    } catch (_) {
      total = 0;
    }
    return {
      personId,
      personName: String(person?.display_name || q),
      total,
      query: q,
    };
  }
  return { personId: 0, personName: "", total: 0, query: base };
}

async function openPersonAssetsFromLookup(lookup) {
  const personId = Number(lookup?.personId || 0);
  if (!personId) return false;
  const personName = String(lookup?.personName || `#${personId}`);
  const total = Number(lookup?.total || 0);
  setActiveTab("people");
  await loadPeople();
  await loadPersonAssets(personId, 1);
  showToast(t("voice_person_opened", { name: personName, total }));
  return true;
}

async function tryClientPersonAssetsFallback(text) {
  const q = extractVoicePersonAssetsQuery(text);
  if (!q) return false;
  const lookup = await lookupPersonByNameQuery(q);
  if (await openPersonAssetsFromLookup(lookup)) return true;
  showToast(t("voice_person_not_found", { name: String(lookup?.query || q || "?") }));
  return true;
}

async function executeVoiceCommand(text) {
  const payload = await api("/voice/command", {
    method: "POST",
    body: JSON.stringify({ text, language: state.lang, limit: 20 }),
  });
  const action = String(payload?.contract?.action || "");
  if (action === "search.person.assets") {
    const personId = Number(payload?.data?.person_id || 0);
    const personName = String(payload?.data?.person_name || "").trim() || `#${personId}`;
    const total = Number(payload?.data?.total || 0);
    if (personId > 0) {
      setActiveTab("people");
      await loadPeople();
      await loadPersonAssets(personId, 1);
      showToast(t("voice_person_opened", { name: personName, total }));
      return;
    }
    const q = String(payload?.data?.query || "").trim() || extractVoicePersonAssetsQuery(text) || text;
    const lookup = await lookupPersonByNameQuery(q);
    if (await openPersonAssetsFromLookup(lookup)) return;
    showToast(t("voice_person_not_found", { name: String(lookup?.query || q || "?") }));
    return;
  }
  if (action === "help") {
    const handled = await tryClientPersonAssetsFallback(text);
    if (handled) return;
  }
  const summary = String(payload?.summary_text || "").trim();
  if (summary) showToast(summary);
}

async function runVoiceCommandCapture() {
  if (state.voiceBusy) return;
  const voiceBtn = qs("btn-voice-command");
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    showToast(t("voice_not_supported"));
    return;
  }
  state.voiceBusy = true;
  if (voiceBtn) voiceBtn.disabled = true;
  let stream = null;
  try {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });
    } catch (_) {
      showToast(t("voice_denied"));
      return;
    }
    setVoiceStatus(t("voice_recording"));
    const chunks = [];
    const mimeCandidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
    const chosenMime = mimeCandidates.find(
      (m) => typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported(m)
    );
    const recorder = chosenMime ? new MediaRecorder(stream, { mimeType: chosenMime }) : new MediaRecorder(stream);
    const stopped = new Promise((resolve, reject) => {
      recorder.addEventListener("stop", resolve, { once: true });
      recorder.addEventListener("error", (ev) => reject(ev?.error || new Error("recording error")), { once: true });
    });
    recorder.addEventListener("dataavailable", (ev) => {
      if (ev.data && ev.data.size > 0) chunks.push(ev.data);
    });
    recorder.start();
    await new Promise((r) => window.setTimeout(r, 5000));
    recorder.stop();
    await stopped;

    const blob = new Blob(chunks, { type: chunks[0]?.type || chosenMime || "audio/webm" });
    if (!blob.size) {
      showToast(t("voice_no_transcript"));
      return;
    }
    setVoiceStatus(t("voice_processing"));
    const form = new FormData();
    form.append("file", blob, "voice.webm");
    form.append("language", state.lang === "zh" ? "zh" : "en");
    const asr = await api("/voice/transcribe", { method: "POST", body: form });
    const transcript = String(asr?.text || asr?.transcript || asr?.result || "").trim();
    if (!transcript) {
      const err = String(asr?.error || "");
      showToast(err ? t("voice_transcribe_failed", { error: err }) : t("voice_no_transcript"));
      return;
    }
    showToast(t("voice_heard", { text: transcript }));
    await executeVoiceCommand(transcript);
  } catch (e) {
    showToast(t("voice_command_failed", { error: e.message }));
  } finally {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    state.voiceBusy = false;
    if (voiceBtn) voiceBtn.disabled = false;
    setVoiceStatus("");
  }
}

function setActiveTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".tab").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((el) => {
    el.classList.toggle("active", el.id === `tab-${tab}`);
  });
  tabToUrl(tab);
}

function renderAssetGrid(items, containerId) {
  const root = qs(containerId);
  if (containerId === "library-grid") {
    state.libraryViewItems = Array.isArray(items) ? items : [];
  }
  items.forEach((asset) => state.assetMap.set(Number(asset.id), asset));
  root.innerHTML = items
    .map((asset) => {
      const id = Number(asset.id);
      const selected = state.selectedAsset && Number(state.selectedAsset.id) === id ? "selected" : "";
      return `
        <article class="asset-card ${selected}" data-asset-id="${id}">
          <div class="thumb">
            <img loading="lazy" src="/assets/${id}/thumbnail?size=256"
                 alt="${esc(basename(asset.path))}"
                 onerror="this.remove(); this.parentElement.querySelector('.fallback').style.display='grid';" />
            <span class="fallback" style="display:none;">${esc(t("no_thumbnail"))}</span>
          </div>
          <div class="asset-meta">
            <p class="id">#${id}</p>
            <p class="name" title="${esc(asset.path)}">${esc(basename(asset.path))}</p>
          </div>
        </article>
      `;
    })
    .join("");
}

async function refreshDashboard() {
  try {
    const [health, metrics] = await Promise.all([api("/health"), api("/metrics")]);
    const setStat = (id, value) => {
      const el = qs(id);
      if (el) el.textContent = value ?? "-";
    };
    setStat("stat-assets", metrics.assets?.total);
    setStat("stat-captions", metrics.captions);
    setStat("stat-faces", metrics.faces);
    setStat("stat-persons", metrics.persons);
    setStat("stat-tags", metrics.tags?.total_links);
    setStat("stat-tag-assets", metrics.tags?.assets_with_tags);
    setStat("stat-pending", health.pending_tasks);
    const healthEl = qs("stat-health");
    if (healthEl) {
      healthEl.textContent = health.ok ? t("status_ok") : t("status_degraded");
      healthEl.style.color = health.ok ? "#0f8a66" : "#b73a3a";
    }
  } catch (e) {
    showToast(t("dashboard_refresh_failed", { error: e.message }));
  }
}

async function loadLibraryLatest(page = 1) {
  try {
    const pageNum = Math.max(1, Number(page) || 1);
    const pageSize = state.libraryPager.pageSize || 120;
    const data = await api(`/assets?page=${pageNum}&page_size=${pageSize}`);
    const assets = data.assets || [];
    const total = Number(data.total) || assets.length;
    state.libraryPager = {
      ...state.libraryPager,
      kind: "latest",
      mode: "path",
      q: "",
      media: qs("search-media")?.value || "all",
      tags: [],
      page: pageNum,
      pageSize,
      total,
      shown: assets.length,
    };
    qs("library-result-meta").textContent = t("latest_assets_meta", {
      shown: assets.length,
      total,
    });
    renderAssetGrid(assets, "library-grid");
    updateLibraryPagerUi();
  } catch (e) {
    showToast(t("library_load_failed", { error: e.message }));
  }
}

function parseTagsInput() {
  return String(qs("search-tags").value || "")
    .split(",")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

function normalizeSearch(mode, data) {
  if (mode === "path") {
    return (data.items || []).map((v) => ({ id: v.id, path: v.path }));
  }
  if (mode === "caption") {
    return (data.results || []).map((v) => ({ id: v.asset_id, path: v.path, mime: v.mime }));
  }
  if (mode === "smart") {
    return (data.results || []).map((v) => ({
      id: v.asset_id,
      path: v.path,
      score: v.score,
      mime: v.mime,
    }));
  }
  if (mode === "person") {
    return (data.items || []).map((v) => ({ id: v.id, path: v.path }));
  }
  return [];
}

async function runSearch(page = 1, fromPager = false) {
  const pageNum = Math.max(1, Number(page) || 1);
  const pageSize = state.libraryPager.pageSize || 120;

  const mode = fromPager ? state.libraryPager.mode : qs("search-mode").value;
  const q = fromPager ? String(state.libraryPager.q || "") : String(qs("search-query").value || "").trim();
  const media = fromPager ? (state.libraryPager.media || "all") : qs("search-media").value;
  const tags = fromPager ? (Array.isArray(state.libraryPager.tags) ? state.libraryPager.tags : []) : parseTagsInput();

  try {
    let payload = null;
    let kind = mode;
    let total = 0;
    let paged = false;

    if (mode === "path") {
      if (!q) {
        await loadLibraryLatest(pageNum);
        return;
      }
      paged = true;
      kind = "path";
      payload = await api(`/search?q=${encodeURIComponent(q)}&page=${pageNum}&page_size=${pageSize}`);
      total = Number(payload?.total) || 0;
    } else if (mode === "caption") {
      if (!q) {
        showToast(t("caption_mode_needs_text"));
        return;
      }
      payload = await api("/search/captions", {
        method: "POST",
        body: JSON.stringify({ text: q, k: pageSize, media }),
      });
    } else if (mode === "smart") {
      payload = await api("/search/smart", {
        method: "POST",
        body: JSON.stringify({
          text: q || null,
          tags: tags.length ? tags : null,
          media,
          k: pageSize,
        }),
      });
    } else if (mode === "person") {
      if (!q) {
        showToast(t("person_mode_needs_name"));
        return;
      }
      paged = true;
      kind = "person";
      payload = await api(`/search/person/name/${encodeURIComponent(q)}?page=${pageNum}&page_size=${pageSize}`);
      total = Number(payload?.total) || 0;
    }

    const items = normalizeSearch(mode, payload || {});
    if (!paged) {
      total = items.length;
    }
    state.libraryPager = {
      ...state.libraryPager,
      kind,
      mode,
      q,
      media,
      tags,
      page: pageNum,
      pageSize,
      total,
      shown: items.length,
    };
    qs("library-result-meta").textContent = paged
      ? t("search_results_meta_paged", {
          mode: modeLabel(mode),
          shown: items.length,
          total,
        })
      : t("search_results_meta", {
          mode: modeLabel(mode),
          count: items.length,
        });
    renderAssetGrid(items, "library-grid");
    updateLibraryPagerUi();
  } catch (e) {
    showToast(t("search_failed", { error: e.message }));
  }
}

async function runLibraryPage(delta) {
  const current = Math.max(1, Number(state.libraryPager.page) || 1);
  const target = Math.max(1, current + Number(delta || 0));
  if (target === current) return;

  const kind = String(state.libraryPager.kind || "latest");
  if (kind === "latest") {
    await loadLibraryLatest(target);
    return;
  }
  await runSearch(target, true);
}

async function runLibraryJump() {
  if (!isLibraryPaged()) return;
  const pages = pageCount(state.libraryPager.total, state.libraryPager.pageSize);
  const input = qs("library-page-input");
  const target = parsePageInputValue(input?.value, pages);
  if (!target) return;

  const current = Math.max(1, Number(state.libraryPager.page) || 1);
  if (target === current) return;

  const kind = String(state.libraryPager.kind || "latest");
  if (kind === "latest") {
    await loadLibraryLatest(target);
    return;
  }
  await runSearch(target, true);
}

async function loadTagsCatalog(page = 1) {
  try {
    const pageNum = Math.max(1, Number(page) || 1);
    const pageSize = state.tagsPager.pageSize || 200;
    const qInput = qs("tags-filter-query");
    const sourceInput = qs("tags-filter-source");
    const q = String((qInput ? qInput.value : state.tagsPager.q) || "").trim();
    const source = String((sourceInput ? sourceInput.value : state.tagsPager.source) || "all");
    const params = new URLSearchParams();
    params.set("q", q);
    params.set("source", source);
    params.set("page", String(pageNum));
    params.set("page_size", String(pageSize));
    const data = await api(`/tags?${params.toString()}`);
    const rows = Array.isArray(data?.rows) ? data.rows : [];
    const total = Number(data?.total) || 0;

    state.tagsPager = {
      ...state.tagsPager,
      q,
      source,
      page: pageNum,
      pageSize,
      total,
      shown: rows.length,
    };
    if (qInput) qInput.value = q;
    if (sourceInput) sourceInput.value = source;

    qs("tags-meta").textContent = t("tags_meta_paged", { shown: rows.length, total });
    qs("tags-rows").innerHTML = rows
      .map((row) => {
        const src = row?.sources && typeof row.sources === "object" ? row.sources : {};
        const sourceText = ["cap", "img", "cap+img", "manual", "rule", "(null)"]
          .filter((k) => Number(src[k]) > 0)
          .map((k) => `${tagSourceLabel(k)}:${Number(src[k])}`)
          .join(" | ");
        const active = Number(state.tagsAssetsPager.tagId) === Number(row.id) ? "tags-row-active" : "";
        return `
          <tr class="${active}">
            <td>${esc(row.name)}</td>
            <td>${esc(row.type || "-")}</td>
            <td>${Number(row.assets) || 0}</td>
            <td>${Number(row.links) || 0}</td>
            <td class="small muted">${esc(sourceText || "-")}</td>
            <td>
              <button class="btn ghost" data-action="tags-view-assets" data-tag-id="${Number(row.id)}" data-tag-name="${esc(row.name)}">${esc(t("view_assets"))}</button>
              <button class="btn ghost" data-action="tags-open-search" data-tag-name="${esc(row.name)}">${esc(t("tag_open_search"))}</button>
            </td>
          </tr>
        `;
      })
      .join("");
    updateTagsPagerUi();
  } catch (e) {
    showToast(t("tag_catalog_load_failed", { error: e.message }));
  }
}

async function runTagsPage(delta) {
  const current = Math.max(1, Number(state.tagsPager.page) || 1);
  const target = Math.max(1, current + Number(delta || 0));
  if (target === current) return;
  await loadTagsCatalog(target);
}

async function runTagsJump() {
  const pages = pageCount(state.tagsPager.total, state.tagsPager.pageSize);
  const input = qs("tags-page-input");
  const target = parsePageInputValue(input?.value, pages);
  if (!target) return;
  const current = Math.max(1, Number(state.tagsPager.page) || 1);
  if (target === current) return;
  await loadTagsCatalog(target);
}

async function loadTagAssets(tagId, page = 1) {
  const id = Number(tagId || 0);
  if (!id) {
    state.tagsAssetsPager = {
      ...state.tagsAssetsPager,
      tagId: null,
      tagName: "",
      page: 1,
      total: 0,
      shown: 0,
    };
    qs("tag-assets-meta").textContent = t("tag_assets_meta_default");
    renderAssetGrid([], "tag-assets-grid");
    updateTagAssetsPagerUi();
    return;
  }
  try {
    const pageNum = Math.max(1, Number(page) || 1);
    const pageSize = state.tagsAssetsPager.pageSize || 120;
    const mediaInput = qs("tag-assets-media");
    const sourceInput = qs("tag-assets-source");
    const media = String((mediaInput ? mediaInput.value : state.tagsAssetsPager.media) || "all");
    const source = String((sourceInput ? sourceInput.value : state.tagsAssetsPager.source) || "all");
    const params = new URLSearchParams();
    params.set("media", media);
    params.set("source", source);
    params.set("page", String(pageNum));
    params.set("page_size", String(pageSize));
    const data = await api(`/tags/${id}/assets?${params.toString()}`);
    const items = Array.isArray(data?.items) ? data.items : [];
    const total = Number(data?.total) || 0;
    const tagName = String(data?.tag?.name || state.tagsAssetsPager.tagName || id);

    state.tagsAssetsPager = {
      ...state.tagsAssetsPager,
      tagId: id,
      tagName,
      page: pageNum,
      pageSize,
      total,
      shown: items.length,
      media,
      source,
    };
    if (mediaInput) mediaInput.value = media;
    if (sourceInput) sourceInput.value = source;

    qs("tag-assets-meta").textContent = t("tag_assets_meta_paged", {
      name: tagName,
      shown: items.length,
      total,
    });
    renderAssetGrid(items, "tag-assets-grid");
    updateTagAssetsPagerUi();
  } catch (e) {
    showToast(t("tag_assets_load_failed", { error: e.message }));
  }
}

async function runTagAssetsPage(delta) {
  const pager = state.tagsAssetsPager || {};
  if (!pager.tagId) return;
  const current = Math.max(1, Number(pager.page) || 1);
  const target = Math.max(1, current + Number(delta || 0));
  if (target === current) return;
  await loadTagAssets(pager.tagId, target);
}

async function runTagAssetsJump() {
  const pager = state.tagsAssetsPager || {};
  if (!pager.tagId) return;
  const pages = pageCount(pager.total, pager.pageSize);
  const input = qs("tag-assets-page-input");
  const target = parsePageInputValue(input?.value, pages);
  if (!target) return;
  const current = Math.max(1, Number(pager.page) || 1);
  if (target === current) return;
  await loadTagAssets(pager.tagId, target);
}

function closeAssetInspector() {
  state.selectedAsset = null;
  qs("asset-inspector").classList.add("hidden");
  qs("asset-empty").classList.remove("hidden");
  qs("asset-preview").innerHTML = "";
  closePreviewModal();
  if (state.libraryViewItems.length) {
    renderAssetGrid(state.libraryViewItems, "library-grid");
  }
}

function openPreviewModal() {
  if (!state.selectedAsset) {
    showToast(t("no_asset_selected"));
    return;
  }
  const asset = state.selectedAsset;
  const body = qs("preview-modal-body");
  if (isVideoAsset(asset)) {
    body.innerHTML = `<video controls autoplay preload="metadata" src="/assets/${asset.id}/media"></video>`;
  } else {
    body.innerHTML = `<img src="/assets/${asset.id}/media" alt="${esc(basename(asset.path))}" />`;
  }
  qs("preview-modal").classList.remove("hidden");
}

function closePreviewModal() {
  const modal = qs("preview-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  const body = qs("preview-modal-body");
  if (body) {
    body.innerHTML = "";
  }
}

async function loadAssetInspector(assetId) {
  const id = Number(assetId);
  let asset = state.assetMap.get(id);
  if (!asset) {
    try {
      const detail = await api(`/assets/detail/${id}`);
      asset = detail.asset || null;
      if (asset) {
        state.assetMap.set(id, asset);
      }
    } catch (e) {
      showToast(t("asset_not_found", { id }));
      return;
    }
  }
  if (!asset) return;
  state.selectedAsset = asset;
  if (state.libraryViewItems.length) {
    renderAssetGrid(state.libraryViewItems, "library-grid");
  }

  qs("asset-empty").classList.add("hidden");
  qs("asset-inspector").classList.remove("hidden");
  qs("asset-id").textContent = t("asset_prefix", { id: asset.id });
  qs("asset-path").textContent = asset.path || t("unknown_path");

  const preview = qs("asset-preview");
  if (isVideoAsset(asset)) {
    preview.innerHTML = `<video controls preload="metadata" src="/assets/${asset.id}/media"></video>`;
  } else {
    preview.innerHTML = `<img src="/assets/${asset.id}/media" alt="${esc(basename(asset.path))}" />`;
  }

  try {
    const [captions, tags, faces] = await Promise.all([
      api(`/assets/${asset.id}/captions`),
      api(`/assets/${asset.id}/tags`),
      api(`/faces?asset_id=${asset.id}&page=1&page_size=200`),
    ]);
    renderCaptions(captions.captions || []);
    renderTags(tags.tags || []);
    renderFaces(faces.faces || []);
  } catch (e) {
    showToast(t("inspector_load_failed", { error: e.message }));
  }
}

function ensureGeoMap() {
  if (state.geoMap) {
    return true;
  }
  if (!window.L) {
    qs("map-meta").textContent = t("map_lib_failed");
    return false;
  }
  const mapRoot = qs("geo-map");
  if (!mapRoot) {
    return false;
  }
  state.geoMap = window.L.map(mapRoot, {
    zoomControl: true,
    preferCanvas: true,
  }).setView([39.9042, 116.4074], 4);
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.geoMap);
  state.geoLayer = window.L.layerGroup().addTo(state.geoMap);
  return true;
}

function mapPopupHtml(point) {
  const when = point.taken_at ? `<p class="small muted">${esc(point.taken_at)}</p>` : "";
  const type = isVideoAsset(point) ? t("popup_video") : t("popup_image");
  return `
    <div>
      <p><strong>#${point.id}</strong> <span class="small muted">(${type})</span></p>
      ${when}
      <p class="small muted" title="${esc(point.path)}">${esc(basename(point.path))}</p>
      <button class="btn ghost" data-action="map-open-asset" data-asset-id="${point.id}">${esc(t("popup_open_asset"))}</button>
    </div>
  `;
}

async function loadGeoMap() {
  try {
    if (!ensureGeoMap()) return;
    const media = qs("map-media-filter").value || "all";
    const limitVal = Number(qs("map-limit").value || "3000");
    const limit = Number.isFinite(limitVal) ? Math.max(100, Math.min(20000, limitVal)) : 3000;
    const data = await api(`/assets/geo?media=${encodeURIComponent(media)}&limit=${limit}`);
    const points = data.points || [];
    points.forEach((p) => state.assetMap.set(Number(p.id), p));

    state.geoLayer.clearLayers();
    const bounds = [];
    for (const p of points) {
      const lat = Number(p.gps_lat);
      const lon = Number(p.gps_lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const marker = window.L.circleMarker([lat, lon], {
        radius: 5,
        weight: 1,
        color: "#0f8a66",
        fillColor: "#18a878",
        fillOpacity: 0.65,
      });
      marker.bindPopup(mapPopupHtml(p), { maxWidth: 280 });
      marker.addTo(state.geoLayer);
      bounds.push([lat, lon]);
    }

    const total = Number(data.total || points.length);
    qs("map-meta").textContent = t("map_showing_meta", {
      shown: points.length,
      total,
      media: mediaLabel(media),
    });

    if (bounds.length > 0) {
      const leafletBounds = window.L.latLngBounds(bounds);
      if (!state.mapLoaded) {
        state.geoMap.fitBounds(leafletBounds.pad(0.1));
      }
      state.mapLoaded = true;
    } else {
      qs("map-meta").textContent = t("map_no_points");
      state.geoMap.setView([39.9042, 116.4074], 3);
    }

    window.setTimeout(() => {
      if (state.geoMap) state.geoMap.invalidateSize();
    }, 50);
  } catch (e) {
    showToast(t("map_load_failed", { error: e.message }));
  }
}

function renderCaptions(captions) {
  const root = qs("caption-list");
  if (!captions.length) {
    root.innerHTML = `<p class="muted">${esc(t("no_captions"))}</p>`;
    return;
  }
  root.innerHTML = captions
    .map(
      (c) => `
        <article class="caption-item" data-caption-id="${c.id}">
          <p class="small muted">#${c.id} | ${esc(c.model || t("caption_unknown_model"))} | ${esc(
            t("edited_flag", { value: Boolean(c.user_edited) })
          )}</p>
          <textarea id="caption-text-${c.id}">${esc(c.text || "")}</textarea>
          <div class="controls">
            <button class="btn" data-action="save-caption" data-caption-id="${c.id}">${esc(t("caption_save"))}</button>
            <button class="btn danger" data-action="delete-caption" data-caption-id="${c.id}">${esc(t("caption_delete"))}</button>
          </div>
        </article>
      `
    )
    .join("");
}

function renderTags(tags) {
  const root = qs("tag-list");
  if (!tags.length) {
    root.innerHTML = `<span class="muted">${esc(t("no_tags"))}</span>`;
    return;
  }
  root.innerHTML = tags
    .map((tag) => {
      const meta = [tag.source, tag.model, typeof tag.score === "number" ? `score=${Number(tag.score).toFixed(3)}` : ""]
        .filter((v) => String(v || "").trim())
        .join(" | ");
      return `
        <span class="tag-chip">
          <span title="${esc(meta)}">${esc(tag.name)}${tag.source ? `<span class="tag-chip-meta">${esc(tag.source)}</span>` : ""}</span>
          <button class="tag-chip-remove" type="button" data-action="remove-tag" data-tag-id="${Number(tag.id) || 0}" title="${esc(
            t("remove_tag")
          )}" aria-label="${esc(t("remove_tag"))}">&times;</button>
        </span>
      `
    })
    .join("");
}

function personOptions(currentId) {
  const base = [`<option value="">${esc(t("assign_to_person"))}</option>`];
  const namedIds = new Set((state.namedPersons || []).map((p) => Number(p.id)));
  const current = Number(currentId || 0);

  // Keep visibility when a face is already attached to an unnamed cluster.
  if (current > 0 && !namedIds.has(current)) {
    base.push(`<option value="${current}" selected>${esc(t("current_person", { id: current }))}</option>`);
  }

  for (const p of state.namedPersons || []) {
    const name = p.display_name || t("person_fallback", { id: p.id });
    const selected = current > 0 && current === Number(p.id) ? "selected" : "";
    base.push(`<option value="${p.id}" ${selected}>${esc(name)}</option>`);
  }

  base.push(`<option value="__NEW__">${esc(t("new_person"))}</option>`);
  base.push(`<option value="__DELETE__">${esc(t("not_face_delete"))}</option>`);
  return base.join("");
}

function renderFaces(faces) {
  const root = qs("face-list");
  if (!faces.length) {
    root.innerHTML = `<p class="muted">${esc(t("no_face_detections"))}</p>`;
    return;
  }
  root.innerHTML = faces
    .map(
      (f) => {
        const source = String(f.label_source || "").trim();
        const score = typeof f.label_score === "number" ? f.label_score.toFixed(3) : "";
        const sourceLine = source
          ? `<p class="small muted">${esc(
              t("label_line", {
                source,
                score: score ? t("label_score", { score }) : "",
              })
            )}</p>`
          : `<p class="small muted">${esc(t("label_none"))}</p>`;
        return `
        <article class="face-card">
          <img src="/faces/${f.id}/crop?size=256" alt="face ${f.id}" />
          <div class="face-body">
            <p class="small muted">${esc(t("face_prefix", { id: f.id }))}</p>
            ${sourceLine}
            <select id="face-person-${f.id}">${personOptions(f.person_id)}</select>
            <input id="face-new-name-${f.id}" type="text" placeholder="${esc(t("new_person_name_ph"))}" />
            <div class="controls">
              <button class="btn ghost" data-action="assign-face" data-face-id="${f.id}">${esc(t("assign"))}</button>
              <button class="btn ghost" data-action="create-assign-face" data-face-id="${f.id}">${esc(t("create_and_assign"))}</button>
              <button class="btn danger" data-action="delete-face" data-face-id="${f.id}">${esc(t("not_face"))}</button>
            </div>
          </div>
        </article>
      `;
      }
    )
    .join("");
}

async function loadPeople() {
  try {
    state.showUnnamedPeople = Boolean(qs("people-show-unnamed")?.checked);
    const personsUrl = state.showUnnamedPeople
      ? "/persons?page=1&page_size=240&include_faces=true&sort_by=face_count&order=desc"
      : "/persons?page=1&page_size=240&include_faces=true&named_only=true&sort_by=face_count&order=desc";
    const [data, named] = await Promise.all([
      api(personsUrl),
      api("/persons?page=1&page_size=500&include_faces=false&named_only=true&sort_by=face_count&order=desc"),
    ]);
    state.persons = data.persons || [];
    state.namedPersons = named.persons || [];
    renderPeopleList();
    await loadUnassignedFaces(state.unassignedFacesPager.page || 1);
  } catch (e) {
    showToast(t("people_load_failed", { error: e.message }));
  }
}

function renderPeopleList() {
  const root = qs("people-list");
  if (!state.persons.length) {
    root.innerHTML = `<p class="muted">${esc(t("no_persons"))}</p>`;
    return;
  }
  const hint = state.showUnnamedPeople
    ? `<p class="small muted">${esc(t("people_hint_all"))}</p>`
    : `<p class="small muted">${esc(t("people_hint_named"))}</p>`;
  root.innerHTML =
    hint +
    state.persons
    .map((p) => {
      const display = p.display_name || t("person_fallback", { id: p.id });
      const samples = (p.sample_faces || [])
        .map((fid) => `<img src="/faces/${fid}/crop?size=256" alt="face ${fid}" />`)
        .join("");
      return `
        <article class="person-card">
          <p><strong>${esc(display)}</strong></p>
          <p class="small muted">${esc(t("person_stats", { id: p.id, count: p.face_count }))}</p>
          <input id="person-name-${p.id}" type="text" value="${esc(p.display_name || "")}" placeholder="${esc(t("display_name_ph"))}" />
          <div class="controls">
            <button class="btn ghost" data-action="rename-person" data-person-id="${p.id}">${esc(t("save_name"))}</button>
            <button class="btn ghost" data-action="view-person-assets" data-person-id="${p.id}">${esc(t("view_assets"))}</button>
          </div>
          <div class="person-samples">${samples}</div>
        </article>
      `;
    })
    .join("");
}

async function loadPersonAssets(personId, page = 1) {
  try {
    const targetPersonId = Number(personId) || null;
    if (!targetPersonId) return;
    const pageNum = Math.max(1, Number(page) || 1);
    const pageSize = state.personAssetsPager.pageSize || 120;
    const data = await api(`/search/person/${targetPersonId}?page=${pageNum}&page_size=${pageSize}`);
    const items = data.items || [];
    const total = Number(data.total) || items.length;
    state.personAssetsPager = {
      ...state.personAssetsPager,
      personId: targetPersonId,
      page: pageNum,
      pageSize,
      total,
      shown: items.length,
    };
    qs("person-assets-meta").textContent = t("person_assets_meta_paged", {
      id: targetPersonId,
      shown: items.length,
      total,
    });
    const normalized = items.map((x) => ({ id: x.id, path: x.path }));
    renderAssetGrid(normalized, "person-assets-grid");
    updatePersonAssetsPagerUi();
  } catch (e) {
    showToast(t("person_assets_load_failed", { error: e.message }));
  }
}

async function runPersonAssetsPage(delta) {
  const personId = Number(state.personAssetsPager.personId) || 0;
  if (!personId) return;
  const current = Math.max(1, Number(state.personAssetsPager.page) || 1);
  const target = Math.max(1, current + Number(delta || 0));
  if (target === current) return;
  await loadPersonAssets(personId, target);
}

async function runPersonAssetsJump() {
  const personId = Number(state.personAssetsPager.personId) || 0;
  if (!personId) return;
  const pages = pageCount(state.personAssetsPager.total, state.personAssetsPager.pageSize);
  const input = qs("person-assets-page-input");
  const target = parsePageInputValue(input?.value, pages);
  if (!target) return;

  const current = Math.max(1, Number(state.personAssetsPager.page) || 1);
  if (target === current) return;
  await loadPersonAssets(personId, target);
}

async function runUnassignedFacesPage(delta) {
  const current = Math.max(1, Number(state.unassignedFacesPager.page) || 1);
  const target = Math.max(1, current + Number(delta || 0));
  if (target === current) return;
  await loadUnassignedFaces(target);
}

async function runUnassignedFacesJump() {
  const pages = pageCount(state.unassignedFacesPager.total, state.unassignedFacesPager.pageSize);
  const input = qs("unassigned-page-input");
  const target = parsePageInputValue(input?.value, pages);
  if (!target) return;

  const current = Math.max(1, Number(state.unassignedFacesPager.page) || 1);
  if (target === current) return;
  await loadUnassignedFaces(target);
}

async function loadUnassignedFaces(page = 1) {
  try {
    const pageNum = Math.max(1, Number(page) || 1);
    const pageSize = state.unassignedFacesPager.pageSize || 120;
    const data = await api(`/faces?unassigned=true&page=${pageNum}&page_size=${pageSize}`);
    const faces = data.faces || [];
    const total = Number(data.total) || 0;
    const pages = pageCount(total, pageSize);
    if (pageNum > pages && total > 0) {
      await loadUnassignedFaces(pages);
      return;
    }
    state.unassignedFacesPager = {
      ...state.unassignedFacesPager,
      page: pageNum,
      pageSize,
      total,
      shown: faces.length,
    };
    const root = qs("unassigned-faces");
    if (!faces.length) {
      root.innerHTML = `<p class="muted">${esc(t("no_unassigned_faces"))}</p>`;
      updateUnassignedFacesPagerUi();
      return;
    }
    root.innerHTML = faces
      .map(
        (f) => `
          <article class="face-card">
            <img src="/faces/${f.id}/crop?size=256" alt="face ${f.id}" />
            <div class="face-body">
              <p class="small muted">${esc(t("face_asset_prefix", { face: f.id, asset: f.asset_id }))}</p>
              <select id="face-person-unassigned-${f.id}">${personOptions(null)}</select>
              <input id="face-new-name-unassigned-${f.id}" type="text" placeholder="${esc(t("new_person_name_ph"))}" />
              <div class="controls">
                <button class="btn ghost" data-action="assign-face-unassigned" data-face-id="${f.id}">${esc(t("assign"))}</button>
                <button class="btn ghost" data-action="create-assign-face-unassigned" data-face-id="${f.id}">${esc(t("create_and_assign"))}</button>
                <button class="btn danger" data-action="delete-face-unassigned" data-face-id="${f.id}">${esc(t("not_face"))}</button>
              </div>
            </div>
          </article>
        `
      )
      .join("");
    updateUnassignedFacesPagerUi();
  } catch (e) {
    showToast(t("unassigned_faces_load_failed", { error: e.message }));
  }
}

async function loadTasks() {
  try {
    const [data, metrics, usage] = await Promise.all([
      api("/tasks?page=1&page_size=180"),
      api("/metrics"),
      api("/system/usage").catch(() => null),
    ]);
    const tasks = data.tasks || [];
    const byStateGlobal = metrics?.tasks?.by_state || {};
    const totalGlobal = metrics?.tasks?.total ?? data.total ?? tasks.length;
    const pendingGlobal = byStateGlobal.pending || 0;
    const runningGlobal = byStateGlobal.running || 0;
    const failedGlobal = byStateGlobal.failed || 0;
    const deadGlobal = byStateGlobal.dead || 0;
    qs("task-meta").textContent = t("task_meta_with_page", {
      total: totalGlobal,
      pending: pendingGlobal,
      running: runningGlobal,
      failed: failedGlobal,
      dead: deadGlobal,
      shown: tasks.length,
    });
    renderSystemUsage(usage);
    qs("task-rows").innerHTML = tasks
      .map((task) => {
        const progress = task.progress_total ? `${task.progress_current || 0}/${task.progress_total}` : "-";
        const canCancel = task.state === "pending" || task.state === "running";
        return `
          <tr>
            <td>${task.id}</td>
            <td>${esc(task.type)}</td>
            <td>${esc(task.state)}</td>
            <td>${esc(progress)}</td>
            <td>${task.retry_count || 0}</td>
            <td class="small muted">${esc((task.last_error || "").slice(0, 120))}</td>
            <td>${canCancel ? `<button class="btn danger" data-action="cancel-task" data-task-id="${task.id}">${esc(t("cancel"))}</button>` : ""}</td>
          </tr>
        `;
      })
      .join("");
  } catch (e) {
    showToast(t("task_load_failed", { error: e.message }));
  }
}

async function refreshAdminPanels() {
  try {
    const [health, metrics, lvface, caption] = await Promise.all([
      api("/health"),
      api("/metrics"),
      api("/health/lvface"),
      api("/health/caption"),
    ]);
    qs("admin-health").textContent = JSON.stringify(health, null, 2);
    qs("admin-metrics").textContent = JSON.stringify(metrics, null, 2);
    qs("admin-services").textContent = JSON.stringify({ lvface, caption }, null, 2);
  } catch (e) {
    showToast(t("admin_refresh_failed", { error: e.message }));
  }
}

async function handleCaptionActions(event) {
  const btn = event.target.closest("button[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;
  const captionId = Number(btn.dataset.captionId);
  if (!captionId) return;
  try {
    if (action === "save-caption") {
      const text = qs(`caption-text-${captionId}`).value;
      await api(`/captions/${captionId}`, {
        method: "PATCH",
        body: JSON.stringify({ text, user_edited: true }),
      });
      showToast(t("caption_saved", { id: captionId }));
    } else if (action === "delete-caption") {
      await api(`/captions/${captionId}`, { method: "DELETE" });
      showToast(t("caption_deleted", { id: captionId }));
    }
    if (state.selectedAsset) {
      await loadAssetInspector(state.selectedAsset.id);
    }
  } catch (e) {
    showToast(t("caption_action_failed", { error: e.message }));
  }
}

async function ensureNamedPerson(nameRaw) {
  const name = String(nameRaw || "").trim();
  if (!name) {
    showToast(t("person_name_required"));
    return null;
  }
  const data = await api("/persons", {
    method: "POST",
    body: JSON.stringify({ display_name: name }),
  });
  const personId = Number(data?.person_id || 0);
  if (!personId) {
    throw new Error(t("invalid_person_selection"));
  }
  const displayName = String(data?.display_name || name);
  if (data?.created) {
    showToast(t("person_created", { name: displayName }));
  } else {
    showToast(t("person_exists_reused", { name: displayName }));
  }
  return { personId, displayName };
}

async function assignFace(faceId, selectorId, newNameInputId = null) {
  const select = qs(selectorId);
  const selected = String(select?.value || "");
  if (!selected) {
    showToast(t("select_target_first"));
    return;
  }

  if (selected === "__NEW__") {
    const nameRaw = newNameInputId ? qs(newNameInputId)?.value : "";
    const person = await ensureNamedPerson(nameRaw);
    if (!person) return;
    await api(`/faces/${faceId}/assign`, {
      method: "POST",
      body: JSON.stringify({ person_id: person.personId }),
    });
    return;
  }

  if (selected === "__DELETE__") {
    if (!window.confirm(t("confirm_delete_face", { id: faceId }))) return;
    await deleteFace(faceId);
    return;
  }

  const personId = Number(selected);
  if (!personId) {
    showToast(t("invalid_person_selection"));
    return;
  }
  await api(`/faces/${faceId}/assign`, {
    method: "POST",
    body: JSON.stringify({ person_id: personId }),
  });
}

async function createAndAssignFaceByName(faceId, inputId) {
  const person = await ensureNamedPerson(qs(inputId)?.value || "");
  if (!person) return;
  await api(`/faces/${faceId}/assign`, {
    method: "POST",
    body: JSON.stringify({ person_id: person.personId }),
  });
}

async function createPersonFromFace(faceId) {
  await api(`/faces/${faceId}/assign`, {
    method: "POST",
    body: JSON.stringify({ create_new: true }),
  });
}

async function deleteFace(faceId) {
  await api(`/faces/${faceId}?prune_empty_person=true`, {
    method: "DELETE",
  });
}

function initEvents() {
  document.querySelectorAll(".lang-btn").forEach((el) => {
    el.addEventListener("click", () => {
      const lang = el.dataset.lang === "zh" ? "zh" : "en";
      setLanguage(lang, true);
      const url = new URL(window.location.href);
      url.searchParams.set("lang", lang);
      window.history.replaceState(null, "", url.toString());
    });
  });

  document.querySelectorAll(".tab").forEach((el) => {
    el.addEventListener("click", async () => {
      setActiveTab(el.dataset.tab);
      if (el.dataset.tab === "tasks") await loadTasks();
      if (el.dataset.tab === "admin") await refreshAdminPanels();
      if (el.dataset.tab === "people") await loadPeople();
      if (el.dataset.tab === "tags") {
        await loadTagsCatalog(state.tagsPager.page || 1);
        if (state.tagsAssetsPager.tagId) {
          await loadTagAssets(state.tagsAssetsPager.tagId, state.tagsAssetsPager.page || 1);
        }
      }
      if (el.dataset.tab === "map") await loadGeoMap();
    });
  });

  qs("btn-refresh-all").addEventListener("click", async () => {
    await Promise.all([refreshDashboard(), loadTasks(), loadPeople(), refreshAdminPanels()]);
    if (state.activeTab === "tags") {
      await loadTagsCatalog(state.tagsPager.page || 1);
      if (state.tagsAssetsPager.tagId) {
        await loadTagAssets(state.tagsAssetsPager.tagId, state.tagsAssetsPager.page || 1);
      }
    }
    if (state.activeTab === "map") await loadGeoMap();
    showToast(t("refreshed"));
  });
  const voiceBtn = qs("btn-voice-command");
  if (voiceBtn) {
    voiceBtn.addEventListener("click", runVoiceCommandCapture);
  }

  qs("btn-search").addEventListener("click", () => runSearch(1, false));
  qs("btn-library-load").addEventListener("click", () => loadLibraryLatest(1));
  qs("btn-library-prev").addEventListener("click", () => runLibraryPage(-1));
  qs("btn-library-next").addEventListener("click", () => runLibraryPage(1));
  qs("btn-library-jump").addEventListener("click", runLibraryJump);
  qs("library-page-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runLibraryJump();
  });
  qs("search-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch(1, false);
  });

  qs("library-grid").addEventListener("click", async (e) => {
    const card = e.target.closest(".asset-card");
    if (!card) return;
    state.inspectorOriginTab = "library";
    await loadAssetInspector(Number(card.dataset.assetId));
  });

  qs("person-assets-grid").addEventListener("click", async (e) => {
    const card = e.target.closest(".asset-card");
    if (!card) return;
    const originTab = state.activeTab;
    setActiveTab("library");
    state.inspectorOriginTab = originTab;
    await loadAssetInspector(Number(card.dataset.assetId));
  });

  qs("tag-assets-grid").addEventListener("click", async (e) => {
    const card = e.target.closest(".asset-card");
    if (!card) return;
    const originTab = state.activeTab;
    setActiveTab("library");
    state.inspectorOriginTab = originTab;
    await loadAssetInspector(Number(card.dataset.assetId));
  });

  qs("btn-asset-back").addEventListener("click", async () => {
    const returnTab = state.inspectorOriginTab || "library";
    closeAssetInspector();
    if (returnTab !== "library") {
      setActiveTab(returnTab);
      if (returnTab === "people") await loadPeople();
      if (returnTab === "tags") {
        await loadTagsCatalog(state.tagsPager.page || 1);
        if (state.tagsAssetsPager.tagId) {
          await loadTagAssets(state.tagsAssetsPager.tagId, state.tagsAssetsPager.page || 1);
        }
      }
      if (returnTab === "map") await loadGeoMap();
      if (returnTab === "tasks") await loadTasks();
      if (returnTab === "admin") await refreshAdminPanels();
    }
  });

  qs("btn-preview-fullscreen").addEventListener("click", openPreviewModal);
  qs("btn-preview-close").addEventListener("click", closePreviewModal);
  qs("preview-modal").addEventListener("click", (e) => {
    if (e.target.id === "preview-modal") {
      closePreviewModal();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closePreviewModal();
    }
  });

  qs("caption-list").addEventListener("click", handleCaptionActions);

  qs("btn-caption-regenerate").addEventListener("click", async () => {
    if (!state.selectedAsset) return;
    try {
      await api(`/assets/${state.selectedAsset.id}/captions/regenerate`, {
        method: "POST",
        body: JSON.stringify({ force: false }),
      });
      showToast(t("caption_regen_enqueued"));
      await loadTasks();
    } catch (e) {
      showToast(t("regenerate_failed", { error: e.message }));
    }
  });

  qs("btn-add-tags").addEventListener("click", async () => {
    if (!state.selectedAsset) return;
    const names = String(qs("tag-input").value || "")
      .split(",")
      .map((v) => v.trim())
      .filter((v) => v);
    if (!names.length) {
      showToast(t("no_tag_entered"));
      return;
    }
    try {
      await api(`/assets/${state.selectedAsset.id}/tags`, {
        method: "POST",
        body: JSON.stringify({ names }),
      });
      qs("tag-input").value = "";
      await loadAssetInspector(state.selectedAsset.id);
      showToast(t("tags_updated"));
    } catch (e) {
      showToast(t("tag_update_failed", { error: e.message }));
    }
  });

  qs("tag-list").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action='remove-tag']");
    if (!btn || !state.selectedAsset) return;
    const tagId = Number(btn.dataset.tagId);
    if (!tagId) return;
    try {
      await api(`/assets/${state.selectedAsset.id}/tags`, {
        method: "DELETE",
        body: JSON.stringify({ tag_ids: [tagId], block_auto: true }),
      });
      await loadAssetInspector(state.selectedAsset.id);
      showToast(t("tag_removed"));
    } catch (err) {
      showToast(t("tag_update_failed", { error: err.message }));
    }
  });

  qs("face-list").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const faceId = Number(btn.dataset.faceId);
    if (!faceId) return;
    try {
      if (btn.dataset.action === "assign-face") {
        await assignFace(faceId, `face-person-${faceId}`, `face-new-name-${faceId}`);
      } else if (btn.dataset.action === "create-assign-face") {
        await createAndAssignFaceByName(faceId, `face-new-name-${faceId}`);
      } else if (btn.dataset.action === "create-person-face") {
        await createPersonFromFace(faceId);
      } else if (btn.dataset.action === "delete-face") {
        if (!window.confirm(t("confirm_delete_face", { id: faceId }))) return;
        await deleteFace(faceId);
      }
      await loadPeople();
      if (state.selectedAsset) {
        await loadAssetInspector(state.selectedAsset.id);
      }
      showToast(t("face_updated", { id: faceId }));
    } catch (err) {
      showToast(t("face_assignment_failed", { error: err.message }));
    }
  });

  qs("people-list").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const personId = Number(btn.dataset.personId);
    if (!personId) return;
    try {
      if (btn.dataset.action === "rename-person") {
        const name = qs(`person-name-${personId}`).value.trim();
        await api(`/persons/${personId}/name`, {
          method: "POST",
          body: JSON.stringify({ display_name: name }),
        });
        await loadPeople();
        showToast(t("person_renamed", { id: personId }));
      } else if (btn.dataset.action === "view-person-assets") {
        await loadPersonAssets(personId, 1);
      }
    } catch (err) {
      showToast(t("person_action_failed", { error: err.message }));
    }
  });

  qs("unassigned-faces").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const faceId = Number(btn.dataset.faceId);
    if (!faceId) return;
    try {
      if (btn.dataset.action === "assign-face-unassigned") {
        await assignFace(faceId, `face-person-unassigned-${faceId}`, `face-new-name-unassigned-${faceId}`);
      } else if (btn.dataset.action === "create-assign-face-unassigned") {
        await createAndAssignFaceByName(faceId, `face-new-name-unassigned-${faceId}`);
      } else if (btn.dataset.action === "create-person-face") {
        await createPersonFromFace(faceId);
      } else if (btn.dataset.action === "delete-face-unassigned") {
        if (!window.confirm(t("confirm_delete_face", { id: faceId }))) return;
        await deleteFace(faceId);
      }
      await loadPeople();
      showToast(t("face_updated", { id: faceId }));
    } catch (err) {
      showToast(t("unassigned_face_action_failed", { error: err.message }));
    }
  });

  qs("btn-refresh-people").addEventListener("click", loadPeople);
  qs("btn-person-assets-prev").addEventListener("click", () => runPersonAssetsPage(-1));
  qs("btn-person-assets-next").addEventListener("click", () => runPersonAssetsPage(1));
  qs("btn-person-assets-jump").addEventListener("click", runPersonAssetsJump);
  qs("person-assets-page-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runPersonAssetsJump();
  });
  qs("btn-unassigned-prev").addEventListener("click", () => runUnassignedFacesPage(-1));
  qs("btn-unassigned-next").addEventListener("click", () => runUnassignedFacesPage(1));
  qs("btn-unassigned-jump").addEventListener("click", runUnassignedFacesJump);
  qs("unassigned-page-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runUnassignedFacesJump();
  });
  qs("people-show-unnamed").addEventListener("change", loadPeople);
  const createPersonBtn = qs("btn-create-person");
  if (createPersonBtn) {
    createPersonBtn.addEventListener("click", async () => {
      try {
        const person = await ensureNamedPerson(qs("people-new-person-name")?.value || "");
        if (!person) return;
        qs("people-new-person-name").value = "";
        await loadPeople();
      } catch (err) {
        showToast(t("person_action_failed", { error: err.message }));
      }
    });
  }
  qs("btn-refresh-map").addEventListener("click", loadGeoMap);
  qs("map-media-filter").addEventListener("change", loadGeoMap);
  qs("btn-refresh-tags").addEventListener("click", () => loadTagsCatalog(1));
  qs("btn-tags-prev").addEventListener("click", () => runTagsPage(-1));
  qs("btn-tags-next").addEventListener("click", () => runTagsPage(1));
  qs("btn-tags-jump").addEventListener("click", runTagsJump);
  qs("tags-page-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runTagsJump();
  });
  qs("tags-filter-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadTagsCatalog(1);
  });
  qs("tags-filter-source").addEventListener("change", () => loadTagsCatalog(1));
  qs("btn-refresh-tag-assets").addEventListener("click", () => {
    if (!state.tagsAssetsPager.tagId) return;
    loadTagAssets(state.tagsAssetsPager.tagId, 1);
  });
  qs("tag-assets-media").addEventListener("change", () => {
    if (!state.tagsAssetsPager.tagId) return;
    loadTagAssets(state.tagsAssetsPager.tagId, 1);
  });
  qs("tag-assets-source").addEventListener("change", () => {
    if (!state.tagsAssetsPager.tagId) return;
    loadTagAssets(state.tagsAssetsPager.tagId, 1);
  });
  qs("btn-tag-assets-prev").addEventListener("click", () => runTagAssetsPage(-1));
  qs("btn-tag-assets-next").addEventListener("click", () => runTagAssetsPage(1));
  qs("btn-tag-assets-jump").addEventListener("click", runTagAssetsJump);
  qs("tag-assets-page-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runTagAssetsJump();
  });
  qs("btn-refresh-tasks").addEventListener("click", loadTasks);

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action='map-open-asset']");
    if (!btn) return;
    const assetId = Number(btn.dataset.assetId);
    if (!assetId) return;
    const originTab = state.activeTab;
    setActiveTab("library");
    state.inspectorOriginTab = originTab;
    await loadAssetInspector(assetId);
  });

  qs("task-rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action='cancel-task']");
    if (!btn) return;
    const taskId = Number(btn.dataset.taskId);
    if (!taskId) return;
    try {
      await api(`/tasks/${taskId}/cancel`, { method: "POST" });
      await loadTasks();
      showToast(t("task_cancel_requested", { id: taskId }));
    } catch (err) {
      showToast(t("cancel_failed", { error: err.message }));
    }
  });

  qs("tags-rows").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    if (btn.dataset.action === "tags-view-assets") {
      const tagId = Number(btn.dataset.tagId || 0);
      if (!tagId) return;
      await loadTagAssets(tagId, 1);
      await loadTagsCatalog(state.tagsPager.page || 1);
      return;
    }
    if (btn.dataset.action === "tags-open-search") {
      const tagName = String(btn.dataset.tagName || "").trim();
      if (!tagName) return;
      setActiveTab("library");
      qs("search-mode").value = "smart";
      qs("search-query").value = "";
      qs("search-tags").value = tagName;
      qs("search-media").value = "all";
      await runSearch(1, false);
    }
  });

  qs("btn-rebuild-index").addEventListener("click", async () => {
    try {
      await api("/vector-index/rebuild", { method: "POST" });
      showToast(t("vector_rebuild_triggered"));
      await refreshAdminPanels();
    } catch (e) {
      showToast(t("rebuild_failed", { error: e.message }));
    }
  });

  qs("btn-recluster").addEventListener("click", async () => {
    try {
      await api("/persons/recluster", { method: "POST" });
      showToast(t("recluster_queued"));
      await loadTasks();
    } catch (e) {
      showToast(t("recluster_failed", { error: e.message }));
    }
  });

  qs("btn-ingest").addEventListener("click", async () => {
    const root = String(qs("ingest-root").value || "").trim();
    if (!root) {
      showToast(t("provide_ingest_root"));
      return;
    }
    try {
      await api("/ingest/scan", {
        method: "POST",
        body: JSON.stringify({ roots: [root] }),
      });
      showToast(t("ingest_started", { root }));
      await loadTasks();
    } catch (e) {
      showToast(t("ingest_failed", { error: e.message }));
    }
  });
}

async function bootstrap() {
  const params = new URLSearchParams(window.location.search);
  const langParam = params.get("lang");
  const storedLang = window.localStorage.getItem("vlm_ui_lang");
  setLanguage(langParam || storedLang || "en", false);
  initEvents();
  const tab = params.get("tab");
  if (tab && ["library", "people", "tags", "map", "tasks", "admin"].includes(tab)) {
    setActiveTab(tab);
  }
  const q = params.get("q");
  if (q) {
    qs("search-query").value = q;
  }
  await Promise.all([refreshDashboard(), loadLibraryLatest(), loadPeople(), loadTasks(), refreshAdminPanels()]);
  if (state.activeTab === "tags") {
    await loadTagsCatalog(1);
    if (state.tagsAssetsPager.tagId) {
      await loadTagAssets(state.tagsAssetsPager.tagId, 1);
    } else {
      updateTagAssetsPagerUi();
    }
  }
  if (state.activeTab === "map") {
    await loadGeoMap();
  }
  if (q) {
    await runSearch(1, false);
  }

  window.setInterval(async () => {
    await refreshDashboard();
    if (state.activeTab === "tasks") await loadTasks();
  }, 10000);
}

window.addEventListener("DOMContentLoaded", bootstrap);
