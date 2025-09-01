#!/usr/bin/env python3
"""
Debug script to manually test task processing
"""
import sys
import os
sys.path.insert(0, 'backend')

from backend.app.config import get_settings
from backend.app import dependencies as deps
from backend.app import tasks as tasks_mod
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('debug_tasks')

def main():
    logger.info("=== TASK PROCESSING DEBUG ===")
    
    # Initialize dependencies
    deps.ensure_db()
    settings = get_settings()
    
    logger.info(f"Settings: embed_device={settings.embed_device}, caption_device={settings.caption_device}")
    logger.info(f"Face provider: {settings.face_embed_provider}, Caption provider: {settings.caption_provider}")
    
    # Create executor
    executor = tasks_mod.TaskExecutor(deps.SessionLocal, settings)
    
    logger.info("Testing single task execution...")
    
    try:
        # Try to run one task
        worked = executor.run_once()
        logger.info(f"Task execution result: worked={worked}")
        
        if worked:
            logger.info("✅ Task processed successfully!")
        else:
            logger.info("ℹ️ No tasks available to process")
            
    except Exception as e:
        logger.error(f"❌ Task execution failed: {e}", exc_info=True)
        
    logger.info("=== DEBUG COMPLETE ===")

if __name__ == "__main__":
    main()
