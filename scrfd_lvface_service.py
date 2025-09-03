#!/usr/bin/env python3
"""
Unified SCRFD Face Detection + LVFace Recognition Service
Combines InsightFace SCRFD for accurate face detection with LVFace for embeddings
"""

import os
import sys
import cv2
import numpy as np
import sqlite3
import logging
import traceback
from typing import List, Dict, Tuple, Optional
from flask import Flask, request, jsonify
from pathlib import Path
import base64
from io import BytesIO
from PIL import Image
import time
import onnxruntime as ort

# Add InsightFace to path
INSIGHTFACE_PATH = Path(__file__).parent.parent / "insightface" / "python-package"
sys.path.insert(0, str(INSIGHTFACE_PATH))

try:
    from insightface.app import FaceAnalysis
    from insightface.data import get_image as ins_get_image
except ImportError as e:
    print(f"❌ InsightFace import failed: {e}")
    print("Please install InsightFace: pip install insightface")
    sys.exit(1)

# Add LVFace to path
LVFACE_PATH = Path(__file__).parent.parent / "LVFace"
sys.path.insert(0, str(LVFACE_PATH))

try:
    from inference_onnx import LVFaceInference
except ImportError as e:
    print(f"❌ LVFace import failed: {e}")
    print("Please check LVFace directory")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scrfd_lvface_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SCRFDLVFaceService:
    """Unified SCRFD face detection + LVFace recognition service"""
    
    def __init__(self, 
                 scrfd_model_name: str = 'buffalo_l',
                 lvface_model_path: str = None,
                 providers: List[str] = None):
        """
        Initialize the unified service
        
        Args:
            scrfd_model_name: InsightFace model name for detection
            lvface_model_path: Path to LVFace ONNX model
            providers: ONNX providers (GPU/CPU)
        """
        logger.info("🚀 Initializing SCRFD + LVFace unified service...")
        
        # Set default providers
        if providers is None:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        self.providers = providers
        
        # Initialize SCRFD face detection
        self._init_scrfd(scrfd_model_name)
        
        # Initialize LVFace recognition  
        self._init_lvface(lvface_model_path)
        
        # Performance stats
        self.stats = {
            'total_processed': 0,
            'total_faces_detected': 0,
            'avg_detection_time': 0.0,
            'avg_recognition_time': 0.0
        }
        
        logger.info("✅ Unified service initialized successfully!")
    
    def _init_scrfd(self, model_name: str):
        """Initialize SCRFD face detection"""
        logger.info(f"📦 Initializing SCRFD model: {model_name}")
        
        try:
            self.face_app = FaceAnalysis(name=model_name, providers=self.providers)
            self.face_app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("✅ SCRFD initialized successfully")
            
            # Print available providers
            logger.info(f"SCRFD Providers: {self.face_app.det_model.session.get_providers()}")
            
        except Exception as e:
            logger.error(f"❌ SCRFD initialization failed: {e}")
            raise
    
    def _init_lvface(self, model_path: str = None):
        """Initialize LVFace recognition"""
        logger.info("📦 Initializing LVFace recognition...")
        
        try:
            # Use default LVFace model path if not provided
            if model_path is None:
                model_path = str(LVFACE_PATH / "models" / "LVFace-onnx" / "model.onnx")
            
            if not os.path.exists(model_path):
                # Try alternative path
                alt_path = str(LVFACE_PATH / "LVFace-onnx" / "model.onnx") 
                if os.path.exists(alt_path):
                    model_path = alt_path
                else:
                    raise FileNotFoundError(f"LVFace model not found at {model_path}")
            
            self.lvface = LVFaceInference(model_path, providers=self.providers)
            logger.info(f"✅ LVFace initialized with model: {model_path}")
            
        except Exception as e:
            logger.error(f"❌ LVFace initialization failed: {e}")
            raise
    
    def detect_and_recognize_faces(self, image: np.ndarray) -> List[Dict]:
        """
        Detect faces with SCRFD and get embeddings with LVFace
        
        Args:
            image: Input image as numpy array (BGR format)
            
        Returns:
            List of face detections with embeddings
        """
        start_time = time.time()
        
        try:
            # Convert BGR to RGB for InsightFace
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # SCRFD face detection
            det_start = time.time()
            faces = self.face_app.get(image_rgb)
            det_time = time.time() - det_start
            
            logger.info(f"🔍 SCRFD detected {len(faces)} faces in {det_time:.3f}s")
            
            results = []
            
            for i, face in enumerate(faces):
                # Extract bounding box
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                
                # Extract face confidence from SCRFD
                confidence = float(face.det_score)
                
                # Crop face for LVFace (with some padding)
                padding = 20
                h, w = image.shape[:2]
                x1_crop = max(0, x1 - padding)
                y1_crop = max(0, y1 - padding)
                x2_crop = min(w, x2 + padding)
                y2_crop = min(h, y2 + padding)
                
                face_crop = image[y1_crop:y2_crop, x1_crop:x2_crop]
                
                if face_crop.size == 0:
                    logger.warning(f"Empty face crop for face {i}")
                    continue
                
                # Get LVFace embedding
                rec_start = time.time()
                try:
                    embedding = self.lvface.get_embedding(face_crop)
                    rec_time = time.time() - rec_start
                    
                    if embedding is not None:
                        face_result = {
                            'face_id': i,
                            'bbox': [int(x1), int(y1), int(x2-x1), int(y2-y1)],  # [x, y, w, h]
                            'confidence': confidence,
                            'embedding': embedding.tolist(),
                            'embedding_size': len(embedding),
                            'detection_time': det_time / len(faces),  # Average per face
                            'recognition_time': rec_time
                        }
                        results.append(face_result)
                        
                        logger.info(f"✅ Face {i}: bbox=({x1},{y1},{x2-x1},{y2-y1}), "
                                  f"conf={confidence:.3f}, emb_size={len(embedding)}")
                    else:
                        logger.warning(f"❌ Failed to get embedding for face {i}")
                        
                except Exception as e:
                    logger.error(f"❌ LVFace recognition failed for face {i}: {e}")
                    continue
            
            total_time = time.time() - start_time
            
            # Update stats
            self.stats['total_processed'] += 1
            self.stats['total_faces_detected'] += len(results)
            self.stats['avg_detection_time'] = ((self.stats['avg_detection_time'] * 
                                               (self.stats['total_processed'] - 1) + det_time) / 
                                              self.stats['total_processed'])
            
            logger.info(f"🎉 Processed {len(results)} faces in {total_time:.3f}s total")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Face detection/recognition failed: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def save_to_database(self, image_path: str, faces: List[Dict], db_path: str = "metadata.sqlite"):
        """Save face detection results to database"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get asset ID
            cursor.execute("SELECT id FROM assets WHERE path = ?", (image_path,))
            asset_result = cursor.fetchone()
            
            if not asset_result:
                logger.warning(f"Asset not found in database: {image_path}")
                return False
            
            asset_id = asset_result[0]
            
            # Save each face
            for face in faces:
                # Create embedding file path
                embedding_filename = f"face_{asset_id}_{face['face_id']}_embedding.npy"
                embedding_dir = Path("embeddings")
                embedding_dir.mkdir(exist_ok=True)
                embedding_path = embedding_dir / embedding_filename
                
                # Save embedding to file
                np.save(embedding_path, np.array(face['embedding']))
                
                # Save to database
                cursor.execute("""
                    INSERT OR REPLACE INTO face_detections 
                    (asset_id, bbox_x, bbox_y, bbox_w, bbox_h, confidence, 
                     embedding_path, detection_method, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    asset_id,
                    face['bbox'][0],  # x
                    face['bbox'][1],  # y
                    face['bbox'][2],  # w
                    face['bbox'][3],  # h
                    face['confidence'],
                    str(embedding_path),
                    'SCRFD+LVFace'
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"💾 Saved {len(faces)} faces to database for asset {asset_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database save failed: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """Get service performance statistics"""
        return {
            **self.stats,
            'scrfd_providers': self.face_app.det_model.session.get_providers(),
            'lvface_providers': self.lvface.providers if hasattr(self.lvface, 'providers') else 'Unknown'
        }

# Flask Web Service
app = Flask(__name__)
service = None

@app.route('/status', methods=['GET'])
def status():
    """Service health check"""
    global service
    if service is None:
        return jsonify({'status': 'error', 'message': 'Service not initialized'}), 500
    
    try:
        stats = service.get_stats()
        return jsonify({
            'status': 'healthy',
            'service': 'SCRFD + LVFace Unified Service',
            'stats': stats
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/detect_faces', methods=['POST'])
def detect_faces():
    """Face detection and recognition endpoint"""
    global service
    if service is None:
        return jsonify({'error': 'Service not initialized'}), 500
    
    try:
        # Handle different input formats
        if 'image' in request.files:
            # File upload
            file = request.files['image']
            image_data = file.read()
            image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        elif 'image_base64' in request.json:
            # Base64 encoded image
            image_data = base64.b64decode(request.json['image_base64'])
            image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        elif 'image_path' in request.json:
            # Image file path
            image_path = request.json['image_path']
            if not os.path.exists(image_path):
                return jsonify({'error': f'Image not found: {image_path}'}), 404
            image = cv2.imread(image_path)
        else:
            return jsonify({'error': 'No image provided'}), 400
        
        if image is None:
            return jsonify({'error': 'Failed to decode image'}), 400
        
        # Detect and recognize faces
        faces = service.detect_and_recognize_faces(image)
        
        # Save to database if image_path provided
        if 'image_path' in request.json and 'save_to_db' in request.json and request.json['save_to_db']:
            service.save_to_database(request.json['image_path'], faces)
        
        return jsonify({
            'success': True,
            'num_faces': len(faces),
            'faces': faces,
            'image_shape': image.shape[:2]  # [height, width]
        })
        
    except Exception as e:
        logger.error(f"❌ Face detection request failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/batch_process', methods=['POST'])
def batch_process():
    """Batch process multiple images"""
    global service
    if service is None:
        return jsonify({'error': 'Service not initialized'}), 500
    
    try:
        data = request.json
        image_paths = data.get('image_paths', [])
        save_to_db = data.get('save_to_db', True)
        
        results = []
        total_faces = 0
        
        for image_path in image_paths:
            if not os.path.exists(image_path):
                logger.warning(f"Image not found: {image_path}")
                continue
            
            image = cv2.imread(image_path)
            if image is None:
                logger.warning(f"Failed to load image: {image_path}")
                continue
            
            faces = service.detect_and_recognize_faces(image)
            
            if save_to_db:
                service.save_to_database(image_path, faces)
            
            results.append({
                'image_path': image_path,
                'num_faces': len(faces),
                'faces': faces
            })
            
            total_faces += len(faces)
        
        return jsonify({
            'success': True,
            'processed_images': len(results),
            'total_faces': total_faces,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"❌ Batch processing failed: {e}")
        return jsonify({'error': str(e)}), 500

def main():
    """Initialize and start the service"""
    global service
    
    print("🚀 SCRFD + LVFace Unified Service")
    print("=" * 50)
    
    try:
        # Check GPU availability
        providers = ort.get_available_providers()
        print(f"Available ONNX providers: {providers}")
        
        if 'CUDAExecutionProvider' in providers:
            print("✅ CUDA GPU acceleration available")
            gpu_providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        else:
            print("⚠️  Using CPU only")
            gpu_providers = ['CPUExecutionProvider']
        
        # Initialize service
        service = SCRFDLVFaceService(
            scrfd_model_name='buffalo_l',  # High accuracy model
            providers=gpu_providers
        )
        
        print("\n🌐 Starting Flask service on port 8004...")
        app.run(host='0.0.0.0', port=8004, debug=False, threaded=True)
        
    except Exception as e:
        logger.error(f"❌ Service startup failed: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()
