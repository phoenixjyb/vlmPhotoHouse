#!/usr/bin/env python3
"""
System Integration Overview and Usage Guide
Shows how all components work together
"""

print("""
🏗️  VLM PHOTO ENGINE - SYSTEM ARCHITECTURE
══════════════════════════════════════════════════════════════════

📋 COMPONENT OVERVIEW:
──────────────────────────────────────────────────────────────────

1️⃣  start_multi_proc.ps1
    ├── Panel 1: Caption Service (vlmCaptionModels)
    ├── Panel 2: unified_scrfd_service.py (WSL - Face Detection)  
    ├── Panel 3: enhanced_face_orchestrator_unified.py (Batch Processor)
    └── Panel 4: AI Orchestrator

2️⃣  enhanced_face_orchestrator_unified.py
    • Purpose: Batch process images for face detection
    • Input: All images in database
    • Output: Updates database with face detection results
    • Speed: ~110 images/second
    • Does NOT create face collection files

3️⃣  complete_face_processor.py
    • Purpose: Create face collection and gallery
    • Input: Database face detection results
    • Output: Face thumbnails + HTML gallery + metadata
    • Two modes: Incremental (default) or Fresh start

4️⃣  unified_scrfd_service.py (WSL)
    • Purpose: SCRFD face detection + LVFace embeddings
    • Port: 8003 (accessible via 172.22.61.27:8003)
    • GPU: CUDA acceleration
    • Proxy bypass: Required for Clash compatibility

🔄 WORKFLOW PATTERNS:
──────────────────────────────────────────────────────────────────

📝 PATTERN 1: Complete Fresh Start
──────────────────────────────────────────────────────────────────
1. python complete_face_processor.py --fresh
   └── Clears database + processes all 6,569 images + creates collection

📝 PATTERN 2: Incremental Processing (Recommended)
──────────────────────────────────────────────────────────────────
1. python enhanced_face_orchestrator_unified.py
   └── Process new/unprocessed images → updates database
   
2. python complete_face_processor.py  
   └── Create face collection from database results

📝 PATTERN 3: Multi-Service Environment
──────────────────────────────────────────────────────────────────
1. .\start_multi_proc.ps1
   └── Start all services in separate panels
   
2. Use Panel 3 for batch processing
3. Run complete_face_processor.py separately for face collection

💾 DATA FLOW:
──────────────────────────────────────────────────────────────────

Images → enhanced_face_orchestrator → Database → complete_face_processor → Face Collection
  ↓              ↓                       ↓                ↓                    ↓
6,569          SCRFD API            face_detections    Thumbnails +       HTML Gallery
images         calls                   table           Metadata           + Statistics

📊 OUTPUT STRUCTURE:
──────────────────────────────────────────────────────────────────

E:/02_PROCESSED/detected_faces/
├── thumbnails/                 # 128x128 compressed face images
│   ├── face_123_0_715.jpg     # Format: face_{image_id}_{detection_id}_{confidence}
│   └── face_456_1_892.jpg
├── metadata/                   # JSON metadata for each face
│   ├── face_123_0_715.json    # Links back to original image
│   └── face_456_1_892.json
└── face_gallery.html          # Interactive web gallery

⚙️  CONFIGURATION:
──────────────────────────────────────────────────────────────────

• WSL IP: 172.22.61.27:8003 (for Clash proxy bypass)
• Face size: 128x128 pixels (highly compressed)
• JPEG quality: 70% (balance of quality/size)
• Database: metadata.sqlite (face_detections table)
• Processing speed: ~110 images/second

🚀 RECOMMENDED USAGE:
──────────────────────────────────────────────────────────────────

For daily use:
1. python enhanced_face_orchestrator_unified.py    # Process new images
2. python complete_face_processor.py               # Update face collection

For fresh start:
1. python complete_face_processor.py --fresh       # Everything from scratch

For development:
1. .\start_multi_proc.ps1                          # Multi-panel environment

🎯 BENEFITS:
──────────────────────────────────────────────────────────────────

✅ Incremental processing (no reprocessing of already-done images)
✅ Proxy bypass for Clash compatibility  
✅ GPU-accelerated SCRFD detection
✅ Space-efficient face thumbnails (~2-5KB each)
✅ Interactive HTML gallery for browsing
✅ Metadata linking faces back to original images
✅ High-speed batch processing (~110 img/s)

══════════════════════════════════════════════════════════════════
""")

print("💡 NEXT STEPS:")
print("1. For incremental face collection: python complete_face_processor.py")
print("2. For fresh start: python complete_face_processor.py --fresh")
print("3. For batch processing: python enhanced_face_orchestrator_unified.py")
print("4. For multi-service: .\\start_multi_proc.ps1")
print()
