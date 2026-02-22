#!/usr/bin/env python3
"""
Inspect local database files and print table-level record counts.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


DEFAULT_CONFIG = Path("config/drive_e_paths.json")
DEFAULT_DATABASES = {
    "app.db (main application database)": "E:/VLM_DATA/databases/app.db",
    "metadata.sqlite (metadata store)": "E:/VLM_DATA/databases/metadata.sqlite",
    "drive_e_processing.db (processing state)": "E:/VLM_DATA/databases/drive_e_processing.db",
}
KEY_TABLES = {"assets", "face_detections", "embeddings", "metadata"}


def load_databases_from_config(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        return DEFAULT_DATABASES

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    dbs = data.get("databases", {})
    mapped = {}
    if dbs.get("app"):
        mapped["app.db (main application database)"] = dbs["app"]
    if dbs.get("metadata"):
        mapped["metadata.sqlite (metadata store)"] = dbs["metadata"]
    if dbs.get("drive_e_processing"):
        mapped["drive_e_processing.db (processing state)"] = dbs["drive_e_processing"]
    return mapped or DEFAULT_DATABASES


def analyze_database(name: str, path: str) -> None:
    db_path = Path(path)
    print(f"\n{name}")
    print("=" * 60)
    print(f"path: {db_path}")

    if not db_path.exists():
        print("status: missing")
        return

    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"size_mb: {size_mb:.2f}")

    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"tables: {len(tables)}")

            for table_name in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"  - {table_name}: {count:,}")

                if table_name in KEY_TABLES:
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = [col[1] for col in cursor.fetchall()]
                    preview = ", ".join(columns[:6])
                    suffix = "..." if len(columns) > 6 else ""
                    print(f"    columns: {preview}{suffix}")
    except Exception as exc:
        print(f"error: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze configured database files")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to drive_e_paths.json (default: config/drive_e_paths.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    databases = load_databases_from_config(args.config)

    print("DATABASE ANALYSIS")
    print("=" * 60)
    print(f"config: {args.config} {'(found)' if args.config.exists() else '(missing, using defaults)'}")

    for name, path in databases.items():
        analyze_database(name, path)


if __name__ == "__main__":
    main()
