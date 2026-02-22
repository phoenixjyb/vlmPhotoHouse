"""Launch the full multiprocess stack and log GPU usage per service."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import requests
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = REPO_ROOT / "start-multi-proc.ps1"
LOG_DIR = REPO_ROOT / "logs"

API_PORT = 8001
CAPTION_PORT = 8002
LVFACE_PORT = 8003

SERVICE_PATTERNS = {
    "app.lvface_http_service": "LVFace HTTP service",
    "caption_server.py": "Caption service (BLIP2)",
    "uvicorn app.main:app": "Main API",
    "tts_server:app": "TTS service",
    "llmytranslate": "Voice/ASR service",
}

TARGET_KILL_PATTERNS = [
    "uvicorn app.main:app",
    "caption_server.py",
    "app.lvface_http_service",
    "tts_server:app",
    "voice_proxy",
    "llmytranslate",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=90.0, help="Sampling duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="nvidia-smi sampling interval in seconds")
    parser.add_argument("--requests", type=int, default=3, help="Number of caption/LVFace request rounds")
    parser.add_argument("--request-delay", type=float, default=3.0, help="Delay between request rounds in seconds")
    parser.add_argument("--health-timeout", type=float, default=180.0, help="Seconds to wait for services to become healthy")
    parser.add_argument("--keep-processes", action="store_true", help="Leave services running after profiling")
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR, help="Directory to store GPU usage CSV")
    parser.add_argument("--image", type=Path, help="Optional image for caption/LVFace requests")
    parser.add_argument("--verbose", action="store_true", help="Print additional debug information")
    return parser.parse_args()


def run_start_script(verbose: bool) -> subprocess.Popen:
    if not START_SCRIPT.exists():
        raise FileNotFoundError(f"Cannot find {START_SCRIPT}")
    cmd = [
        "pwsh",
        "-NoLogo",
        "-NoProfile",
        "-File",
        str(START_SCRIPT),
        "-UseWindowsTerminal:$false",
        "-WithInteractiveShell:$false",
        "-KillExisting",
    ]
    if verbose:
        print("Launching start-multi-proc:", " ".join(cmd))
    return subprocess.Popen(cmd, cwd=REPO_ROOT)


def wait_for_services(timeout: float) -> None:
    endpoints = {
        "API": f"http://127.0.0.1:{API_PORT}/health",
        "Caption": f"http://127.0.0.1:{CAPTION_PORT}/health",
        "LVFace": f"http://127.0.0.1:{LVFACE_PORT}/health",
    }
    pending = set(endpoints)
    start = time.time()
    while pending and time.time() - start < timeout:
        finished = []
        for name in list(pending):
            url = endpoints[name]
            try:
                resp = requests.get(url, timeout=3.0)
                if resp.status_code == 200:
                    finished.append(name)
            except Exception:
                pass
        for name in finished:
            pending.remove(name)
        if pending:
            time.sleep(1.0)
    if pending:
        raise TimeoutError(f"Services not healthy within timeout: {', '.join(sorted(pending))}")


def ensure_image(image: Optional[Path]) -> Path:
    if image:
        if not image.exists():
            raise FileNotFoundError(f"Image not found: {image}")
        return image
    tmp = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".png").name)
    tmp.unlink(missing_ok=True)
    Image.new("RGB", (512, 512), color=(70, 110, 190)).save(tmp, "PNG")
    return tmp


def trigger_requests(image: Path, rounds: int, delay: float) -> None:
    payload = image.read_bytes()
    files = {"file": (image.name, payload, "image/png")}
    for idx in range(1, rounds + 1):
        try:
            caption_resp = requests.post(f"http://127.0.0.1:{CAPTION_PORT}/caption", files=files, timeout=180)
            caption_resp.raise_for_status()
            caption = caption_resp.json().get("caption", "")
            print(f"[Round {idx}] Caption length={len(caption)}")
        except Exception as exc:
            print(f"[Round {idx}] Caption request failed: {exc}")
        try:
            lv_resp = requests.post(f"http://127.0.0.1:{LVFACE_PORT}/embed", files=files, timeout=120)
            lv_resp.raise_for_status()
            emb_dim = len(lv_resp.json().get("embedding", []))
            print(f"[Round {idx}] LVFace embedding dim={emb_dim}")
        except Exception as exc:
            print(f"[Round {idx}] LVFace request failed: {exc}")
        time.sleep(delay)


def get_command_line(pid: int) -> str:
    cmd = [
        "pwsh",
        "-NoLogo",
        "-NoProfile",
        "-Command",
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\"; if ($p) {{ $p.CommandLine }}"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


_command_cache: Dict[int, str] = {}


def sample_gpu(interval: float, duration: float, verbose: bool) -> List[dict]:
    query_cmd = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ]
    samples: List[dict] = []
    start = time.time()
    while time.time() - start <= duration:
        timestamp = dt.datetime.utcnow().isoformat() + "Z"
        try:
            result = subprocess.run(query_cmd, capture_output=True, text=True, check=True)
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if not lines and verbose:
                print(f"{timestamp}: GPU idle")
            for line in lines:
                parts = [part.strip() for part in line.split(",")]
                if len(parts) != 3:
                    continue
                try:
                    pid = int(parts[0])
                    used_mb = int(float(parts[2]))
                except ValueError:
                    continue
                if pid not in _command_cache:
                    _command_cache[pid] = get_command_line(pid)
                samples.append({
                    "timestamp": timestamp,
                    "pid": pid,
                    "process_name": parts[1],
                    "used_memory_mb": used_mb,
                    "command_line": _command_cache.get(pid, ""),
                })
        except FileNotFoundError:
            print("nvidia-smi not found; aborting sampling.")
            break
        except subprocess.CalledProcessError as exc:
            if verbose:
                print("nvidia-smi error:", exc.stderr.strip())
        time.sleep(interval)
    return samples


def write_csv(log_dir: Path, samples: List[dict]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"main_launcher_gpu_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = ["timestamp", "pid", "process_name", "used_memory_mb", "command_line"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in samples:
            writer.writerow(row)
    return path


def identify_service(command_line: str) -> str:
    if not command_line:
        return "Unknown"
    for pattern, label in SERVICE_PATTERNS.items():
        if pattern in command_line:
            return label
    return "Other"


def summarize(samples: List[dict]) -> None:
    if not samples:
        print("No GPU samples captured.")
        return
    grouped: Dict[str, int] = defaultdict(int)
    for row in samples:
        label = identify_service(row["command_line"] or row["process_name"])
        key = f"{label} (PID {row['pid']})"
        grouped[key] = max(grouped[key], row["used_memory_mb"])
    print("\nPeak GPU memory per service (MiB):")
    for key, peak in grouped.items():
        print(f"  {key}: {peak} MiB")


def cleanup_processes(samples: List[dict], verbose: bool) -> None:
    pids = {row["pid"] for row in samples}
    for pid in pids:
        cmdline = _command_cache.get(pid, "")
        if not cmdline:
            continue
        if any(pattern in cmdline for pattern in TARGET_KILL_PATTERNS):
            if verbose:
                print(f"Stopping PID {pid}: {cmdline}")
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)


def main() -> int:
    args = parse_args()
    launcher = run_start_script(args.verbose)
    launcher.wait(timeout=args.health_timeout)
    print("Launcher invoked; waiting for services to report healthy ...")
    wait_for_services(args.health_timeout)
    image_path = ensure_image(args.image)
    try:
        trigger_requests(image_path, args.requests, args.request_delay)
    finally:
        if args.image is None and image_path.exists():
            image_path.unlink(missing_ok=True)
    print(f"Sampling GPU usage for {args.duration} seconds ...")
    samples = sample_gpu(args.interval, args.duration, args.verbose)
    log_path = write_csv(args.log_dir, samples)
    print(f"GPU usage CSV written to {log_path}")
    summarize(samples)
    if not args.keep_processes:
        cleanup_processes(samples, args.verbose)
    else:
        print("Services kept alive (keep-processes specified).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(1)
