import os
from pydantic import BaseModel, Field
from functools import lru_cache

def _default_data_root() -> str:
    return os.getenv("VLM_DATA_ROOT", r"E:\VLM_DATA")

def _default_originals_path() -> str:
    return os.getenv("ORIGINALS_PATH", r"E:\01_INCOMING")

def _default_derived_path() -> str:
    return os.getenv("DERIVED_PATH", os.path.join(_default_data_root(), "derived"))

def _default_vector_index_path() -> str:
    return os.getenv("VECTOR_INDEX_PATH", os.path.join(_default_derived_path(), "vector.index"))

def _default_database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    db_path = os.path.join(_default_data_root(), "databases", "metadata.sqlite").replace("\\", "/")
    if db_path.startswith("/"):
        return f"sqlite://{db_path}"
    return f"sqlite:///{db_path}"

class Settings(BaseModel):
    deploy_profile: str = Field(default=os.getenv("DEPLOY_PROFILE", "P1"))  # P1,P2,P3,P4
    run_mode: str = Field(default=os.getenv("RUN_MODE", "api"))  # api|worker|all
    database_url: str = Field(default=_default_database_url())
    vector_backend: str = Field(default=os.getenv("VECTOR_BACKEND", "faiss"))  # faiss|qdrant (future)
    originals_path: str = Field(default=_default_originals_path())
    derived_path: str = Field(default=_default_derived_path())
    enable_inline_worker: bool = Field(default=os.getenv("ENABLE_INLINE_WORKER", "true").lower() == "true")
    worker_poll_interval: float = Field(default=float(os.getenv("WORKER_POLL_INTERVAL", "2.0")))
    max_task_batch: int = Field(default=int(os.getenv("WORKER_MAX_BATCH", "10")))
    auto_migrate: bool = Field(default=os.getenv('AUTO_MIGRATE', 'true').lower()=='true')
    alembic_script_location: str = Field(default=os.getenv('ALEMBIC_SCRIPT_LOCATION','migrations'))
    log_format: str = Field(default=os.getenv('LOG_FORMAT','text'))  # text|json
    log_level: str = Field(default=os.getenv('LOG_LEVEL','INFO'))
    request_log_body: bool = Field(default=os.getenv('REQUEST_LOG_BODY','false').lower()=='true')
    slow_request_ms: int = Field(default=int(os.getenv('SLOW_REQUEST_MS','1000')))
    vector_index_backend: str = Field(default=os.getenv('VECTOR_INDEX_BACKEND','memory'))  # memory|faiss (future)
    vector_index_path: str = Field(default=_default_vector_index_path())
    vector_index_autosave: bool = Field(default=os.getenv('VECTOR_INDEX_AUTOSAVE','true').lower()=='true')
    vector_index_save_interval: int = Field(default=int(os.getenv('VECTOR_INDEX_SAVE_INTERVAL','300')))  # seconds
    embed_model_image: str = Field(default=os.getenv('EMBED_MODEL_IMAGE','stub-clip'))
    embed_model_text: str = Field(default=os.getenv('EMBED_MODEL_TEXT','stub-clip'))
    embed_device: str = Field(default=os.getenv('EMBED_DEVICE', 'cpu'))  # cpu|cuda
    embed_model_version: str = Field(default=os.getenv('EMBED_MODEL_VERSION',''))  # optional explicit version tag
    embed_reembed_startup_limit: int = Field(default=int(os.getenv('EMBED_REEMBED_STARTUP_LIMIT','1000')))
    max_index_load: int = Field(default=int(os.getenv('MAX_INDEX_LOAD','200000')))
    vector_index_autoload: bool = Field(default=os.getenv('VECTOR_INDEX_AUTOLOAD','true').lower()=='true')
    vector_index_rebuild_on_demand_only: bool = Field(default=os.getenv('VECTOR_INDEX_REBUILD_ON_DEMAND_ONLY','false').lower()=='true')
    face_cluster_threshold: float = Field(default=float(os.getenv('FACE_CLUSTER_THRESHOLD','0.35')))
    face_recluster_batch_limit: int = Field(default=int(os.getenv('FACE_RECLUSTER_BATCH_LIMIT','2000')))
    face_embed_provider: str = Field(default=os.getenv('FACE_EMBED_PROVIDER', 'stub'))  # stub|facenet|insight
    face_embed_model: str = Field(default=os.getenv('FACE_EMBED_MODEL', 'stub-v1'))
    face_embed_dim: int = Field(default=int(os.getenv('FACE_EMBED_DIM', '128')))
    face_detect_provider: str = Field(default=os.getenv('FACE_DETECT_PROVIDER','scrfd'))  # stub|mtcnn|insight|scrfd|auto
    face_crop_margin: float = Field(default=float(os.getenv('FACE_CROP_MARGIN','0.0')))  # fraction of max(w,h) to expand each side
    lvface_model_path: str = Field(default=os.getenv('LVFACE_MODEL_PATH', 'models/lvface.onnx'))
    lvface_external_dir: str = Field(default=os.getenv('LVFACE_EXTERNAL_DIR', ''))  # Path to external LVFace installation
    lvface_python_exe: str = Field(default=os.getenv('LVFACE_PYTHON_EXE', ''))  # Optional dedicated python for external LVFace subprocess
    lvface_model_name: str = Field(default=os.getenv('LVFACE_MODEL_NAME', 'lvface.onnx'))  # Model filename in external dir
    lvface_service_url: str = Field(default=os.getenv('LVFACE_SERVICE_URL', ''))  # Optional LVFace HTTP service URL
    caption_provider: str = Field(default=os.getenv('CAPTION_PROVIDER', 'http'))  # stub|blip2|llava|qwen2.5-vl|qwen3-vl|auto|http
    caption_device: str = Field(default=os.getenv('CAPTION_DEVICE', 'cpu'))  # cpu|cuda
    caption_model: str = Field(default=os.getenv('CAPTION_MODEL', 'auto'))  # model name override
    caption_external_dir: str = Field(default=os.getenv('CAPTION_EXTERNAL_DIR', ''))  # Path to external caption models installation
    caption_service_url: str = Field(default=os.getenv('CAPTION_SERVICE_URL', 'http://127.0.0.1:8102'))  # HTTP caption service URL
    image_tag_provider: str = Field(default=os.getenv('IMAGE_TAG_PROVIDER', 'stub'))  # stub|http|auto
    image_tag_service_url: str = Field(default=os.getenv('IMAGE_TAG_SERVICE_URL', 'http://127.0.0.1:8112'))
    image_tag_model: str = Field(default=os.getenv('IMAGE_TAG_MODEL', 'ram-plus'))
    image_tag_auto_enable: bool = Field(default=os.getenv('IMAGE_TAG_AUTO_ENABLE', 'false').lower()=='true')
    image_tag_auto_enqueue: bool = Field(default=os.getenv('IMAGE_TAG_AUTO_ENQUEUE', 'false').lower()=='true')
    worker_concurrency: int = Field(default=int(os.getenv('WORKER_CONCURRENCY','1')))
    max_task_retries: int = Field(default=int(os.getenv('MAX_TASK_RETRIES','3')))
    # Backoff configuration (supports legacy env var synonyms)
    retry_backoff_base_seconds: float = Field(default=float(os.getenv('RETRY_BACKOFF_BASE_SECONDS', os.getenv('RETRY_BACKOFF_BASE','2.0'))))
    retry_backoff_cap_seconds: float = Field(default=float(os.getenv('RETRY_BACKOFF_CAP_SECONDS', os.getenv('RETRY_BACKOFF_CAP','300'))))
    retry_backoff_jitter: float = Field(default=float(os.getenv('RETRY_BACKOFF_JITTER','0.25')))
    # --- Video (MVP scaffolding) ---
    video_enabled: bool = Field(default=os.getenv('VIDEO_ENABLED', 'false').lower() == 'true')
    video_keyframe_interval_sec: float = Field(default=float(os.getenv('VIDEO_KEYFRAME_INTERVAL_SEC', '2.0')))
    video_extensions: str = Field(default=os.getenv('VIDEO_EXTENSIONS', '.mp4,.mov,.mkv,.avi,.m4v'))
    video_scene_detect: bool = Field(default=os.getenv('VIDEO_SCENE_DETECT', 'false').lower() == 'true')
    video_scene_min_sec: float = Field(default=float(os.getenv('VIDEO_SCENE_MIN_SEC', '1.0')))
    # --- Voice/ASR/TTS (optional external service) ---
    voice_enabled: bool = Field(default=os.getenv('VOICE_ENABLED', 'false').lower() == 'true')
    voice_provider: str = Field(default=os.getenv('VOICE_PROVIDER', 'external'))  # external|local
    voice_external_base_url: str = Field(default=os.getenv('VOICE_EXTERNAL_BASE_URL', ''))
    # Defaults aligned to llmytranslate API
    voice_asr_path: str = Field(default=os.getenv('VOICE_ASR_PATH', '/api/voice-chat/transcribe'))
    voice_tts_path: str = Field(default=os.getenv('VOICE_TTS_PATH', '/api/tts/synthesize'))
    voice_conversation_path: str = Field(default=os.getenv('VOICE_CONVERSATION_PATH', '/api/voice-chat/conversation'))
    voice_health_path: str = Field(default=os.getenv('VOICE_HEALTH_PATH', '/api/voice-chat/health'))
    voice_capabilities_path: str = Field(default=os.getenv('VOICE_CAPABILITIES_PATH', '/api/voice-chat/capabilities'))
    voice_api_key: str = Field(default=os.getenv('VOICE_API_KEY', ''))
    voice_timeout_sec: float = Field(default=float(os.getenv('VOICE_TIMEOUT_SEC', '30')))
    # Optional local TTS fallback (e.g., Piper) when external TTS is unavailable
    tts_fallback_provider: str = Field(default=os.getenv('TTS_FALLBACK_PROVIDER', 'none'))  # none|piper
    piper_exe_path: str = Field(default=os.getenv('PIPER_EXE_PATH', ''))
    piper_model_path: str = Field(default=os.getenv('PIPER_MODEL_PATH', ''))

@lru_cache
def get_settings() -> Settings:
    # Read environment variables at call time so overrides (e.g., in tests) take effect
    return Settings(
        deploy_profile=os.getenv("DEPLOY_PROFILE", "P1"),
        run_mode=os.getenv("RUN_MODE", "api"),
        database_url=_default_database_url(),
        vector_backend=os.getenv("VECTOR_BACKEND", "faiss"),
        originals_path=_default_originals_path(),
        derived_path=_default_derived_path(),
        enable_inline_worker=os.getenv("ENABLE_INLINE_WORKER", "true").lower() == "true",
        worker_poll_interval=float(os.getenv("WORKER_POLL_INTERVAL", "2.0")),
        max_task_batch=int(os.getenv("WORKER_MAX_BATCH", "10")),
        auto_migrate=os.getenv('AUTO_MIGRATE', 'true').lower()=='true',
        alembic_script_location=os.getenv('ALEMBIC_SCRIPT_LOCATION','migrations'),
        log_format=os.getenv('LOG_FORMAT','text'),
        log_level=os.getenv('LOG_LEVEL','INFO'),
        request_log_body=os.getenv('REQUEST_LOG_BODY','false').lower()=='true',
        slow_request_ms=int(os.getenv('SLOW_REQUEST_MS','1000')),
        vector_index_backend=os.getenv('VECTOR_INDEX_BACKEND','memory'),
        vector_index_path=_default_vector_index_path(),
        vector_index_autosave=os.getenv('VECTOR_INDEX_AUTOSAVE','true').lower()=='true',
        vector_index_save_interval=int(os.getenv('VECTOR_INDEX_SAVE_INTERVAL','300')),
        embed_model_image=os.getenv('EMBED_MODEL_IMAGE','stub-clip'),
        embed_model_text=os.getenv('EMBED_MODEL_TEXT','stub-clip'),
        embed_device=os.getenv('EMBED_DEVICE', 'cpu'),
        embed_model_version=os.getenv('EMBED_MODEL_VERSION',''),
        embed_reembed_startup_limit=int(os.getenv('EMBED_REEMBED_STARTUP_LIMIT','1000')),
        max_index_load=int(os.getenv('MAX_INDEX_LOAD','200000')),
        vector_index_autoload=os.getenv('VECTOR_INDEX_AUTOLOAD','true').lower()=='true',
        vector_index_rebuild_on_demand_only=os.getenv('VECTOR_INDEX_REBUILD_ON_DEMAND_ONLY','false').lower()=='true',
        face_cluster_threshold=float(os.getenv('FACE_CLUSTER_THRESHOLD','0.35')),
    face_recluster_batch_limit=int(os.getenv('FACE_RECLUSTER_BATCH_LIMIT','2000')),
    face_embed_provider=os.getenv('FACE_EMBED_PROVIDER','stub'),
    face_embed_model=os.getenv('FACE_EMBED_MODEL','stub-v1'),
    face_embed_dim=int(os.getenv('FACE_EMBED_DIM','128')),
    face_detect_provider=os.getenv('FACE_DETECT_PROVIDER','scrfd'),
    face_crop_margin=float(os.getenv('FACE_CROP_MARGIN','0.0')),
        lvface_model_path=os.getenv('LVFACE_MODEL_PATH', 'models/lvface.onnx'),
        lvface_external_dir=os.getenv('LVFACE_EXTERNAL_DIR', ''),
        lvface_python_exe=os.getenv('LVFACE_PYTHON_EXE', ''),
        lvface_model_name=os.getenv('LVFACE_MODEL_NAME', 'lvface.onnx'),
        lvface_service_url=os.getenv('LVFACE_SERVICE_URL', ''),
        caption_provider=os.getenv('CAPTION_PROVIDER', 'http'),
        caption_device=os.getenv('CAPTION_DEVICE', 'cpu'),
        caption_model=os.getenv('CAPTION_MODEL', 'auto'),
        caption_external_dir=os.getenv('CAPTION_EXTERNAL_DIR', ''),
        caption_service_url=os.getenv('CAPTION_SERVICE_URL', 'http://127.0.0.1:8102'),
        image_tag_provider=os.getenv('IMAGE_TAG_PROVIDER', 'stub'),
        image_tag_service_url=os.getenv('IMAGE_TAG_SERVICE_URL', 'http://127.0.0.1:8112'),
        image_tag_model=os.getenv('IMAGE_TAG_MODEL', 'ram-plus'),
        image_tag_auto_enable=os.getenv('IMAGE_TAG_AUTO_ENABLE', 'false').lower()=='true',
        image_tag_auto_enqueue=os.getenv('IMAGE_TAG_AUTO_ENQUEUE', 'false').lower()=='true',
        worker_concurrency=int(os.getenv('WORKER_CONCURRENCY','1')),
        max_task_retries=int(os.getenv('MAX_TASK_RETRIES','3')),
    retry_backoff_base_seconds=float(os.getenv('RETRY_BACKOFF_BASE_SECONDS', os.getenv('RETRY_BACKOFF_BASE','2.0'))),
    retry_backoff_cap_seconds=float(os.getenv('RETRY_BACKOFF_CAP_SECONDS', os.getenv('RETRY_BACKOFF_CAP','300'))),
    retry_backoff_jitter=float(os.getenv('RETRY_BACKOFF_JITTER','0.25')),
    # --- Video (MVP scaffolding) ---
    video_enabled=os.getenv('VIDEO_ENABLED', 'false').lower() == 'true',
    video_keyframe_interval_sec=float(os.getenv('VIDEO_KEYFRAME_INTERVAL_SEC', '2.0')),
    video_extensions=os.getenv('VIDEO_EXTENSIONS', '.mp4,.mov,.mkv,.avi,.m4v'),
    video_scene_detect=os.getenv('VIDEO_SCENE_DETECT', 'false').lower() == 'true',
    video_scene_min_sec=float(os.getenv('VIDEO_SCENE_MIN_SEC', '1.0')),
    # --- Voice/ASR/TTS ---
    voice_enabled=os.getenv('VOICE_ENABLED', 'false').lower() == 'true',
    voice_provider=os.getenv('VOICE_PROVIDER', 'external'),
    voice_external_base_url=os.getenv('VOICE_EXTERNAL_BASE_URL', ''),
    voice_asr_path=os.getenv('VOICE_ASR_PATH', '/api/voice-chat/transcribe'),
    voice_tts_path=os.getenv('VOICE_TTS_PATH', '/api/tts/synthesize'),
    voice_conversation_path=os.getenv('VOICE_CONVERSATION_PATH', '/api/voice-chat/conversation'),
    voice_health_path=os.getenv('VOICE_HEALTH_PATH', '/api/voice-chat/health'),
    voice_capabilities_path=os.getenv('VOICE_CAPABILITIES_PATH', '/api/voice-chat/capabilities'),
    voice_api_key=os.getenv('VOICE_API_KEY', ''),
    voice_timeout_sec=float(os.getenv('VOICE_TIMEOUT_SEC', '30')),
    tts_fallback_provider=os.getenv('TTS_FALLBACK_PROVIDER', 'none'),
    piper_exe_path=os.getenv('PIPER_EXE_PATH', ''),
    piper_model_path=os.getenv('PIPER_MODEL_PATH', ''),
    )

# Expose a module-level settings object for tests to patch easily (e.g., `patch('app.config.settings')`).
# Note: Most application code should call get_settings() to pick up env changes; tests may mock this object.
settings = get_settings()
