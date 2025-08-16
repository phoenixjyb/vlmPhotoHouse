from pydantic import BaseModel
from typing import List, Optional, Dict, Any

API_VERSION = "1.0"

class APIBase(BaseModel):
    api_version: str = API_VERSION

class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int

class AssetBrief(BaseModel):
    id: int
    path: str

class AssetDetail(BaseModel):
    id: int
    path: str
    hash_sha256: str
    perceptual_hash: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    taken_at: Optional[str] = None
    status: Optional[str] = None

class AssetUploadResponse(APIBase):
    asset: AssetDetail
    tasks_enqueued: int

class AssetsListResponse(APIBase):
    page: int
    page_size: int
    total: int
    assets: List[AssetDetail]

class SearchResponse(APIBase):
    page: int
    page_size: int
    total: int
    items: List[AssetBrief]

class PersonOut(BaseModel):
    id: int
    display_name: Optional[str]
    face_count: int
    sample_faces: Optional[List[int]] = None

class PersonsResponse(APIBase):
    page: int
    page_size: int
    total: int
    persons: List[PersonOut]

class FaceOut(BaseModel):
    id: int
    asset_id: int
    person_id: Optional[int]

class FacesResponse(APIBase):
    page: int
    page_size: int
    total: int
    faces: List[FaceOut]

class TaskOut(BaseModel):
    id: int
    type: str
    state: str
    priority: int
    retry_count: int
    last_error: Optional[str] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    cancel_requested: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

class TasksResponse(APIBase):
    page: int
    page_size: int
    total: int
    tasks: List[TaskOut]

class TaskDetailResponse(APIBase):
    task: TaskOut | None

class TaskCancelResponse(APIBase):
    task_id: int
    state: str

class DuplicateGroup(BaseModel):
    hash: str | None = None
    phash: str | None = None
    count: int
    assets: List[AssetBrief]

class DuplicateGroupsPage(BaseModel):
    page: int
    page_size: int
    total_groups: int
    groups: List[DuplicateGroup]

class DuplicatesResponse(APIBase):
    sha256: Optional[DuplicateGroupsPage] = None
    phash: Optional[DuplicateGroupsPage] = None

class NearDuplicateMember(BaseModel):
    id: int
    path: str
    phash: str
    distance: int

class NearDuplicateCluster(BaseModel):
    representative: int
    size: int
    members: List[NearDuplicateMember]

class NearDuplicatesResponse(APIBase):
    page: int
    page_size: int
    total_clusters: int
    clusters: List[NearDuplicateCluster]
    max_distance: int
    scanned: int
    truncated: bool

class VectorSearchResult(BaseModel):
    asset_id: int
    score: float
    path: str | None

class VectorSearchResponse(APIBase):
    query: Dict[str, Any]
    k: int
    results: List[VectorSearchResult]

class ReclusterTriggerResponse(APIBase):
    task_id: int

class ReclusterStatusTask(BaseModel):
    id: int
    state: str
    retry_count: int
    created_at: Optional[str]
    updated_at: Optional[str] = None
    summary: Optional[dict[str, int]] = None

class ReclusterStatusResponse(APIBase):
    running: bool
    task: Optional[ReclusterStatusTask]

class HealthIndexStatus(BaseModel):
    initialized: bool
    size: int
    dim: Optional[int] = None

class HealthResponse(APIBase):
    ok: bool
    db_ok: bool
    pending_tasks: int
    running_tasks: int
    failed_tasks: int
    index: HealthIndexStatus
    profile: str
    worker_enabled: bool
    face: Optional[dict] = None
    caption: Optional[dict] = None

class MetricsTasks(BaseModel):
    total: int
    by_state: Dict[str, int]

class MetricsVectorIndex(BaseModel):
    size: int
    dim: Optional[int] = None

class MetricsResponse(APIBase):
    assets: Dict[str, int]
    embeddings: int
    captions: int
    faces: int
    persons: int
    tasks: MetricsTasks
    vector_index: MetricsVectorIndex
    last_recluster: Optional[Dict[str, int]] = None
    task_duration_seconds_avg: Optional[float] = None

class EmbeddingBackendStatus(APIBase):
    image_model: str
    text_model: str
    device: str
    dim: int
    model_version: Optional[str] = None
    reembed_scheduled: int
    total_assets: int

# --- Albums ---
class TimeAlbumDay(BaseModel):
    day: int
    count: int
    sample_asset_ids: List[int]

class TimeAlbumMonth(BaseModel):
    month: int
    count: int
    days: List[TimeAlbumDay]
    sample_asset_ids: List[int]

class TimeAlbumYear(BaseModel):
    year: int
    count: int
    months: List[TimeAlbumMonth]
    sample_asset_ids: List[int]

class TimeAlbumsResponse(APIBase):
    years: List[TimeAlbumYear]
