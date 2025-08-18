#!/usr/bin/env python3
"""Simple test server to check basic FastAPI functionality."""

import sys
import os

# Add the backend app to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from app.dependencies import get_db, SessionLocal
from app.db import Asset
from sqlalchemy import func
import uvicorn

# Create simple test app
test_app = FastAPI()

@test_app.get("/health")
def health():
    return {"status": "ok", "message": "Simple test server working"}

@test_app.get("/db-test")
def db_test():
    try:
        with SessionLocal() as session:
            count = session.query(func.count(Asset.id)).scalar()
            return {"db_status": "ok", "asset_count": count}
    except Exception as e:
        return {"db_status": "error", "error": str(e)}

if __name__ == "__main__":
    print("Starting simple test server on port 8002...")
    uvicorn.run(test_app, host="127.0.0.1", port=8002, log_level="info")
