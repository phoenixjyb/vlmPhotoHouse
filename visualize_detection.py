import cv2
import requests
import json
import os

def visualize_face_detection(image_path, bbox, confidence, detector):
    """Visualize face detection results on the image"""
    
    # Load the original image
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ Could not load image: {image_path}")
        return
    
    print(f"📸 Image dimensions: {image.shape[1]}x{image.shape[0]} (width x height)")
    
    # Extract bounding box coordinates
    x, y, w, h = bbox
    print(f"📦 Bounding box: x={x}, y={y}, width={w}, height={h}")
    print(f"🎯 Detection confidence: {confidence:.3f}")
    print(f"🔍 Detector: {detector}")
    
    # Draw bounding box
    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 3)
    
    # Add confidence text
    label = f"{detector}: {confidence:.3f}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.0
    thickness = 2
    
    # Get text size to create background rectangle
    (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    
    # Draw background rectangle for text
    cv2.rectangle(image, (x, y - text_height - 10), (x + text_width, y), (0, 255, 0), -1)
    
    # Draw text
    cv2.putText(image, label, (x, y - 5), font, font_scale, (0, 0, 0), thickness)
    
    # Save result to a separate visualization directory
    viz_dir = "visualizations"
    os.makedirs(viz_dir, exist_ok=True)
    
    # Get just the filename without path
    filename = os.path.basename(image_path)
    output_filename = filename.replace('.jpg', '_detected.jpg').replace('.png', '_detected.png')
    output_path = os.path.join(viz_dir, output_filename)
    
    cv2.imwrite(output_path, image)
    
    print(f"✅ Visualization saved to: {output_path}")
    
    # Show dimensions for verification
    print(f"📊 Face region covers: {w}x{h} pixels")
    print(f"📊 Face position: ({x}, {y}) to ({x+w}, {y+h})")
    
    return output_path

def test_scrfd_visualization():
    """Test SCRFD detection and visualize results"""
    
    # Test image path - convert WSL path to Windows path
    wsl_image_path = "/mnt/e/01_INCOMING/Jane/20220112_043621.jpg"
    windows_image_path = "E:/01_INCOMING/Jane/20220112_043621.jpg"
    
    if not os.path.exists(windows_image_path):
        print(f"❌ Test image not found: {windows_image_path}")
        print("🔍 Checking for alternative images...")
        
        # Try to find any jpg files in the directory
        dir_path = "E:/01_INCOMING/Jane/"
        if os.path.exists(dir_path):
            jpg_files = [f for f in os.listdir(dir_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            if jpg_files:
                windows_image_path = os.path.join(dir_path, jpg_files[0])
                wsl_image_path = f"/mnt/e/01_INCOMING/Jane/{jpg_files[0]}"
                print(f"✅ Using: {windows_image_path}")
            else:
                print(f"❌ No image files found in {dir_path}")
                return
        else:
            print(f"❌ Directory not found: {dir_path}")
            return
    
    try:
        # Send request to SCRFD service using WSL path
        print(f"🔍 Testing SCRFD detection on: {windows_image_path}")
        print(f"🔍 Using WSL path for service: {wsl_image_path}")
        
        response = requests.post('http://localhost:8003/process_image', 
                               json={"image_path": wsl_image_path})
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Service response: {json.dumps(result, indent=2)}")
            
            if result.get('faces', 0) > 0 and 'detections' in result:
                # Visualize first face detection
                detection = result['detections'][0]
                bbox = detection['bbox']
                confidence = detection['confidence']
                detector = detection['detector']
                
                output_path = visualize_face_detection(windows_image_path, bbox, confidence, detector)
                
                print(f"\n🎨 Open this file to see the detection visualization:")
                print(f"   {output_path}")
                
            else:
                print("❌ No faces detected")
                
        else:
            print(f"❌ Service error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_scrfd_visualization()
