"""Monitor LVFace service GPU usage while issuing embedding requests."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

import requests
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_LOG_DIR = REPO_ROOT / "logs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8003, help="Port to run LVFace service on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the service")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds for nvidia-smi")
    parser.add_argument("--requests", type=int, default=5, help="Number of embed requests to issue")
    parser.add_argument("--request-delay", type=float, default=0.5, help="Delay between embed requests (seconds)")
    parser.add_argument("--cooldown", type=float, default=3.0, help="Sleep after workload before shutdown")
    parser.add_argument("--image", type=Path, help="Optional image file to post to /embed; default is generated solid image")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help="Directory to write GPU usage CSV")
    parser.add_argument("--service-log", action="store_true", help="Stream uvicorn stdout/stderr to console")
    return parser.parse_args()


def ensure_python_exe() -> Path:
    if not PYTHON_EXE.exists():
        raise FileNotFoundError(f"Python interpreter not found at {PYTHON_EXE}")
    return PYTHON_EXE


def start_service(host: str, port: int, stream_output: bool) -> subprocess.Popen:
    python_exe = ensure_python_exe()
    env = os.environ.copy()
    env.setdefault("LVFACE_MODEL_PATH", str(BACKEND_DIR / "models" / "lvface.onnx"))
    env.setdefault("FACE_EMBED_DIM", "512")
    env.setdefault("EMBED_DEVICE", "cuda")
    env.setdefault("PYTORCH_CUDA_DEVICE", "0")
    stdout = None if stream_output else subprocess.DEVNULL
    stderr = None if stream_output else subprocess.STDOUT
    cmd = [
        str(python_exe),
        "-m", "uvicorn",
        "app.lvface_http_service:app",
        "--host", host,
        "--port", str(port),
    ]
    proc = subprocess.Popen(cmd, cwd=str(BACKEND_DIR), env=env, stdout=stdout, stderr=stderr)
    return proc


def wait_for_health(url: str, timeout: float = 120.0) -> dict:
    start = time.time()
    last_exc: Optional[Exception] = None
    while time.time() - start < timeout:
        try:
            resp = requests.get(url, timeout=2.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        time.sleep(1.0)
    raise TimeoutError(f"Service did not become healthy within {timeout}s") from last_exc


def run_embed_requests(url: str, count: int, delay: float, image: Optional[Path]) -> None:
    if image and not image.exists():
        raise FileNotFoundError(f"Image not found: {image}")
    temp_image: Optional[Path] = None
    try:
        img_path = image
        if img_path is None:
            temp_image = Path(tempfile_image())
            img_path = temp_image
        with img_path.open("rb") as fh:
            payload = fh.read()
        for idx in range(1, count + 1):
            files = {"file": (img_path.name, payload, "image/png")}
            resp = requests.post(f"{url}/embed", files=files, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            dim = len(data.get("embedding", []))
            print(f"[{idx}/{count}] embedding dim={dim} device={data.get('device')}")
            time.sleep(delay)
    finally:
        if temp_image and temp_image.exists():
            temp_image.unlink(missing_ok=True)


def tempfile_image() -> str:
    from PIL import Image
    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.close()
    Image.new("RGB", (256, 256), color=(64, 96, 160)).save(tmp.name)
    return tmp.name


def collect_gpu_samples(stop_event: threading.Event, interval: float, buffer: List[dict]) -> None:
    query = ["index", "name", "memory.used", "memory.total"]
    cmd = ["nvidia-smi", "--query-gpu=" + ",".join(query), "--format=csv,noheader,nounits"]
    while not stop_event.is_set():
        sample_time = dt.datetime.utcnow()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            for line in lines:
                parts = [part.strip() for part in line.split(",")]
                if len(parts) != 4:
                    continue
                gpu_index, name, used, total = parts
                buffer.append({
                    "timestamp": sample_time.isoformat() + "Z",
                    "gpu_index": gpu_index,
                    "gpu_name": name,
                    "memory_used_mb": int(float(used)),
                    "memory_total_mb": int(float(total)),
                })
        except FileNotFoundError:
            print("nvidia-smi not found on PATH; stopping GPU sampling.")
            break
        except subprocess.CalledProcessError as exc:
            print(f"nvidia-smi command failed: {exc.stderr}")
        time.sleep(interval)


def write_csv(log_dir: Path, samples: List[dict]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = log_dir / f"lvface_gpu_usage_{timestamp}.csv"
    fieldnames = ["timestamp", "gpu_index", "gpu_name", "memory_used_mb", "memory_total_mb"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in samples:
            writer.writerow(row)
    return path


def summarize(samples: List[dict]) -> None:
    if not samples:
        print("No GPU samples collected.")
        return
    by_gpu = {}
    for row in samples:
        key = (row["gpu_index"], row["gpu_name"])
        by_gpu.setdefault(key, []).append(row)
    print("\nPeak memory usage (MiB):")
    for (gpu_index, name), rows in by_gpu.items():
        peak = max(r["memory_used_mb"] for r in rows)
        total = rows[0]["memory_total_mb"]
        print(f"  GPU {gpu_index} ({name}): {peak} / {total}")


def main() -> int:
    args = parse_args()
    service_url = f"http://{args.host}:{args.port}"
    proc = start_service(args.host, args.port, args.service_log)
    samples: List[dict] = []
    stop_event = threading.Event()
    sampler = threading.Thread(target=collect_gpu_samples, args=(stop_event, args.interval, samples), daemon=True)
    sampler.start()
    try:
        health = wait_for_health(f"{service_url}/health")
        print("LVFace service health:", health)
        run_embed_requests(service_url, args.requests, args.request_delay, args.image)
        if args.cooldown > 0:
            print(f"Cooldown for {args.cooldown}s ...")
            time.sleep(args.cooldown)
    finally:
        stop_event.set()
        sampler.join(timeout=args.interval * 2)
        print("Stopping LVFace service ...")
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    if samples:
        log_path = write_csv(args.log_dir, samples)
        print(f"GPU usage log written to {log_path}")
        summarize(samples)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(1)
