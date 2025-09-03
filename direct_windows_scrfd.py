#!/usr/bin/env python3
"""
Direct Windows SCRFD Service - No WSL Required
Uses the same SCRFD models but runs in Windows Python environment
"""

import cv2
import numpy as np
import sqlite3
import json
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify

# Add the LVFace path to import the unified service
sys.path.append(r'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace')

try:
    import onnxruntime as ort
    from insightface import FaceAnalysis
    SCRFD_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ SCRFD not available: {e}")
    SCRFD_AVAILABLE = False

class DirectWindowsSCRFDService:
    def __init__(self):
        self.app = Flask(__name__)
        self.scrfd_app = None
        self.setup_scrfd()
        self.setup_routes()
    
    def setup_scrfd(self):
        """Initialize SCRFD face detection"""
        if not SCRFD_AVAILABLE:
            print("❌ SCRFD dependencies not available")
            return
            
        try:
            print("🔍 Initializing SCRFD...")
            self.scrfd_app = FaceAnalysis(providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
            self.scrfd_app.prepare(ctx_id=0, det_size=(640, 640))
            print("✅ SCRFD initialized successfully")
        except Exception as e:
            print(f"❌ SCRFD initialization failed: {e}")
            self.scrfd_app = None
    
    def detect_faces_scrfd(self, image):
        """Detect faces using SCRFD"""
        if not self.scrfd_app:
            return []
            
        try:
            faces = self.scrfd_app.get(image)
            face_detections = []
            
            for face in faces:
                bbox = face.bbox.astype(int)
                x1, y1, x2, y2 = bbox
                w, h = x2 - x1, y2 - y1
                
                face_info = {
                    'bbox': [int(x1), int(y1), int(w), int(h)],
                    'confidence': float(face.det_score),
                    'landmarks': face.kps.tolist() if hasattr(face, 'kps') else None,
                    'detector': 'scrfd'
                }
                face_detections.append(face_info)
            
            return face_detections
            
        except Exception as e:
            print(f"❌ SCRFD detection error: {e}")
            return []
    
    def detect_faces_opencv(self, image):
        """Fallback OpenCV face detection"""
        try:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            face_detections = []
            for (x, y, w, h) in faces:
                face_info = {
                    'bbox': [int(x), int(y), int(w), int(h)],
                    'confidence': 0.8,
                    'landmarks': None,
                    'detector': 'opencv'
                }
                face_detections.append(face_info)
            
            return face_detections
            
        except Exception as e:
            print(f"❌ OpenCV detection error: {e}")
            return []
    
    def setup_routes(self):
        @self.app.route('/status', methods=['GET'])
        def status():
            detector = 'scrfd' if self.scrfd_app else 'opencv'
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if self.scrfd_app else ['CPUExecutionProvider']
            
            return jsonify({
                "status": "running",
                "service": "direct_windows_scrfd_service",
                "face_detector": detector,
                "insightface_available": SCRFD_AVAILABLE,
                "providers": providers
            })
        
        @self.app.route('/process_image', methods=['POST'])
        def process_image():
            try:
                data = request.get_json()
                image_path = data.get('image_path')
                
                if not image_path:
                    return jsonify({"error": "No image_path provided"}), 400
                
                # Convert WSL path to Windows path
                if image_path.startswith('/mnt/'):
                    windows_path = image_path.replace('/mnt/', '').replace('/', '\\')
                    windows_path = windows_path[0].upper() + ':' + windows_path[1:]
                else:
                    windows_path = image_path
                
                print(f"🔍 Processing: {os.path.basename(windows_path)}")
                
                if not os.path.exists(windows_path):
                    return jsonify({"error": f"Image not found: {windows_path}"}), 404
                
                # Load image
                image = cv2.imread(windows_path)
                if image is None:
                    return jsonify({"error": "Could not load image"}), 400
                
                # Detect faces (SCRFD first, OpenCV fallback)
                if self.scrfd_app:
                    face_detections = self.detect_faces_scrfd(image)
                    detector_used = "scrfd"
                else:
                    face_detections = self.detect_faces_opencv(image)
                    detector_used = "opencv"
                
                if face_detections:
                    print(f"✅ {detector_used.upper()} detected {len(face_detections)} faces")
                else:
                    print(f"🔍 {os.path.basename(windows_path)}: No faces detected")
                
                # Format response
                detections = []
                for face_info in face_detections:
                    detections.append({
                        "bbox": face_info['bbox'],
                        "confidence": face_info.get('confidence', 0.0),
                        "detector": face_info.get('detector', 'unknown'),
                        "embedding_size": 0,  # No embedding in this version
                        "has_landmarks": face_info.get('landmarks') is not None
                    })
                
                result = {
                    "faces": len(face_detections),
                    "detector": detector_used,
                    "detections": detections
                }
                
                return jsonify(result)
                
            except Exception as e:
                print(f"❌ Error processing image: {e}")
                return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Starting Direct Windows SCRFD Service")
    print("   This bypasses WSL networking issues")
    print("   Running on: http://localhost:8005")
    
    service = DirectWindowsSCRFDService()
    service.app.run(host='0.0.0.0', port=8005, debug=False)
