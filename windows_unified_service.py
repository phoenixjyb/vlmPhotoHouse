#!/usr/bin/env python3
"""
Windows-compatible version of unified SCRFD service
Runs directly in Windows Python environment
"""

import cv2
import numpy as np
import requests
import sqlite3
import json
import os
import time
from datetime import datetime
from flask import Flask, request, jsonify

class WindowsUnifiedService:
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
    
    def setup_routes(self):
        @self.app.route('/status', methods=['GET'])
        def status():
            return jsonify({
                "status": "running",
                "service": "windows_unified_scrfd_lvface", 
                "face_detector": "opencv_fallback",
                "note": "SCRFD service running in WSL, using OpenCV fallback"
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
                
                print(f"🔍 Processing: {windows_path}")
                
                # Try to forward to WSL SCRFD service first
                try:
                    response = requests.post("http://172.22.61.27:8003/process_image",
                                           json={"image_path": image_path}, timeout=10)
                    if response.status_code == 200:
                        result = response.json()
                        print(f"✅ SCRFD result: {result.get('faces', 0)} faces")
                        return jsonify(result)
                except:
                    pass
                
                # Fallback to OpenCV detection
                return self.process_with_opencv(windows_path)
                
            except Exception as e:
                print(f"❌ Error: {e}")
                return jsonify({"error": str(e)}), 500
    
    def process_with_opencv(self, image_path):
        """Fallback OpenCV face detection"""
        try:
            if not os.path.exists(image_path):
                return jsonify({"error": f"Image not found: {image_path}"}), 404
            
            # Load image
            image = cv2.imread(image_path)
            if image is None:
                return jsonify({"error": "Could not load image"}), 400
            
            # OpenCV face detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            detections = []
            for (x, y, w, h) in faces:
                detections.append({
                    "bbox": [int(x), int(y), int(w), int(h)],
                    "confidence": 0.8,  # Default confidence for OpenCV
                    "detector": "opencv_fallback",
                    "embedding_size": 0,  # No embedding in fallback
                    "has_landmarks": False
                })
            
            result = {
                "faces": len(detections),
                "detector": "opencv_fallback",
                "detections": detections
            }
            
            print(f"🔍 OpenCV fallback: {len(faces)} faces detected")
            return jsonify(result)
            
        except Exception as e:
            print(f"❌ OpenCV fallback error: {e}")
            return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Starting Windows Unified Service (SCRFD Proxy + OpenCV Fallback)")
    service = WindowsUnifiedService()
    service.app.run(host='0.0.0.0', port=8004, debug=False)
