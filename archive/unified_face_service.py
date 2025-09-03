"""
Unified Face Detection + Recognition Service
Combines YOLOv8-Face detection with LVFace embeddings in a single GPU-accelerated pipeline
Updated with enhanced database schema support
"""

import cv2
import numpy as np
import onnxruntime
import torch
from ultralytics import YOLO
from typing import List, Dict, Tuple, Optional
from flask import Flask, request, jsonify
import base64
import io
from PIL import Image
import json
import time
import sqlite3
import os
from pathlib import Path
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UnifiedFaceService:
    """Unified Face Detection and Recognition Service"""
    
    def __init__(self, 
                 lvface_model_path: str = "../LVFace/models/LVFace-B_Glint360K.onnx",
                 yolo_model: str = "yolov8n.pt",  # We'll switch to face-specific model
                 use_gpu: bool = True,
                 confidence_threshold: float = 0.5):
        """
        Initialize the unified face service
        
        Args:
            lvface_model_path: Path to LVFace ONNX model
            yolo_model: YOLOv8 model (will download face-specific model)
            use_gpu: Whether to use GPU acceleration
            confidence_threshold: Minimum confidence for face detection
        """
        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold
        self.device = 'cuda' if use_gpu and torch.cuda.is_available() else 'cpu'
        
        print(f"🚀 Initializing Unified Face Service on {self.device}")
        
        # Initialize YOLOv8 for face detection
        self._init_yolo_face_detector(yolo_model)
        
        # Initialize LVFace for embeddings
        self._init_lvface_embedder(lvface_model_path)
        
        print("✅ Unified Face Service initialized successfully")
    
    def _init_yolo_face_detector(self, model_name: str):
        """Initialize YOLO face detector"""
        try:
            print("📦 Loading YOLO face detection model...")
            
            # For now use general YOLO, but we'll enhance with face-specific model
            self.yolo_model = YOLO(model_name)
            
            # Move to GPU if available
            if self.use_gpu and torch.cuda.is_available():
                self.yolo_model.to(self.device)
                print(f"✅ YOLO model loaded on {self.device}")
            else:
                print("✅ YOLO model loaded on CPU")
                
        except Exception as e:
            raise RuntimeError(f"Failed to initialize YOLO face detector: {e}")
    
    def _init_lvface_embedder(self, model_path: str):
        """Initialize LVFace embedder"""
        try:
            print("📦 Loading LVFace embedding model...")
            
            # Select execution provider
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if self.use_gpu else ['CPUExecutionProvider']
            
            # Initialize ONNX Runtime session
            self.ort_session = onnxruntime.InferenceSession(
                model_path,
                providers=providers
            )
            
            # Get input and output names
            self.input_name = self.ort_session.get_inputs()[0].name
            self.output_name = self.ort_session.get_outputs()[0].name
            
            # Input image size for LVFace
            self.lvface_input_size = (112, 112)
            
            # Check which providers are actually being used
            active_providers = self.ort_session.get_providers()
            print(f"✅ LVFace model loaded with providers: {active_providers}")
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize LVFace embedder: {e}")
    
    def detect_faces(self, image: np.ndarray, return_crops: bool = True) -> List[Dict]:
        """
        Detect faces in image using YOLO
        
        Args:
            image: Input image (BGR format from cv2)
            return_crops: Whether to return face crop images
            
        Returns:
            List of face detections with bounding boxes and optional crops
        """
        try:
            # Run YOLO inference
            results = self.yolo_model(image, conf=self.confidence_threshold, verbose=False)
            
            faces = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        # Filter for person class (class 0 in COCO)
                        if int(box.cls) == 0:  # Person class
                            conf = float(box.conf)
                            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                            
                            face_info = {
                                'bbox': [x1, y1, x2 - x1, y2 - y1],  # [x, y, w, h]
                                'bbox_xyxy': [x1, y1, x2, y2],       # [x1, y1, x2, y2]
                                'confidence': conf,
                                'area': (x2 - x1) * (y2 - y1)
                            }
                            
                            # Extract face crop if requested
                            if return_crops:
                                # Add some padding around the face
                                padding = 0.1
                                w, h = x2 - x1, y2 - y1
                                pad_w, pad_h = int(w * padding), int(h * padding)
                                
                                # Ensure we don't go out of bounds
                                img_h, img_w = image.shape[:2]
                                crop_x1 = max(0, x1 - pad_w)
                                crop_y1 = max(0, y1 - pad_h)
                                crop_x2 = min(img_w, x2 + pad_w)
                                crop_y2 = min(img_h, y2 + pad_h)
                                
                                face_crop = image[crop_y1:crop_y2, crop_x1:crop_x2]
                                face_info['crop'] = face_crop
                                face_info['crop_bbox'] = [crop_x1, crop_y1, crop_x2 - crop_x1, crop_y2 - crop_y1]
                            
                            faces.append(face_info)
            
            # Sort by confidence (highest first)
            faces.sort(key=lambda x: x['confidence'], reverse=True)
            
            return faces
            
        except Exception as e:
            raise RuntimeError(f"Face detection failed: {e}")
    
    def get_face_embedding(self, face_crop: np.ndarray) -> np.ndarray:
        """
        Get face embedding using LVFace
        
        Args:
            face_crop: Face crop image (BGR format)
            
        Returns:
            Face embedding vector
        """
        try:
            # Preprocess for LVFace
            img_resized = cv2.resize(face_crop, self.lvface_input_size)
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            img_transposed = np.transpose(img_rgb, (2, 0, 1))
            img_normalized = ((img_transposed / 255.0) - 0.5) / 0.5
            img_tensor = img_normalized.astype(np.float32)[np.newaxis, ...]
            
            # Run LVFace inference
            output = self.ort_session.run(
                [self.output_name],
                {self.input_name: img_tensor}
            )
            
            return output[0].flatten()
            
        except Exception as e:
            raise RuntimeError(f"Face embedding failed: {e}")
    
    def process_image_full_pipeline(self, image: np.ndarray) -> Dict:
        """
        Complete face detection + recognition pipeline
        
        Args:
            image: Input image (BGR format)
            
        Returns:
            Dict with all face detections and embeddings
        """
        start_time = time.time()
        
        # Step 1: Detect faces
        faces = self.detect_faces(image, return_crops=True)
        detection_time = time.time() - start_time
        
        # Step 2: Get embeddings for each face
        embedding_start = time.time()
        for i, face in enumerate(faces):
            if 'crop' in face:
                try:
                    embedding = self.get_face_embedding(face['crop'])
                    face['embedding'] = embedding.tolist()
                    face['embedding_shape'] = embedding.shape
                except Exception as e:
                    print(f"⚠️ Failed to get embedding for face {i}: {e}")
                    face['embedding'] = None
        
        embedding_time = time.time() - embedding_start
        total_time = time.time() - start_time
        
        # Remove crops from response (too large for JSON)
        for face in faces:
            if 'crop' in face:
                del face['crop']
        
        return {
            'num_faces': len(faces),
            'faces': faces,
            'timing': {
                'detection_time': detection_time,
                'embedding_time': embedding_time,
                'total_time': total_time,
                'fps': 1.0 / total_time if total_time > 0 else 0
            },
            'image_shape': image.shape
        }
    
    @staticmethod
    def calculate_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings"""
        if embedding1 is None or embedding2 is None:
            return 0.0
        
        # Ensure numpy arrays
        emb1 = np.array(embedding1).flatten()
        emb2 = np.array(embedding2).flatten()
        
        # Calculate cosine similarity
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        return float(dot_product / (norm1 * norm2)) if (norm1 > 0 and norm2 > 0) else 0.0


# Flask Web Service
def create_app():
    """Create Flask application"""
    app = Flask(__name__)
    
    # Initialize the unified service
    try:
        face_service = UnifiedFaceService(use_gpu=True, confidence_threshold=0.5)
        print("✅ Unified Face Service ready")
    except Exception as e:
        print(f"❌ Failed to initialize face service: {e}")
        face_service = None
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        status = "healthy" if face_service is not None else "unhealthy"
        
        gpu_info = {}
        if torch.cuda.is_available():
            gpu_info = {
                'gpu_available': True,
                'gpu_name': torch.cuda.get_device_name(0),
                'gpu_memory_total': torch.cuda.get_device_properties(0).total_memory,
                'gpu_memory_allocated': torch.cuda.memory_allocated(),
            }
        else:
            gpu_info = {'gpu_available': False}
        
        return jsonify({
            "status": status,
            "service": "Unified-Face-Detection-Recognition",
            "model_loaded": face_service is not None,
            "gpu_info": gpu_info
        })
    
    @app.route('/detect_faces', methods=['POST'])
    def detect_faces_endpoint():
        """Face detection only endpoint"""
        if face_service is None:
            return jsonify({"error": "Service not initialized"}), 500
        
        try:
            # Get image from request
            image = _get_image_from_request(request)
            if image is None:
                return jsonify({"error": "No valid image provided"}), 400
            
            # Detect faces only
            faces = face_service.detect_faces(image, return_crops=False)
            
            return jsonify({
                "num_faces": len(faces),
                "faces": faces,
                "image_shape": image.shape
            })
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/process_image', methods=['POST'])
    def process_image_endpoint():
        """Full pipeline: detection + recognition"""
        if face_service is None:
            return jsonify({"error": "Service not initialized"}), 500
        
        try:
            # Get image from request
            image = _get_image_from_request(request)
            if image is None:
                return jsonify({"error": "No valid image provided"}), 400
            
            # Run full pipeline
            result = face_service.process_image_full_pipeline(image)
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/similarity', methods=['POST'])
    def calculate_similarity_endpoint():
        """Calculate similarity between two embeddings"""
        try:
            data = request.json
            if 'embedding1' not in data or 'embedding2' not in data:
                return jsonify({"error": "Two embeddings required"}), 400
            
            similarity = UnifiedFaceService.calculate_similarity(
                data['embedding1'], 
                data['embedding2']
            )
            
            return jsonify({"similarity": similarity})
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    def _get_image_from_request(request):
        """Extract image from Flask request"""
        try:
            if request.json and 'image' in request.json:
                # Base64 encoded image
                image_data = base64.b64decode(request.json['image'])
                np_arr = np.frombuffer(image_data, np.uint8)
                image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                return image
            elif request.json and 'image_path' in request.json:
                # Local file path
                image_path = request.json['image_path']
                image = cv2.imread(image_path)
                return image
            elif request.files and 'image' in request.files:
                # File upload
                file = request.files['image']
                np_arr = np.frombuffer(file.read(), np.uint8)
                image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                return image
            else:
                return None
        except Exception as e:
            print(f"Error extracting image: {e}")
            return None
    
    return app


if __name__ == "__main__":
    # Test the service locally
    print("🧪 Testing Unified Face Service...")
    
    try:
        # Initialize service
        service = UnifiedFaceService(use_gpu=True)
        
        # Test with a sample image
        test_image_path = "E:/01_INCOMING/Jane/20220112_043621.jpg"
        if os.path.exists(test_image_path):
            print(f"📸 Testing with: {test_image_path}")
            
            # Load test image
            image = cv2.imread(test_image_path)
            if image is not None:
                print(f"📐 Image shape: {image.shape}")
                
                # Run full pipeline
                result = service.process_image_full_pipeline(image)
                
                print(f"🎯 Results:")
                print(f"  Faces detected: {result['num_faces']}")
                print(f"  Detection time: {result['timing']['detection_time']:.3f}s")
                print(f"  Embedding time: {result['timing']['embedding_time']:.3f}s")
                print(f"  Total time: {result['timing']['total_time']:.3f}s")
                print(f"  FPS: {result['timing']['fps']:.2f}")
                
                # Print face details
                for i, face in enumerate(result['faces']):
                    print(f"  Face {i+1}: bbox={face['bbox']}, conf={face['confidence']:.3f}, "
                          f"embedding={'✅' if face.get('embedding') else '❌'}")
            else:
                print("❌ Could not load test image")
        else:
            print("ℹ️ Test image not found, skipping local test")
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    # Start Flask server
    print("\n🚀 Starting Unified Face Service on port 8004...")
    app = create_app()
    app.run(host='0.0.0.0', port=8004, debug=False)
