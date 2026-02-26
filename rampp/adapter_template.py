from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Template adapter for RAM++ tag inference")
    p.add_argument("--image", required=True, help="Absolute image path")
    p.add_argument("--max-tags", type=int, default=8)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    # TODO: Replace this template with real RAM++ inference logic.
    # Output MUST be JSON to stdout and include `tags` as list of {name, score}.
    payload = {
        "tags": [
            {"name": "photo", "score": 0.05},
        ][: max(1, int(args.max_tags or 8))],
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
