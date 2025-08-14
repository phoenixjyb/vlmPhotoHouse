from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from typing import Optional

registry = CollectorRegistry()

# Counters
tasks_processed = Counter('tasks_processed_total', 'Total tasks processed (terminal states done|failed|canceled|dead)', ['type', 'state'], registry=registry)
tasks_retried = Counter('tasks_retried_total', 'Total task retries attempted', ['type'], registry=registry)
embeddings_generated = Counter('embeddings_generated_total', 'Total image embeddings generated', registry=registry)
faces_detected = Counter('faces_detected_total', 'Total faces detected', registry=registry)
face_embeddings_generated = Counter('face_embeddings_generated_total', 'Total face embeddings generated', registry=registry)

# Gauges
tasks_pending_gauge = Gauge('tasks_pending', 'Number of tasks pending', registry=registry)
tasks_running_gauge = Gauge('tasks_running', 'Number of tasks currently running', registry=registry)
tasks_dead_gauge = Gauge('tasks_dead', 'Number of tasks in dead-letter (exhausted retries/permanent failure)', registry=registry)
vector_index_size = Gauge('vector_index_size', 'Vector index size (rows)', registry=registry)
persons_total_gauge = Gauge('persons_total', 'Total persons (clusters) tracked', registry=registry)

# Histograms
task_duration = Histogram('task_duration_seconds', 'Task execution duration seconds', ['type'], buckets=(0.05,0.1,0.25,0.5,1,2,5,10,30,60,120,300,600), registry=registry)

# Face pipeline histograms
# Provider label values should be stable lowercase identifiers (e.g. stub, facenet, insight, lvface, mtcnn)
face_embedding_inference_seconds = Histogram(
    'face_embedding_inference_seconds',
    'Latency (seconds) to compute a single face embedding',
    ['provider'],
    buckets=(0.002,0.005,0.01,0.02,0.05,0.1,0.25,0.5,1,2,5),
    registry=registry
)
face_detection_inference_seconds = Histogram(
    'face_detection_inference_seconds',
    'Latency (seconds) for a detection pass on one image',
    ['provider'],
    buckets=(0.005,0.01,0.02,0.05,0.1,0.25,0.5,1,2,5,10),
    registry=registry
)
face_embedding_model_load_seconds = Histogram(
    'face_embedding_model_load_seconds',
    'Model/provider initialization time (seconds) for face embedding providers',
    ['provider'],
    buckets=(0.05,0.1,0.25,0.5,1,2,5,10,30,60),
    registry=registry
)

def render_prometheus() -> bytes:
    return generate_latest(registry)

def update_queue_gauges(pending: int, running: int):
    tasks_pending_gauge.set(pending)
    tasks_running_gauge.set(running)

def update_dead_tasks(count: int):
    tasks_dead_gauge.set(count)

def update_vector_index_size(size: int):
    vector_index_size.set(size)

def update_persons_total(count: int):
    persons_total_gauge.set(count)
