import os
from pydantic import BaseModel, Field
from functools import lru_cache

class Settings(BaseModel):
    deploy_profile: str = Field(default=os.getenv("DEPLOY_PROFILE", "P1"))  # P1,P2,P3,P4
    run_mode: str = Field(default=os.getenv("RUN_MODE", "api"))  # api|worker|all
    database_url: str = Field(default=os.getenv("DATABASE_URL", "sqlite:///./metadata.sqlite"))
    vector_backend: str = Field(default=os.getenv("VECTOR_BACKEND", "faiss"))  # faiss|qdrant (future)
    originals_path: str = Field(default=os.getenv("ORIGINALS_PATH", "./originals"))
    derived_path: str = Field(default=os.getenv("DERIVED_PATH", "./derived"))
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
    vector_index_path: str = Field(default=os.getenv('VECTOR_INDEX_PATH', 'derived/vector.index'))
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
    worker_concurrency: int = Field(default=int(os.getenv('WORKER_CONCURRENCY','1')))
    max_task_retries: int = Field(default=int(os.getenv('MAX_TASK_RETRIES','3')))
    retry_backoff_base_seconds: float = Field(default=float(os.getenv('RETRY_BACKOFF_BASE_SECONDS','2.0')))
    retry_backoff_cap_seconds: float = Field(default=float(os.getenv('RETRY_BACKOFF_CAP_SECONDS','300')))

@lru_cache
def get_settings() -> Settings:
    return Settings()
