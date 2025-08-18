#!/usr/bin/env python3
"""Test script to debug startup issues."""

import sys
import os

# Add the backend app to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing basic imports...")
    
    from app.config import get_settings
    print("✓ Config imported successfully")
    
    settings = get_settings()
    print(f"✓ Settings loaded: deploy_profile={settings.deploy_profile}")
    
    from app.dependencies import get_db, SessionLocal
    print("✓ Dependencies imported successfully")
    
    # Test database connection
    from app.db import Base, Asset
    print("✓ Database models imported successfully")
    
    # Test database engine creation
    from sqlalchemy import create_engine
    engine = create_engine(settings.database_url, future=True, echo=False)
    print(f"✓ Database engine created: {settings.database_url}")
    
    # Test basic connection
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✓ Database connection test passed")
    
    print("Basic imports successful! Testing FastAPI app creation...")
    
    from app.main import app
    print("✓ FastAPI app imported successfully")
    
    print("\nAll basic components loaded successfully!")
    print("Issue might be in the startup event handlers or uvicorn configuration.")
    
except Exception as e:
    print(f"✗ Error during startup: {e}")
    import traceback
    traceback.print_exc()
