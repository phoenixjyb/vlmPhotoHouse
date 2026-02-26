from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAM++ adapter for local /tag service")
    parser.add_argument("--image", required=True, help="Absolute image path")
    parser.add_argument("--max-tags", type=int, default=8)
    return parser.parse_args()


def _split_tag_text(text: str) -> list[str]:
    out: list[str] = []
    for part in str(text or "").replace(",", "|").split("|"):
        name = part.strip()
        if name:
            out.append(name)
    return out


def _dedupe(tags: list[str], max_tags: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        clean = str(tag or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= max_tags:
            break
    return out


def _parse_inference_output(raw: Any, max_tags: int) -> list[str]:
    if isinstance(raw, dict):
        if isinstance(raw.get("tags"), list):
            return _dedupe([str(x) for x in raw["tags"]], max_tags)
        if isinstance(raw.get("tag"), str):
            return _dedupe(_split_tag_text(raw["tag"]), max_tags)
    if isinstance(raw, str):
        return _dedupe(_split_tag_text(raw), max_tags)
    if isinstance(raw, (list, tuple)):
        if not raw:
            return []
        first = raw[0]
        if isinstance(first, str):
            return _dedupe(_split_tag_text(first), max_tags)
        if isinstance(first, (list, tuple)):
            return _dedupe([str(x) for x in first], max_tags)
        if isinstance(first, dict):
            names = [str(x.get("name") or "") for x in raw if isinstance(x, dict)]
            return _dedupe(names, max_tags)
    return []


def _stub_tags(image_path: Path, max_tags: int) -> list[dict[str, Any]]:
    with Image.open(image_path) as im:
        image = im.convert("RGB")
        width, height = image.size
        orientation = "landscape" if width >= height else "portrait"
        brightness = float(ImageStat.Stat(image.convert("L")).mean[0]) if width and height else 127.0
    light_tag = "night" if brightness < 85 else ("sunny" if brightness > 170 else "indoor")
    tags = [
        {"name": orientation, "score": 0.12},
        {"name": light_tag, "score": 0.10},
        {"name": "photo", "score": 0.05},
    ]
    return tags[: max_tags]


def _build_model(models_mod: Any, checkpoint: str, image_size: int, vit: str):
    variant = str(os.getenv("RAMPP_MODEL_VARIANT", "ram_plus") or "ram_plus").strip().lower()
    ctor = getattr(models_mod, "ram_plus", None) if variant in ("ram_plus", "ram++") else getattr(models_mod, "ram", None)
    if ctor is None:
        ctor = getattr(models_mod, "ram_plus", None) or getattr(models_mod, "ram", None)
    if ctor is None:
        raise RuntimeError("Neither ram_plus nor ram constructor was found in ram.models")

    kwargs_candidates = []
    if checkpoint:
        kwargs_candidates.append({"pretrained": checkpoint, "image_size": image_size, "vit": vit})
        kwargs_candidates.append({"pretrained": checkpoint, "image_size": image_size})
        kwargs_candidates.append({"pretrained": checkpoint})
    kwargs_candidates.append({"image_size": image_size, "vit": vit})
    kwargs_candidates.append({"image_size": image_size})
    kwargs_candidates.append({})

    last_error: Exception | None = None
    for kwargs in kwargs_candidates:
        try:
            return ctor(**kwargs)
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"Failed to initialize RAM++ model: {last_error}")


def _infer_tags(image_path: Path, max_tags: int) -> list[dict[str, Any]]:
    # Optional GPU pinning for P2000 path.
    cuda_device = str(os.getenv("RAMPP_CUDA_DEVICE", "1") or "1").strip()
    if cuda_device:
        os.environ["CUDA_VISIBLE_DEVICES"] = cuda_device

    import importlib
    import torch

    ram_mod = importlib.import_module("ram")
    models_mod = importlib.import_module("ram.models")
    get_transform = getattr(ram_mod, "get_transform", None)
    if get_transform is None:
        raise RuntimeError("ram.get_transform is not available")
    inference_fn = (
        getattr(ram_mod, "inference_ram", None)
        or getattr(ram_mod, "inference_tag2text", None)
        or getattr(ram_mod, "inference", None)
    )
    if inference_fn is None:
        raise RuntimeError("No RAM inference function found (inference_ram/inference_tag2text/inference)")

    image_size = int(os.getenv("RAMPP_IMAGE_SIZE", "384") or 384)
    vit = str(os.getenv("RAMPP_VIT", "swin_l") or "swin_l")
    checkpoint = str(os.getenv("RAMPP_CHECKPOINT", "") or "").strip()
    if checkpoint and not Path(checkpoint).exists():
        raise FileNotFoundError(f"RAMPP_CHECKPOINT does not exist: {checkpoint}")

    model = _build_model(models_mod=models_mod, checkpoint=checkpoint, image_size=image_size, vit=vit)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()

    try:
        transform = get_transform(image_size=image_size)
    except TypeError:
        transform = get_transform(image_size)

    with Image.open(image_path) as im:
        image = im.convert("RGB")
    tensor = transform(image).unsqueeze(0).to(device)

    raw = None
    errors: list[str] = []
    for call in (
        lambda: inference_fn(tensor, model),
        lambda: inference_fn(tensor, model, topk=max_tags),
        lambda: inference_fn(tensor, model, threshold=float(os.getenv("RAMPP_THRESHOLD", "0.68") or 0.68)),
    ):
        try:
            raw = call()
            break
        except Exception as e:
            errors.append(str(e))
            continue
    if raw is None:
        raise RuntimeError(f"RAM++ inference failed: {' | '.join(errors)}")

    names = _parse_inference_output(raw, max_tags=max_tags)
    if not names:
        raise RuntimeError("RAM++ inference returned no parseable tags")

    tags: list[dict[str, Any]] = []
    for idx, name in enumerate(names[:max_tags]):
        score = max(0.01, 0.99 - (idx * 0.05))
        tags.append({"name": name, "score": round(score, 4)})
    return tags


def main() -> None:
    args = _parse_args()
    image_path = Path(args.image).expanduser().resolve()
    max_tags = max(1, min(int(args.max_tags or 8), 32))
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    try:
        tags = _infer_tags(image_path=image_path, max_tags=max_tags)
    except Exception:
        allow_stub = str(os.getenv("RAMPP_ALLOW_STUB_FALLBACK", "false") or "false").lower() in ("1", "true", "yes")
        if not allow_stub:
            raise
        tags = _stub_tags(image_path=image_path, max_tags=max_tags)
    print(json.dumps({"tags": tags}, ensure_ascii=False))


if __name__ == "__main__":
    main()
